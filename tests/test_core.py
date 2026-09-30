import pandas as pd
import pytest

from imopt import geo, ine, scoring


def test_parse_period_variants():
    assert ine.parse_period("2019 - 4.º Trimestre").label == "2019Q4"
    assert ine.parse_period("2024T2").label == "2024Q2"
    assert ine.parse_period("Março de 2021").label == "2021-03"
    assert ine.parse_period("2015").kind == "year"
    with pytest.raises(ValueError):
        ine.parse_period("sem ano")


def test_parse_response_and_levels():
    payload = [{"IndicadorCod": "X", "Dados": {
        "2024Q1": [{"geocod": "1701106", "geodsg": "Lisboa", "valor": "4 800,5", "dim_2": "T", "dim_2_t": "Total"},
                   {"geocod": "PT", "geodsg": "Portugal", "valor": "2100.0"}],
        "2024Q2": [{"geocod": "1701106", "geodsg": "Lisboa", "valor": "x", "dim_2": "T"}]}}]
    df = ine.parse_response(payload, "X")
    lis = df[(df.geocod == "1701106") & (df.period == "2024Q1")].iloc[0]
    assert lis.value == 4800.5 and lis.dico == "1106" and lis.level == "municipality"
    assert df[df.geocod == "PT"].iloc[0].level == "national"
    assert pd.isna(df[df.period == "2024Q2"].value.iloc[0])


def test_missing_dados_raises():
    with pytest.raises(ValueError):
        ine.parse_response([{"Erro": "x"}], "X")


def test_ambiguous_dimensions_fail_loudly():
    payload = [{"Dados": {"2024": [
        {"geocod": "1701106", "valor": "1", "dim_2": "Q1"}, {"geocod": "1701106", "valor": "2", "dim_2": "Q2"}]}}]
    df = ine.parse_response(payload, "X")
    with pytest.raises(ine.AmbiguousDimensionError):
        ine.apply_dim_filters(df, None, "X")
    assert len(ine.apply_dim_filters(df, {"dim_2": "Q2"}, "X")) == 1
    with pytest.raises(KeyError):
        ine.apply_dim_filters(df, {"dim_9": "1"}, "X")


def _muni(dico, name, vals, kind_keys):
    return pd.DataFrame({"dico": dico, "geoname": name, "sort_key": kind_keys, "value": vals,
                         "period": [str(k) for k in kind_keys]})


def test_shift_key():
    assert scoring._shift_key(202601, "quarter", 4) == 202501
    assert scoring._shift_key(202602, "quarter", 3) == 202503  # 2026Q2 - 3 trimestres = 2025Q3
    assert scoring._shift_key(202600, "year", 1) == 202500
    assert scoring._shift_key(202601, "month", 1) == 202512


def test_municipal_features_growth_yield_and_ranking():
    qs = [202501, 202502, 202503, 202504, 202601]
    a = _muni("0001", "A", [100, 100, 100, 100, 110], qs)       # +10% a 1 ano
    b = _muni("0002", "B", [100, 100, 100, 100, 101], qs)       # +1%
    sales = pd.concat([a, b])
    rent = pd.concat([_muni("0001", "A", [0.4, 0.5], [202500, 202600]),   # yield = 0.5*12/110
                      _muni("0002", "B", [0.6, 0.7], [202500, 202600])])   # yield = 0.7*12/101
    f = scoring.municipal_features(sales, rent).set_index("dico")
    assert f.loc["0001", "price_growth_1y"] == pytest.approx(0.10)
    assert f.loc["0001", "gross_yield"] == pytest.approx(0.5 * 12 / 110)
    assert f.loc["0002", "gross_yield"] > f.loc["0001", "gross_yield"]
    assert f.loc["0001", "score_overall"] > f.loc["0002", "score_overall"]
    assert f.loc["0001", "band"] in {"amber", "red"}


def test_features_without_rent_still_work():
    qs = [202501, 202502, 202503, 202504, 202601]
    sales = pd.concat([_muni("0001", "A", [1, 1, 1, 1, 1.2], qs), _muni("0002", "B", [1, 1, 1, 1, 1.0], qs)])
    f = scoring.municipal_features(sales, None).set_index("dico")
    assert f.loc["0001", "score_overall"] > f.loc["0002", "score_overall"]


