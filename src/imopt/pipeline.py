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

from . import geo, ine, macro, outlook, parishes, scoring, tracking

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
    fetched: dict[tuple, pd.DataFrame] = {}   # o mesmo indicador com outras categorias: um só pedido
    for key, spec in cfg["ine"]["indicators"].items():
        varcd = spec.get("varcd")
        if not varcd:
            status[key] = "sem código (config)"
            continue
        try:
            if ine_down:
                raise ConnectionError("INE não contactado (modo cache ou já indisponível nesta execução)")
            fetch_kw = {"retries": 1, "timeout": (10, 180)} if mode == "auto" else {}
            ckey = (varcd, tuple(sorted((k, v) for k, v in (spec.get("dims") or {}).items() if k.startswith("api_"))))
            if ckey not in fetched:
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
                fetched[ckey] = raw
            raw = fetched[ckey]
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
EXTRA_KEYS = ("sales_price_new", "sales_price_existing", "valuation_apartments", "valuation_houses", "rent_q1",
              "rent_q3", "rent_contracts", "tourism_nights", "housing_credit_pc", "sales_price_domestic",
              "sales_price_foreign", "sales_price_apartments", "sales_price_t01", "sales_price_t2", "sales_price_t3",
              "sales_price_t4", "valuation_count", "valuation_count_apartments",
              "valuation_count_houses", "sales_price_households", "sales_price_companies")


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


def real_index(nominal: pd.DataFrame | None, hicp: pd.DataFrame | None) -> pd.DataFrame | None:
    """HPI real = HPI nominal / IHPC, recentrado para média de 2015 = 100 (ambos são base 2015)."""
    if nominal is None or hicp is None or nominal.empty or hicp.empty:
        return None
    df = nominal[["period", "value"]].merge(hicp[["period", "value"]], on="period", suffixes=("", "_p"))
    if df.empty:
        return None
    df["value"] = df["value"] / df["value_p"] * 100
    ref = df[df["period"].str.startswith("2015")]["value"]
    if len(ref) == 4:
        df["value"] = df["value"] * 100 / ref.mean()
    return df[["period", "value"]].sort_values("period").reset_index(drop=True)


