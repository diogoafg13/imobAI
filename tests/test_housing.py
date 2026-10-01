import json

import pandas as pd
import pytest

from imopt import demo, housing, pipeline


def _rows(dico, kind, keys, values, level="municipality"):
    return [dict(dico=dico, level=level, period_kind=kind, sort_key=k, period=str(k), value=v) for k, v in zip(keys, values)]


def test_to_annual_sums_complete_years_only():
    keys = [2024 * 100 + m for m in range(1, 13)] + [2025 * 100 + m for m in range(1, 7)]
    a = housing.to_annual(pd.DataFrame(_rows("0001", "month", keys, [1.0] * 18)), "sum")
    assert list(a["sort_key"]) == [202400] and float(a["value"].iloc[0]) == 12.0
    y = pd.DataFrame(_rows("0001", "year", [202400], [5.0]))
    assert housing.to_annual(y) is y


def test_context_features_census_beds_and_irs():
    census = lambda v: pd.DataFrame([dict(dico=None, level="other", geocod="1106", period_kind="year",
                                          sort_key=202100, period="2021", value=v)])  # noqa: E731
    frames = {
        "dwellings_stock": pd.DataFrame(_rows("0001", "year", [202100, 202200], [9000.0, 10000.0])),
        "tourism_beds": pd.DataFrame(_rows("0001", "year", [202500], [500.0])),
        "tourism_beds_al": pd.DataFrame(_rows("0001", "year", [202500], [100.0])),
        "irs_median": pd.DataFrame(_rows("0001", "year", [202300, 202400], [10000.0, 11000.0])),
    }
    for k, v in (("total", 1000.0), ("secondary", 100.0), ("vacant_market", 50.0), ("vacant_other", 70.0)):
        frames[f"census_{k}"] = pipeline.municipal(housing.dico4(census(v)))
    f = housing.context_features(frames).set_index("dico")
    assert f.at["0001", "beds_per_100"] == pytest.approx(5.0) and f.at["0001", "al_beds_per_100"] == pytest.approx(1.0)
    assert f.at["0001", "irs_year"] == 2024 and f.at["0001", "irs_growth_1y"] == pytest.approx(0.1)
    assert f.at["1106", "vacant_share"] == pytest.approx(0.12) and f.at["1106", "secondary_share"] == pytest.approx(0.1)
    assert f.at["1106", "vacant_market_share"] == pytest.approx(0.05) and f.at["1106", "census_year"] == 2021
    assert housing.context_features({}).empty


def test_supply_national_series_and_recent_change():
    keys = [y * 100 + m for y in (2023, 2024) for m in range(1, 13)] + [202501, 202502]
    lic = pd.DataFrame(_rows("PT", "month", keys, [100.0] * 12 + [110.0] * 12 + [120.0, 120.0], "national"))
    stock = pd.DataFrame(_rows("PT", "year", [202200], [5000000.0], "national"))
    s = housing.supply(lic, None, stock)
    assert s["series"]["licensed"] == [["2023", 1200.0, pytest.approx(0.24)], ["2024", 1320.0, pytest.approx(0.264)]]
    assert s["recent"]["licensed"]["until"] == "202502" and s["recent"]["licensed"]["last12"] == 1340.0
    assert housing.supply(None, None) is None


def test_affordability_history_payment_and_income_asof():
    months = [y * 100 + m for y in (2023, 2024, 2025) for m in range(1, 13)]
    val = pd.DataFrame(_rows("PT", "month", months, [2000.0] * 36, "national"))
    mort = pd.DataFrame({"period": [f"{k // 100}-{k % 100:02d}" for k in months], "value": [3.0] * 36})
    wages = pd.DataFrame(_rows("PT", "year", [202300], [1500.0], "national"))
    a = housing.affordability_history(val, mort, wages)
    loan, r = 2000 * 90 * 0.9, 0.03 / 12
    pay = loan * r / (1 - (1 + r) ** -360)
    assert a["last"]["payment"] == pytest.approx(pay)
    assert a["first"]["effort_wage"] == pytest.approx(pay / 1500) and a["first"]["wage_year"] == 2023
    # 2025 ainda usa o salário de 2023 (2 anos); a partir de 3 anos deixa de usar
    assert a["last"]["wage_year"] == 2023 and a["last"]["effort_irs"] is None