def test_municipal_features_income_ratio_and_graceful_absence():
    qs = [202501, 202502, 202503, 202504, 202601]
    sales = pd.concat([_muni("0001", "A", [1000, 1000, 1000, 1000, 1100], qs),
                       _muni("0002", "B", [1000, 1000, 1000, 1000, 1000], qs)])
    income = pd.concat([_muni("0001", "A", [1000.0], [202600]), _muni("0002", "B", [1100.0], [202600])])
    f = scoring.municipal_features(sales, None, income=income).set_index("dico")
    assert f.loc["0001", "income"] == pytest.approx(1000.0)
    assert f.loc["0001", "price_to_income_months"] == pytest.approx(1100 / 1000)
    assert f.loc["0002", "price_to_income_months"] == pytest.approx(1000 / 1100)
    # sem dados de rendimento, continua a funcionar (degrada com NaN, não crasha)
    f2 = scoring.municipal_features(sales, None).set_index("dico")
    assert pd.isna(f2.loc["0001", "price_to_income_months"])
    assert pd.isna(f.loc["0001", "gross_yield"])


def test_national_scores_direction():
    idx = [f"{y}Q{q}" for y in range(2010, 2026) for q in range(1, 5)]
    calm = pd.DataFrame({"period": idx, "value": [100 * 1.005 ** i for i in range(len(idx))]})
    hot = calm.copy()
    hot.loc[hot.index[-6:], "value"] *= [1.02, 1.05, 1.09, 1.14, 1.2, 1.28]
    s_calm = scoring.national_scores(calm, None, None)
    s_hot = scoring.national_scores(hot, None, None)
    assert s_hot["overall"] > s_calm["overall"]
    assert scoring.national_scores(None, None, None)["overall"] is None


