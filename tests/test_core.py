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
