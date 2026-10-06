"""Orquestração: fontes -> Parquet (raw/clean) -> DuckDB -> features/scores -> JSON para o site."""
from __future__ import annotations

import datetime as dt
import logging
import os
import time
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import yaml

from . import al, changes, discover, flood, freshness, osm, geo, housing, imi, ine, macro, outlook, parishes, scoring, tracking

log = logging.getLogger("imopt")
ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None) -> dict:
    with open(path or ROOT / "config" / "sources.yml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


# ---------------------------------------------------------------- ingestão
def ingest_ine(cfg: dict, data_dir: Path, today: str, pause: float = 60.0) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    frames: dict[str, pd.DataFrame] = {}
    status: dict[str, str] = {}
    base, lang = cfg["ine"]["base_url"], cfg["ine"].get("lang", "PT")
    # IMOPT_INE_MODE: live (defeito: 5 tentativas por indicador), cache (nunca usa a rede) ou auto (o do
    # workflow): 1 tentativa rápida por indicador. O INE recusa os runners do GitHub de forma intermitente (a meio
    # de um build, não sempre): em auto só se desiste depois de 3 falhas seguidas, e os que falharam têm uma
    # segunda volta no fim, depois de uma pausa. O que continuar a falhar usa o último snapshot (data/clean).
    mode = os.environ.get("IMOPT_INE_MODE", "live").lower()
    fetch_kw = {"retries": 1, "timeout": (10, 180)} if mode == "auto" else {}
    fetched: dict[tuple, pd.DataFrame] = {}   # o mesmo indicador com outras categorias: um só pedido
    errors: dict[str, Exception] = {}

    def one(key: str, spec: dict) -> None:
        varcd = spec["varcd"]
        ckey = (varcd, tuple(sorted((k, v) for k, v in (spec.get("dims") or {}).items() if k.startswith("api_"))))
        if ckey not in fetched:
            payload = ine.fetch(base, varcd, lang, spec.get("dims"), **fetch_kw)
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

    def run_pass(keys: list[str]) -> None:
        streak = 0
        for key in keys:
            spec = cfg["ine"]["indicators"][key]
            if mode == "cache" or (mode == "auto" and streak >= 3):
                errors[key] = ConnectionError("INE não contactado (modo cache ou indisponível nesta execução)")
                continue
            try:
                one(key, spec)
                errors.pop(key, None)
                streak = 0
            except ine.AmbiguousDimensionError as e:
                errors[key] = e
            except Exception as e:  # noqa: BLE001
                errors[key] = e
                if isinstance(e, RuntimeError):      # falha de rede (ine.fetch esgotou as tentativas)
                    streak += 1

    keys = []
    for key, spec in cfg["ine"]["indicators"].items():
        if spec.get("varcd"):
            keys.append(key)
        else:
            status[key] = "sem código (config)"
    run_pass(keys)
    retry = [k for k, e in errors.items() if not isinstance(e, ine.AmbiguousDimensionError)]
    if mode == "auto" and retry:
        log.warning("INE: %d indicadores falharam; segunda volta daqui a %.0fs", len(retry), pause)
        time.sleep(pause)
        run_pass(retry)
    for key, e in errors.items():
        spec, varcd = cfg["ine"]["indicators"][key], cfg["ine"]["indicators"][key]["varcd"]
        cached = data_dir / "clean" / f"ine_{key}.parquet"
        if cached.exists() and not isinstance(e, ine.AmbiguousDimensionError):
            frames[key] = pd.read_parquet(cached)
            status[key] = f"CACHE (INE indisponível, dados do último snapshot): {str(e)[:120]}"
            log.warning("indicador %s (%s): INE falhou, a usar snapshot anterior: %s", key, varcd, e)
            continue
        status[key] = f"ERRO: {e}"
        log.warning("indicador %s (%s) falhou: %s", key, varcd, e)
        if not spec.get("optional") and key == "sales_price_12m":
            raise e
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
            cached = data_dir / "clean" / f"macro_{key}.parquet"
            if cached.exists():      # como no INE: a série do último build que a obteve, em vez de nenhuma
                frames[key] = pd.read_parquet(cached)
                status[key] = f"CACHE ({str(e)[:150]})"
            else:
                status[key] = f"ERRO: {e}"
            log.warning("macro %s falhou: %s", key, e)
    return frames, status


# ---------------------------------------------------------------- análise
EXTRA_KEYS = ("sales_price_new", "sales_price_existing", "valuation_apartments", "valuation_houses", "rent_q1",
              "rent_q3", "rent_contracts", "tourism_nights", "housing_credit_pc", "sales_price_domestic",
              "sales_price_foreign", "sales_price_apartments", "sales_price_t01", "sales_price_t2", "sales_price_t3",
              "sales_price_t4", "valuation_count", "valuation_count_apartments",
              "valuation_count_houses", "sales_price_households", "sales_price_companies")

# Contexto de habitação (imopt/housing.py): IRS de quem vive no concelho, oferta nova, parque e camas turísticas.
CONTEXT_KEYS = ("irs_median", "dwellings_stock", "tourism_beds", "tourism_beds_al", "census_total",
                "census_secondary", "census_vacant_market", "census_vacant_other", "tourism_guests",
                "tourism_guests_al", "tourism_occupancy", "population") + tuple(f"tax_households_{k}" for k in range(1, 7))


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
                  forecast_log: Path | None = None, parish_geojson: dict | None = None,
                  ine_summary: dict | None = None, imi_rates: pd.DataFrame | None = None,
                  imi_status: str | None = None, al_points: pd.DataFrame | None = None,
                  al_status: str | None = None, stale: list[dict] | None = None,
                  osm_points: pd.DataFrame | None = None, osm_status: str | None = None,
                  flood_zones: dict | None = None, flood_status: str | None = None) -> dict:
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
    ctx = housing.context_features({k: municipal(housing.dico4(frames.get(k))) for k in CONTEXT_KEYS})
    if not ctx.empty:
        feats = feats.merge(ctx, on="dico", how="left")
    feats = scoring.real_growth(feats, macro_frames.get("eurostat_hicp"))
    price_series = series_by_dico(sales)
    h_at, h_last = scoring.hicp_asof(macro_frames.get("eurostat_hicp"))
    h_ref = h_at(10 ** 9)

    def real_series(ser):
        out = []
        for p, v in ser:
            k = int(p[:4]) * 100 + int(p[-1])
            hv = h_at(k)
            out.append([p, round(v * h_ref / hv, 1) if hv and hv == hv else None])
        return out
    rent_series = series_by_dico(rent)

    hpi = macro_frames.get("eurostat_hpi")
    if hpi is None and "hpi" in frames:  # HPI nacional do INE como alternativa
        h = frames["hpi"]
        h = h[h["level"].isin(["national", "nuts1"])].sort_values("sort_key")
        hpi = h[["period", "value"]].drop_duplicates("period") if not h.empty else None
        if hpi is not None:   # o INE publica em base 2025: repõe em 2015 = 100, como o do Eurostat e o resto do site
            b15 = hpi.loc[hpi["period"].astype(str).str.startswith("2015"), "value"]
            if len(b15) == 4 and b15.mean() > 0:
                hpi = hpi.assign(value=hpi["value"] / b15.mean() * 100)
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

    cols = ["price", "latest_key", "price_growth_1y", "price_growth_3y", "price_growth_5y", "price_growth_1y_real",
            "price_growth_3y_real", "price_growth_5y_real", "hicp_period", "rent",
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
            "price_households", "price_companies", "companies_premium", "irs_median", "irs_year", "irs_growth_1y",
            "dwellings", "dwellings_year", "tourism_beds", "tourism_beds_year", "beds_per_100", "al_beds",
            "al_beds_year", "al_beds_per_100", "census_total", "census_year", "secondary_share", "vacant_share",
            "vacant_market_share", "guests_12m", "guests_growth_1y", "guests_until", "guests_al_share", "occupancy",
            "occupancy_year", "occupancy_chg", "population", "population_year", "tax_hh_year", "tax_hh_total",
            "tax_hh_1", "tax_hh_2", "tax_hh_3", "tax_hh_4", "tax_hh_5", "tax_hh_6", "score_part_g1y", "score_part_g3y", "score_part_yield"]
    # Perspetivas (previsões e padrões): só leitura, não mexe nos scores; falha de forma não-fatal.
    try:
        outlook_data, per = outlook.build(frames, macro_frames, feats, geojson, hpi, hpi_real, demo=demo)
    except Exception as e:  # noqa: BLE001
        log.warning("perspetivas falharam: %s", e)
        outlook_data, per = {"demo": demo, "errors": {"build": str(e)[:200]}}, {}
    try:
        ch, ch_per = changes.quarter_changes(sales, rent, feats)
        if ch:
            outlook_data["changes"] = outlook.sanitize(ch)
            for d, v in ch_per.items():
                per.setdefault(d, {}).update(v)
    except Exception as e:  # noqa: BLE001
        log.warning("resumo trimestral falhou: %s", e)
        outlook_data.setdefault("errors", {})["changes"] = str(e)[:200]
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
    imi_per = imi.per_municipality(imi_rates)
    munis = []
    for r in feats.to_dict("records"):
        item = {"dico": r["dico"], "name": r["name"]}
        item.update({c: _clean(r.get(c)) for c in cols if c in r})
        item.update(per.get(str(r["dico"]), {}))
        item.update(imi_per.get(str(r["dico"]), {}))
        item["series"] = {"price": price_series.get(r["dico"], []), "rent": rent_series.get(r["dico"], [])}
        if h_last:
            item["series"]["price_real"] = real_series(item["series"]["price"])
        munis.append(item)

    latest_period = sales.sort_values("sort_key")["period"].iloc[-1]
    meta = {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "demo": demo,
        "latest_price_period": latest_period,
        "n_municipalities": len(munis),
        "sources": {"ine": ine_status, "macro": macro_status, **({"at": {"imi_rates": imi_status}} if imi_status else {}),
                    **({"turismo": {"al_rnal": al_status}} if al_status else {}),
                    **({"osm": {"osm_points": osm_status}} if osm_status else {}),
                    **({"apa": {"flood_zones": flood_status}} if flood_status else {})},
        "ine_summary": ine_summary,
        "stale": stale or [],
        "geo_unmatched": (geo_unmatched or [])[:20],
        "geo_unmatched_count": len(geo_unmatched or []),
        "disclaimer": ("Indicador informativo, não é aconselhamento financeiro. Scores municipais são "
                       "relativos (percentis entre concelhos) e não foram validados por backtest."),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    # Séries e previsões por concelho num ficheiro à parte (carregado pelo site só quando é preciso): o
    # municipalities.json fica com os números do ranking, do mapa e do detalhe, e abre mais depressa.
    try:      # feeds RSS por concelho (precisam das séries, que a seguir saem do municipalities.json)
        from . import feeds
        feeds.write(munis, out_dir, os.environ.get("IMOPT_SITE_URL", "https://diogoafg13.github.io/imobAI/"),
                    str(sales.sort_values("sort_key")["period"].iloc[-1]))
    except Exception as e:  # noqa: BLE001
        log.warning("feeds RSS falharam: %s", e)
    heavy = {}
    for item in munis:
        rent_s = item.get("series", {}).get("rent") or []
        item["rent_first"] = int(str(rent_s[0][0])[:4]) if rent_s else None
        heavy[item["dico"]] = {k: item.pop(k) for k in ("series", "fc", "effort_hist") if k in item}
    geo.dump(heavy, str(out_dir / "series.json"))
    try:
        geo.dump(housing.history_export(frames.get("sales_price_12m"), frames.get("valuation_apartments"),
                                        frames.get("valuation_houses"), macro_frames.get("eurostat_hicp"),
                                        frames.get("bank_valuation"),
                                        {k: frames.get(f"sales_price_{k}") for k, _ in housing.TYPOLOGIES},
                                        frames.get("sales_price_existing")),
                 str(out_dir / "history.json"))
    except Exception as e:  # noqa: BLE001
        log.warning("histórico para \"O meu imóvel\" falhou: %s", e)
    geo.dump(munis, str(out_dir / "municipalities.json"))
    geo.dump(national, str(out_dir / "national.json"))
    geo.dump(meta, str(out_dir / "meta.json"))
    geo.dump(outlook_data, str(out_dir / "outlook.json"))
    # Freguesias: tabela sempre que o INE as publique; mapa só se houver fronteiras.
    try:
        ptab = parishes.table(frames.get("sales_price_12m"), frames.get("rent_parish"),
                              dict(zip(feats["dico"].astype(str), feats["price"])), frames.get("irs_median"),
                              {k: frames.get(f"census_{k}") for k in ("total", "secondary", "vacant_market", "vacant_other")},
                              frames.get("rent_contracts"))
        try:      # alojamento local (RNAL) por freguesia: pelas coordenadas, ou pelo nome dentro do concelho
            if al_points is not None and not ptab.empty:
                mnames = dict(zip(feats["dico"].astype(str), feats["name"]))
                pn = {c: (n, mnames.get(str(c)[:4], "")) for c, n in zip(ptab["code"], ptab["name"]) if isinstance(n, str)}
                agg = al.by_parish(al_points, parish_geojson, pn)
                ct = ptab.set_index("code")["census_total"] if "census_total" in ptab else None
                f = al.per_parish_fields(agg, ct)
                if f is not None:
                    ptab = ptab.merge(f, left_on="code", right_index=True, how="left")
                    log.info("alojamento local: %.0f%% dos registos ligados a uma freguesia", 100 * agg.attrs.get("matched", 0))
        except Exception as e:  # noqa: BLE001
            log.warning("alojamento local por freguesia falhou: %s", e)
        try:      # escolas, saúde e estações (OpenStreetMap) por freguesia
            if osm_points is not None and not ptab.empty:
                cnt = osm.by_parish(osm_points, parish_geojson)
                if cnt is not None:
                    ptab = ptab.merge(cnt, left_on="code", right_index=True, how="left")
                    for k in ("school", "health", "station"):
                        ptab[f"n_{k}"] = ptab[f"n_{k}"].fillna(0)
                    if "census_total" in ptab:
                        for k in ("school", "health"):
                            ptab[f"{k}_per_1000"] = (ptab[f"n_{k}"] / ptab["census_total"] * 1000).where(ptab["census_total"] > 0)
        except Exception as e:  # noqa: BLE001
            log.warning("OpenStreetMap por freguesia falhou: %s", e)
        try:      # edifícios dos Censos 2021: antigos (antes de 1961) e a precisar de obras médias ou profundas
            bld = parishes.buildings({k: frames.get(f"census_bld_{k}") for k in parishes.BLD_KEYS})
            if bld is not None and not ptab.empty:
                ptab = ptab.merge(bld, left_on="code", right_index=True, how="left")
        except Exception as e:  # noqa: BLE001
            log.warning("edifícios por freguesia falharam: %s", e)
        try:      # % da área em zona inundável cartografada (APA); sem zona cartografada fica sem valor
            if flood_zones is not None and not ptab.empty:
                fl = flood.by_parish(flood_zones, parish_geojson)
                if fl:
                    ptab["flood_pct"] = ptab["code"].astype(str).map(fl)
                    meta["flood"] = {"rp_years": flood_zones.get("rp_years"), "fetched": flood_zones.get("fetched"),
                                     "n": len(fl)}
                    log.info("zonas inundáveis: %d freguesias com área cartografada", len(fl))
        except Exception as e:  # noqa: BLE001
            log.warning("zonas inundáveis por freguesia falharam: %s", e)
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
                            "yield": m["gross_yield"], "g1y": m["price_growth_1y"], "g1yr": m.get("price_growth_1y_real"), "fc": m.get("fc_growth_12m"),
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
    try:
        s12 = municipal(frames.get("sales_price_12m"))
        names = dict(s12.drop_duplicates("dico")[["dico", "geoname"]].itertuples(index=False)) if s12 is not None else {}
    except Exception:  # noqa: BLE001
        names = {}
    imi_rates, imi_status = imi.ingest(cfg.get("imi"), data_dir, today, names)
    al_points, al_status = al.ingest(cfg.get("al"), data_dir, today)
    disc = discover.run(cfg.get("discover"), data_dir, cfg.get("ine"), today)
    osm_points, osm_status = osm.ingest(cfg.get("osm"), data_dir)
    flood_zones, flood_status = flood.ingest(cfg.get("flood"), data_dir)
    stale = freshness.check(frames, macro_frames, cfg)
    for r in stale:
        log.warning("série parada: %s %s — último período %s (há %d meses; normal até %d)", r["source"], r["key"],
                    r["last"], r["months"], r["limit"])
    try:   # estado de todas as fontes no branch `data` (os logs do GitHub nem sempre estão à mão)
        import json as _json
        (data_dir / "clean").mkdir(parents=True, exist_ok=True)
        (data_dir / "clean" / "sources_status.json").write_text(_json.dumps(
            {"date": today, "ine": ine_status, "macro": macro_status, "at": {"imi_rates": imi_status},
             "turismo": {"al_rnal": al_status}, "osm": {"osm_points": osm_status},
             "apa": {"flood_zones": flood_status}, "stale": stale, "discover": disc},
            ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("estado das fontes não gravado: %s", e)
    ine_summary = write_ine_status(ine_status, data_dir)

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
                         forecast_log=data_dir / "clean" / "forecast_log.parquet", parish_geojson=parish_gj,
                         ine_summary=ine_summary, imi_rates=imi_rates, imi_status=imi_status,
                         al_points=al_points, al_status=al_status, stale=stale,
                         osm_points=osm_points, osm_status=osm_status,
                         flood_zones=flood_zones, flood_status=flood_status)


def ine_live(status: dict) -> dict:
    """Resumo do contacto com o INE neste build: ao vivo se pelo menos um indicador veio do INE e nenhum da cache."""
    vals = [str(v) for k, v in status.items() if k != "geo" and not str(v).startswith("sem código")]
    n_ok = sum(v.startswith("ok") for v in vals)
    n_cache = sum(v.startswith("CACHE") for v in vals)
    return {"live": n_ok > 0 and n_cache == 0, "n_ok": n_ok, "n_cache": n_cache,
            "n_error": sum(v.startswith("ERRO") for v in vals)}


def write_ine_status(status: dict, data_dir: Path) -> dict:
    """data/clean/ine_status.json: o workflow só repete o build (tentativas extra) se o último não chegou ao INE.
    Guarda também a data do último build que chegou ao INE (para o site dizer de quando são os dados)."""
    import json as _json
    path = data_dir / "clean" / "ine_status.json"
    prev = {}
    try:
        prev = _json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    out = {"date": dt.date.today().isoformat(), **ine_live(status)}
    out["last_live"] = out["date"] if out["live"] else prev.get("last_live")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(out), encoding="utf-8")
    return out


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