def test_geo_attach_and_slim():
    gj = {"features": [
        {"properties": {"DICO": "1106"}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
        {"properties": {"municipality": "São João da Madeira"}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
        {"properties": {"municipality": "Desconhecido"}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}]}
    out, unmatched = geo.attach_dico(gj, ["dico"], ["municipality"], {geo.norm_name("Sao Joao da Madeira"): "1309"})
    assert [f["properties"].get("dico") for f in out["features"]] == ["1106", "1309", None]
    assert unmatched == ["Desconhecido"]
    slim = geo.slim_geojson(out, {"1106": {"band": "red"}})
    assert len(slim["features"]) == 2 and slim["features"][0]["properties"]["band"] == "red"


def test_ambiguity_error_lists_labels_and_dim_labels():
    payload = [{"Dados": {"2024": [
        {"geocod": "1701106", "valor": "1", "dim_3": "H1", "dim_3_t": "Total"},
        {"geocod": "1701106", "valor": "2", "dim_3": "H11", "dim_3_t": "Apartamento"}]}}]
    df = ine.parse_response(payload, "X")
    with pytest.raises(ine.AmbiguousDimensionError, match="Apartamento"):
        ine.apply_dim_filters(df, None, "X")
    assert ine.dim_labels(df, {"dim_3": "H11"}) == "dim_3=H11 'Apartamento'"


def test_ingest_falls_back_to_cached_snapshot(tmp_path, monkeypatch):
    from imopt import pipeline
    clean = tmp_path / "clean"
    clean.mkdir()
    pd.DataFrame({"dico": ["1106"], "value": [1.0]}).to_parquet(clean / "ine_sales_price_12m.parquet")
    cfg = {"ine": {"base_url": "http://x", "lang": "PT",
                   "indicators": {"sales_price_12m": {"varcd": "0012234"}}}}

    def boom(*a, **k):
        raise RuntimeError("timeout")
    monkeypatch.setattr(pipeline.ine, "fetch", boom)
    frames, status = pipeline.ingest_ine(cfg, tmp_path, "20260930")
    assert "sales_price_12m" in frames and status["sales_price_12m"].startswith("CACHE")
    # sem cache, o indicador obrigatório continua a falhar alto
    (clean / "ine_sales_price_12m.parquet").unlink()
    with pytest.raises(RuntimeError):
        pipeline.ingest_ine(cfg, tmp_path, "20260930")


def test_ine_auto_mode_stops_after_first_failure(tmp_path, monkeypatch):
    from imopt import pipeline
    clean = tmp_path / "clean"
    clean.mkdir()
    for k in ("a", "b"):
        pd.DataFrame({"dico": ["1"], "value": [1.0]}).to_parquet(clean / f"ine_{k}.parquet")
    cfg = {"ine": {"base_url": "http://x", "indicators": {
        "a": {"varcd": "1", "optional": True}, "b": {"varcd": "2", "optional": True}}}}
    calls = []

    def boom(*args, **kw):
        calls.append(kw)
        raise RuntimeError("connect timeout")
    monkeypatch.setattr(pipeline.ine, "fetch", boom)
    monkeypatch.setenv("IMOPT_INE_MODE", "auto")
    frames, status = pipeline.ingest_ine(cfg, tmp_path, "d")
    assert len(calls) == 1 and calls[0]["retries"] == 1      # só tenta uma vez, rápido
    assert status["a"].startswith("CACHE") and status["b"].startswith("CACHE")
    calls.clear()
    monkeypatch.setenv("IMOPT_INE_MODE", "cache")
    pipeline.ingest_ine(cfg, tmp_path, "d")
    assert calls == []                                        # nunca toca na rede


def test_geocod_with_letters_in_nuts3_is_municipality():
    assert ine.classify_level("11A1312") == "municipality"      # Porto (AMP)
    assert ine.dico_from_geocod("11A1312") == "1312"
    assert ine.classify_level("1701106") == "municipality"      # Lisboa
    assert ine.dico_from_geocod("1701106") == "1106"
    assert ine.classify_level("16B1004") == "municipality"
    assert ine.classify_level("11A") == "nuts3" and ine.classify_level("150") == "nuts3"
    assert ine.classify_level("PT") == "national" and ine.classify_level("11") == "nuts2"
    assert ine.dico_from_geocod("11A") is None


def test_volatile_municipality_is_flagged_and_shrunk():
    import numpy as np
    qs = [y * 100 + q for y in range(2022, 2027) for q in range(1, 5)][:17]
    rows = []
    for i in range(12):                       # 11 estáveis com crescimento crescente, 1 muito volátil
        d = f"{i + 1:04d}"
        if i == 11:
            vals = [100 * (1.8 if k % 2 else 0.6) for k in range(len(qs))]
            vals[-1] = vals[-5] * 2.5          # +150% a 1 ano
        else:
            vals = [100 * (1 + 0.005 * (i + 1)) ** k for k in range(len(qs))]
        rows.append(pd.DataFrame({"dico": d, "geoname": d, "sort_key": qs, "value": vals, "period": [str(k) for k in qs]}))
    f = scoring.municipal_features(pd.concat(rows), None).set_index("dico")
    assert bool(f.loc["0012", "volatile"]) and f["volatile"].sum() >= 1
    assert abs(f.loc["0012", "score_overall"] - 50) <= 25 + 1e-9    # atenuado: no máximo 50 ± 25


def test_build_outputs_exports_all_euribor_series(tmp_path):
    import json
    from imopt import demo, pipeline
    frames, macro_frames = demo.demo_frames()
    pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path, None, demo=True)
    nat = json.loads((tmp_path / "national.json").read_text(encoding="utf-8"))
    for k in ("euribor_3m", "euribor_6m", "euribor_12m"):
        assert len(nat["series"][k]) > 100, k
    # o score nacional continua a usar só a variação da 12M
    assert "euribor_change_12m" in nat["components"]


def test_monthly_to_quarterly_only_complete_quarters():
    from imopt import macro
    df = pd.DataFrame({"period": ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05"],
                       "value": [100.0, 101.0, 102.0, 110.0, 111.0]})
    q = macro.monthly_to_quarterly(df)
    assert list(q["period"]) == ["2024Q1"] and q["value"].iloc[0] == pytest.approx(101.0)


def test_real_index_deflates_and_rebases_2015():
    from imopt import pipeline
    per = [f"{y}Q{q}" for y in (2015, 2016) for q in range(1, 5)]
    nominal = pd.DataFrame({"period": per, "value": [100.0] * 4 + [110.0] * 4})
    hicp = pd.DataFrame({"period": per, "value": [100.0] * 4 + [105.0] * 4})
    real = pipeline.real_index(nominal, hicp).set_index("period")["value"]
    assert real["2015Q3"] == pytest.approx(100.0)
    assert real["2016Q1"] == pytest.approx(110 / 105 * 100)
    assert pipeline.real_index(nominal, None) is None


def test_build_outputs_exports_real_hpi(tmp_path):
    import json
    from imopt import demo, pipeline
    frames, macro_frames = demo.demo_frames()
    pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path, None, demo=True)
    nat = json.loads((tmp_path / "national.json").read_text(encoding="utf-8"))
    assert len(nat["series"]["hpi_real"]) > 50
