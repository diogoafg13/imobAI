"""Orquestração: fontes -> Parquet (raw/clean) -> DuckDB -> features/scores -> JSON para o site."""
from __future__ import annotations

import datetime as dt
import logging
import os
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import yaml

from . import geo, ine, macro, scoring

log = logging.getLogger("imopt")
ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None) -> dict:
    with open(path or ROOT / "config" / "sources.yml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


# ---------------------------------------------------------------- ingestão
def ingest_ine(cfg: dict, data_dir: Path, today: str) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    frames: dict[str, pd.DataFrame] = {}
    status: dict[str, str] = {}
    base, lang = cfg["ine"]["base_url"], cfg["ine"].get("lang", "PT")
    # IMOPT_INE_MODE: live (defeito: 5 tentativas), auto (1 tentativa rápida; se o INE não
    # responder, usa data/clean e não insiste nos restantes), cache (nunca usa a rede).
    mode = os.environ.get("IMOPT_INE_MODE", "live").lower()
    ine_down = mode == "cache"
    for key, spec in cfg["ine"]["indicators"].items():
        varcd = spec.get("varcd")
        if not varcd:
            status[key] = "sem código (config)"
            continue
        try:
            if ine_down:
                raise ConnectionError("INE não contactado (modo cache ou já indisponível nesta execução)")
            fetch_kw = {"retries": 1, "timeout": (10, 180)} if mode == "auto" else {}
            try:
                payload = ine.fetch(base, varcd, lang, spec.get("dims"), **fetch_kw)
            except RuntimeError:
                if mode == "auto":
                    ine_down = True
                raise
            raw = ine.parse_response(payload, varcd)
            if raw.empty:
                raise ValueError("resposta vazia")
            _write_parquet(raw, data_dir / "raw" / "ine" / varcd / f"{today}.parquet")
            filt = {k: v for k, v in (spec.get("dims") or {}).items() if not k.startswith("api_")}
            df = ine.apply_dim_filters(raw, filt, varcd)
            _write_parquet(df, data_dir / "clean" / f"ine_{key}.parquet")
            frames[key] = df
            chosen = ine.dim_labels(raw, filt)
            status[key] = f"ok ({len(df)} linhas, {df['period'].max()})" + (f" [{chosen}]" if chosen else "")
            log.info("%s: %s", key, status[key])
        except Exception as e:  # noqa: BLE001
            cached = data_dir / "clean" / f"ine_{key}.parquet"
            if cached.exists() and not isinstance(e, ine.AmbiguousDimensionError):
                frames[key] = pd.read_parquet(cached)
                status[key] = f"CACHE (INE indisponível, dados do último snapshot): {str(e)[:120]}"
                log.warning("indicador %s (%s): INE falhou, a usar snapshot anterior: %s", key, varcd, e)
                continue
            status[key] = f"ERRO: {e}"
            log.warning("indicador %s (%s) falhou: %s", key, varcd, e)
            if not spec.get("optional") and key == "sales_price_12m":
                raise
    return frames, status


def ingest_macro(cfg: dict, data_dir: Path) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    frames, status = {}, {}
    for key, spec in cfg.get("macro", {}).items():
        try:
            df = macro.FETCHERS[key](spec)
            _write_parquet(df, data_dir / "clean" / f"macro_{key}.parquet")
            frames[key] = df
            status[key] = f"ok ({len(df)} pontos, {df['period'].iloc[-1]})"
        except Exception as e:  # noqa: BLE001
            status[key] = f"ERRO: {e}"
            log.warning("macro %s falhou: %s", key, e)
    return frames, status


# ---------------------------------------------------------------- análise
def municipal(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    return df[df["level"] == "municipality"].dropna(subset=["dico", "value"])


def series_by_dico(df: pd.DataFrame | None) -> dict[str, list[list]]:
    """Séries por concelho via DuckDB (ordenadas por período)."""
    if df is None or df.empty:
        return {}
    con = duckdb.connect()
    con.register("t", df[["dico", "period", "sort_key", "value"]])
    rows = con.execute("SELECT dico, period, value FROM t ORDER BY dico, sort_key").fetchall()
    out: dict[str, list[list]] = {}
    for d, p, v in rows:
        out.setdefault(d, []).append([p, round(float(v), 4)])
    return out


def _clean(v: Any) -> Any:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        v = v.item()
    return round(v, 4) if isinstance(v, float) else v


def build_outputs(frames: dict[str, pd.DataFrame], macro_frames: dict[str, pd.DataFrame],
                  ine_status: dict, macro_status: dict, out_dir: Path,
                  geojson: dict | None, demo: bool = False, geo_unmatched: list[str] | None = None) -> dict:
    sales = municipal(frames.get("sales_price_12m"))
    if sales is None or sales.empty:
        raise RuntimeError("sem dados de preços por concelho: nada para calcular")
    rent = municipal(frames.get("rent_new_contracts"))
    permits = municipal(frames.get("building_permits"))
    completed = municipal(frames.get("completed_dwellings"))

    feats = scoring.municipal_features(sales, rent, permits, completed)
    price_series = series_by_dico(sales)
    rent_series = series_by_dico(rent)

    hpi = macro_frames.get("eurostat_hpi")
    if hpi is None and "hpi" in frames:  # HPI nacional do INE como alternativa
        h = frames["hpi"]
        h = h[h["level"].isin(["national", "nuts1"])].sort_values("sort_key")
        hpi = h[["period", "value"]].drop_duplicates("period") if not h.empty else None
    national = scoring.national_scores(hpi, macro_frames.get("euribor_12m"), macro_frames.get("bis_credit_gap"))
    national["series"] = {
        "hpi": [[r.period, _clean(r.value)] for r in hpi.itertuples()] if hpi is not None else [],
        "euribor_12m": [[r.period, _clean(r.value)] for r in macro_frames["euribor_12m"].itertuples()]
        if "euribor_12m" in macro_frames else [],
        "credit_gap": [[r.period, _clean(r.value)] for r in macro_frames["bis_credit_gap"].itertuples()]
        if "bis_credit_gap" in macro_frames else [],
    }

    cols = ["price", "latest_key", "price_growth_1y", "price_growth_3y", "price_growth_5y", "rent",
            "rent_year", "rent_growth_1y", "gross_yield", "price_to_rent_years", "permits", "permits_growth",
            "completed", "completed_growth", "score_valuation", "score_supply", "score_overall", "band"]
    munis = []
    for r in feats.to_dict("records"):
        item = {"dico": r["dico"], "name": r["name"]}
        item.update({c: _clean(r.get(c)) for c in cols if c in r})
        item["series"] = {"price": price_series.get(r["dico"], []), "rent": rent_series.get(r["dico"], [])}
        munis.append(item)

    latest_period = sales.sort_values("sort_key")["period"].iloc[-1]
    meta = {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "demo": demo,
        "latest_price_period": latest_period,
        "n_municipalities": len(munis),
        "sources": {"ine": ine_status, "macro": macro_status},
        "geo_unmatched": geo_unmatched or [],
        "disclaimer": ("Indicador informativo, não é aconselhamento financeiro. Scores municipais são "
                       "relativos (percentis entre concelhos) e não foram validados por backtest."),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    geo.dump(munis, str(out_dir / "municipalities.json"))
    geo.dump(national, str(out_dir / "national.json"))
    geo.dump(meta, str(out_dir / "meta.json"))
    if geojson is not None:
        keep = {m["dico"]: {"name": m["name"], "band": m["band"], "score": m["score_overall"], "price": m["price"],
                            "yield": m["gross_yield"], "g1y": m["price_growth_1y"]} for m in munis}
        geo.dump(geo.slim_geojson(geojson, keep), str(out_dir / "concelhos.geojson"))
    return meta


def run(data_dir: str | Path | None = None, out_dir: str | Path | None = None, skip_geo: bool = False) -> dict:
    cfg = load_config()
    data_dir = Path(data_dir or ROOT / "data")
    out_dir = Path(out_dir or ROOT / "site" / "data")
    today = dt.date.today().strftime("%Y%m%d")
    frames, ine_status = ingest_ine(cfg, data_dir, today)
    macro_frames, macro_status = ingest_macro(cfg, data_dir)

    geojson, unmatched = None, []
    if not skip_geo:
        try:
            gj = geo.download_geojson(cfg["geo"]["municipalities_geojson"])
            sales = municipal(frames["sales_price_12m"])
            by_name = {geo.norm_name(n): d for d, n in sales.drop_duplicates("dico")[["dico", "geoname"]].itertuples(index=False)}
            geojson, unmatched = geo.attach_dico(gj, cfg["geo"]["dico_props"], cfg["geo"]["name_props"], by_name)
        except Exception as e:  # noqa: BLE001
            log.warning("geometrias indisponíveis: %s", e)
            ine_status["geo"] = f"ERRO: {e}"
    return build_outputs(frames, macro_frames, ine_status, macro_status, out_dir, geojson, geo_unmatched=unmatched)