def test_build_outputs_supply_and_history(tmp_path):
    frames, macro_frames = demo.demo_frames()
    pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path, None, demo=True)
    ol = json.loads((tmp_path / "outlook.json").read_text(encoding="utf-8"))
    assert "supply" in ol and "afford_hist" in ol, ol["errors"]
    m = json.loads((tmp_path / "municipalities.json").read_text(encoding="utf-8"))[0]
    assert m["irs_median"] and m["vacant_share"] is not None and m["al_beds_per_100"] is not None
    assert ol["supply"]["series"]["licensed"] and ol["supply"]["recent"]["completed"]["change"] is not None
    assert m["guests_12m"] and m["guests_growth_1y"] == pytest.approx(0.04, abs=0.02) and m["guests_al_share"] == pytest.approx(0.3, abs=0.01)
    assert 0.3 <= m["occupancy"] <= 0.7 and "europe" in ol
    # contexto não mexe nos scores
    assert "score_supply" in m and m["score_supply"] is None


def test_typology_mix_shares_and_price_growth():
    def lic(vals):
        keys = [y * 100 + m for y in range(2019, 2026) for m in range(1, 13)]
        return pd.DataFrame(_rows("PT", "month", keys, [v for v in vals for _ in range(12)], "national"))
    by_type = {"t01": lic([1, 1, 1, 1, 1, 2, 2]), "t2": lic([1] * 7), "t3": lic([2] * 7), "t4": lic([1] * 7)}
    prices = {"t2": pd.DataFrame(_rows("PT", "quarter", [202501, 202502, 202503, 202504, 202601], [100, 1, 1, 1, 110.0], "national"))}
    m = housing.typology_mix(by_type, prices)
    assert m["year"] == 2025 and m["year_before"] == 2020
    r = {x["key"]: x for x in m["rows"]}
    assert r["t01"]["share_before"] == pytest.approx(0.2) and r["t01"]["share_now"] == pytest.approx(2 / 6)
    assert r["t2"]["price_growth_1y"] == pytest.approx(0.1) and r["t3"]["price_growth_1y"] is None
    assert housing.typology_mix({}, {}) is None


def test_score_parts_average_to_valuation_score():
    from imopt import scoring
    frames, _ = demo.demo_frames()
    f = scoring.municipal_features(pipeline.municipal(frames["sales_price_12m"]), pipeline.municipal(frames["rent_new_contracts"]))
    parts = f[["score_part_g1y", "score_part_g3y", "score_part_yield"]].mean(axis=1)
    assert (parts - f["score_valuation"]).abs().max() < 1e-9


def test_last12_needs_full_years():
    keys = [y * 100 + m for y in (2024, 2025) for m in range(1, 13)]
    df = pd.DataFrame(_rows("0001", "month", keys, [1.0] * 12 + [2.0] * 12))
    r = housing.last12(df).iloc[0]
    assert r["now"] == 24.0 and r["growth"] == pytest.approx(1.0) and r["until"] == "2025-12"
    assert pd.isna(housing.last12(df[df["sort_key"] >= 202403]).iloc[0]["growth"])


def test_construction_costs_vs_prices():
    keys = [y * 100 + m for y in (2021, 2022, 2023) for m in range(1, 13)]
    cost = pd.DataFrame(_rows("PT", "month", keys, [100.0] * 12 + [110.0] * 12 + [121.0] * 12, "national"))
    pq = [y * 100 + q for y in (2021, 2022, 2023) for q in range(1, 5)]
    new = pd.DataFrame(_rows("PT", "quarter", pq, [1000.0] * 4 + [1200.0] * 4 + [1500.0] * 4, "national"))
    k = housing.construction_costs({"total": cost}, new)
    assert k["until"] == "2023-12" and k["yoy"] == pytest.approx(0.1) and k["since_2021"] == pytest.approx(0.21)
    assert k["prices"]["new"]["yoy"] == pytest.approx(0.25) and k["prices"]["new"]["since_2021"] == pytest.approx(0.5)
    assert housing.construction_costs({}) is None


def test_history_export_for_property_analysis(tmp_path):
    frames, macro_frames = demo.demo_frames()
    pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path, None, demo=True)
    h = json.loads((tmp_path / "history.json").read_text(encoding="utf-8"))
    assert h["parish"] and all(len(v) > 4 for v in h["parish"].values())
    assert set(h["val"]) >= {"apt", "house", "all"} and h["hicp"]
    # mediana de venda por tipologia e de casas existentes, por concelho (para o valor de casas grandes/pequenas)
    assert set(h["typ"]) == {"t01", "t2", "t3", "t4"} and all(len(k) == 4 for k in h["typ"]["t4"]) and h["exist"]
    code, ser = next(iter(h["parish"].items()))
    assert len(code) == 6 and ser[0][0] <= ser[-1][0]
