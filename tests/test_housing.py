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


def test_context_features_rates_per_dwelling():
    years = [y * 100 for y in range(2019, 2025)]
    frames = {
        "dwellings_licensed": pd.DataFrame(_rows("0001", "year", years, [10, 10, 10, 20, 20, 20])),
        "dwellings_stock": pd.DataFrame(_rows("0001", "year", [202400], [10000.0])),
        "tourism_beds": pd.DataFrame(_rows("0001", "year", [202400], [500.0])),
        "irs_median": pd.DataFrame(_rows("0001", "year", [202300, 202400], [10000.0, 11000.0])),
    }
    f = housing.context_features(frames).set_index("dico")
    assert f.at["0001", "lic_avg3"] == 20 and f.at["0001", "lic_per_1000"] == pytest.approx(2.0)
    assert f.at["0001", "lic_growth_3y"] == pytest.approx(1.0) and f.at["0001", "beds_per_100"] == pytest.approx(5.0)
    assert f.at["0001", "irs_year"] == 2024 and f.at["0001", "irs_growth_1y"] == pytest.approx(0.1)
    assert housing.context_features({}).empty


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
    assert m["irs_median"] and m["lic_per_1000"] and m["beds_per_100"] is not None
    # contexto não mexe nos scores
    assert "score_supply" in m and m["score_supply"] is None