def build_outputs(frames: dict[str, pd.DataFrame], macro_frames: dict[str, pd.DataFrame],
                  ine_status: dict, macro_status: dict, out_dir: Path,
                  geojson: dict | None, demo: bool = False, geo_unmatched: list[str] | None = None,
                  forecast_log: Path | None = None, parish_geojson: dict | None = None) -> dict:
    sales = municipal(frames.get("sales_price_12m"))
    if sales is None or sales.empty:
        raise RuntimeError("sem dados de preços por concelho: nada para calcular")
    rent = municipal(frames.get("rent_new_contracts"))
    permits = municipal(frames.get("building_permits"))
    completed = municipal(frames.get("completed_dwellings"))
    income = municipal(frames.get("income"))
    density = municipal(frames.get("population_density"))
    ageing = municipal(frames.get("ageing_index"))
    migration = municipal(frames.get("migration_balance"))

    feats = scoring.municipal_features(sales, rent, permits, completed, income, density, ageing, migration)
    extras = scoring.extra_features({k: municipal(frames.get(k)) for k in EXTRA_KEYS})
    if not extras.empty:
        feats = feats.merge(extras, on="dico", how="left")
    price_series = series_by_dico(sales)
    rent_series = series_by_dico(rent)

    hpi = macro_frames.get("eurostat_hpi")
    if hpi is None and "hpi" in frames:  # HPI nacional do INE como alternativa
        h = frames["hpi"]
        h = h[h["level"].isin(["national", "nuts1"])].sort_values("sort_key")
        hpi = h[["period", "value"]].drop_duplicates("period") if not h.empty else None
    national = scoring.national_scores(hpi, macro_frames.get("euribor_12m"), macro_frames.get("bis_credit_gap"))
    hpi_real = real_index(hpi, macro_frames.get("eurostat_hicp"))
    national["series"] = {
        "hpi": [[r.period, _clean(r.value)] for r in hpi.itertuples()] if hpi is not None else [],
        "hpi_real": [[r.period, _clean(r.value)] for r in hpi_real.itertuples()] if hpi_real is not None else [],
        **{k: [[r.period, _clean(r.value)] for r in macro_frames[k].itertuples()] if k in macro_frames else []
           for k in ("euribor_3m", "euribor_6m", "euribor_12m")},
        "credit_gap": [[r.period, _clean(r.value)] for r in macro_frames["bis_credit_gap"].itertuples()]
        if "bis_credit_gap" in macro_frames else [],
    }

    cols = ["price", "latest_key", "price_growth_1y", "price_growth_3y", "price_growth_5y", "rent",
            "rent_year", "rent_growth_1y", "gross_yield", "price_to_rent_years", "income", "income_year",
            "price_to_income_months", "rent_to_income", "density", "ageing_index", "migration_balance",
            "permits", "permits_growth",
            "completed", "completed_growth", "score_valuation", "score_supply", "score_overall", "band",
            "volatility", "volatile", "price_new", "price_existing", "new_premium", "val_apt", "val_apt_growth_1y",
            "val_house", "val_house_growth_1y", "rent_q1", "rent_q3", "rent_spread", "rent_contracts",
            "rent_contracts_year", "rent_contracts_growth", "tourism_nights", "tourism_nights_year",
            "housing_credit_pc", "housing_credit_pc_year", "price_domestic", "price_foreign", "foreign_premium",
            "price_apt_sales", "price_t01", "price_t2", "price_t3", "price_t4", "val_count", "val_count_growth_1y",
            "val_count_apt", "val_count_apt_growth_1y", "val_count_house", "val_count_house_growth_1y",
            "price_households", "price_companies", "companies_premium"]
    # Perspetivas (previsões e padrões): só leitura, não mexe nos scores; falha de forma não-fatal.
    try:
        outlook_data, per = outlook.build(frames, macro_frames, feats, geojson, hpi, hpi_real, demo=demo)
    except Exception as e:  # noqa: BLE001
        log.warning("perspetivas falharam: %s", e)
        outlook_data, per = {"demo": demo, "errors": {"build": str(e)[:200]}}, {}
    # Arquivo de previsões (só em builds reais): guarda as deste build e avalia as antigas contra o publicado.
    if forecast_log is not None:
        try:
            archive = tracking.record(tracking.load(forecast_log), outlook_data, per, feats)
            tracking.save(archive, forecast_log)
            outlook_data["tracking"], past = tracking.evaluate(archive, sales, rent)
            for d, v in past.items():
                per.setdefault(d, {}).update(v)
            outlook_data, per = outlook.sanitize(outlook_data), outlook.sanitize(per)
        except Exception as e:  # noqa: BLE001
            log.warning("arquivo de previsões falhou: %s", e)
            outlook_data.setdefault("errors", {})["tracking"] = str(e)[:200]
    munis = []
    for r in feats.to_dict("records"):
        item = {"dico": r["dico"], "name": r["name"]}
        item.update({c: _clean(r.get(c)) for c in cols if c in r})
        item.update(per.get(str(r["dico"]), {}))
        item["series"] = {"price": price_series.get(r["dico"], []), "rent": rent_series.get(r["dico"], [])}
        munis.append(item)

    latest_period = sales.sort_values("sort_key")["period"].iloc[-1]
    meta = {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "demo": demo,
        "latest_price_period": latest_period,
        "n_municipalities": len(munis),
        "sources": {"ine": ine_status, "macro": macro_status},
        "geo_unmatched": (geo_unmatched or [])[:20],
        "geo_unmatched_count": len(geo_unmatched or []),
        "disclaimer": ("Indicador informativo, não é aconselhamento financeiro. Scores municipais são "
                       "relativos (percentis entre concelhos) e não foram validados por backtest."),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    geo.dump(munis, str(out_dir / "municipalities.json"))
    geo.dump(national, str(out_dir / "national.json"))
    geo.dump(meta, str(out_dir / "meta.json"))
    geo.dump(outlook_data, str(out_dir / "outlook.json"))
    # Freguesias: tabela sempre que o INE as publique; mapa só se houver fronteiras.
    try:
        ptab = parishes.table(frames.get("sales_price_12m"), frames.get("rent_parish"),
                              dict(zip(feats["dico"].astype(str), feats["price"])))
        ptab = parishes.add_neighbours(ptab, parish_geojson)
        rows = [{k: _clean(v) for k, v in r.items()} for r in ptab.to_dict("records")]
        geo.dump({"period": ptab.attrs.get("period"), "with_map": False, "rows": rows}, str(out_dir / "freguesias.json"))
        pgj = parishes.geojson_out(ptab, parish_geojson)
        if pgj is not None:
            geo.dump(pgj, str(out_dir / "freguesias.geojson"))
            geo.dump({"period": ptab.attrs.get("period"), "with_map": True, "rows": rows}, str(out_dir / "freguesias.json"))
        meta["parishes"] = f"{len(rows)} freguesias" + (f", {len(pgj['features'])} no mapa" if pgj else ", sem mapa")
    except Exception as e:  # noqa: BLE001
        log.warning("freguesias falharam: %s", e)
        meta["parishes"] = f"ERRO: {str(e)[:150]}"
    geo.dump(meta, str(out_dir / "meta.json"))
    if geojson is not None:
        keep = {m["dico"]: {"name": m["name"], "band": m["band"], "score": m["score_overall"], "price": m["price"],
                            "yield": m["gross_yield"], "g1y": m["price_growth_1y"], "fc": m.get("fc_growth_12m"),
                            "fv": m.get("fv_gap"), "fp": m.get("foreign_premium")} for m in munis}
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
            if len(unmatched) > 0.1 * len(gj.get("features", [])):
                sample = (gj["features"][0].get("properties") if gj.get("features") else None)
                ine_status["geo"] = (f"AVISO: {len(unmatched)} fronteiras sem código DICO; "
                                     f"propriedades de exemplo: {sample}")
                log.warning(ine_status["geo"])
            else:
                ine_status["geo"] = f"ok ({len(gj['features']) - len(unmatched)} fronteiras ligadas)"
                geo.dump(geo.slim_geojson(geojson, {}), str(data_dir / "clean" / "geo_municipalities.json"))
        except Exception as e:  # noqa: BLE001
            cached_geo = data_dir / "clean" / "geo_municipalities.json"
            if cached_geo.exists():
                import json as _json
                geojson = _json.loads(cached_geo.read_text(encoding="utf-8"))
                ine_status["geo"] = f"CACHE (download falhou): {str(e)[:100]}"
                log.warning("fronteiras: a usar cache (%s)", e)
            else:
                log.warning("geometrias indisponíveis: %s", e)
                ine_status["geo"] = f"ERRO: {e}"
    parish_gj = None if skip_geo else load_parish_geojson(cfg, data_dir, ine_status)
    return build_outputs(frames, macro_frames, ine_status, macro_status, out_dir, geojson, geo_unmatched=unmatched,
                         forecast_log=data_dir / "clean" / "forecast_log.parquet", parish_geojson=parish_gj)


def load_parish_geojson(cfg: dict, data_dir: Path, status: dict) -> dict | None:
    """Fronteiras das freguesias: tenta os URLs configurados; guarda a primeira que funcionar; senão usa a cache."""
    import json as _json
    cached = data_dir / "clean" / "geo_parishes.json"
    errors = []
    for url in cfg["geo"].get("parishes_geojson") or []:
        try:
            gj, n = geo.attach_code(geo.download_geojson(url), cfg["geo"].get("parish_props", []))
            if n < 100:
                raise ValueError(f"só {n} freguesias com código DICOFRE; propriedades de exemplo: "
                                 f"{(gj.get('features') or [{}])[0].get('properties')}")
            slim = geo.slim_geojson(gj, {}, tolerance=0.0008, key="code")
            cached.parent.mkdir(parents=True, exist_ok=True)
            geo.dump(slim, str(cached))
            status["geo_parishes"] = f"ok ({n} freguesias, {url})"
            return slim
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url}: {str(e)[:150]}")
    if cached.exists():
        status["geo_parishes"] = "CACHE" + (f" (download falhou: {errors[0]})" if errors else "")
        return _json.loads(cached.read_text(encoding="utf-8"))
    status["geo_parishes"] = "ERRO: " + ("; ".join(errors) or "sem URL configurado")
    log.warning("fronteiras das freguesias indisponíveis: %s", status["geo_parishes"])
    return None
