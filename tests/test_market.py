import json

import pandas as pd
import pytest

from imopt import demo, market, pipeline


def _monthly(dico, level, start_year, values):
    rows = []
    for i, v in enumerate(values):
        y, m = start_year + i // 12, i % 12 + 1
        rows.append(dict(dico=dico, level=level, period=f"{y}-{m:02d}", sort_key=y * 100 + m, value=v))
    return rows


def _quarterly(dico, level, start_year, values):
    rows = []
    for i, v in enumerate(values):
        y, q = start_year + i // 4, i % 4 + 1
        rows.append(dict(dico=dico, level=level, period=f"{y}Q{q}", sort_key=y * 100 + q, value=v))
    return rows


def test_valuation_gap_uses_same_12_month_window():
    sales, val = [], []
    for i in range(12):
        d = f"{i + 1:04d}"
        sales += _quarterly(d, "municipality", 2024, [1000.0] * 8)
        # avaliação constante a 900 em 2024 e, em 2025, 900 (concelho 0001) ou 950 (restantes)
        val += _monthly(d, "municipality", 2024, [900.0] * 12 + ([900.0] if i == 0 else [950.0]) * 12)
    s, per = market.valuation_gap(pd.DataFrame(sales), pd.DataFrame(val), {"0001": "Um"})
    assert s["period"] == "2025Q4" and s["prev_period"] == "2024Q4"
    assert per["0001"]["val_gap"] == pytest.approx(-0.10) and per["0001"]["val_gap_chg"] == pytest.approx(0.0)
    assert per["0002"]["val_gap"] == pytest.approx(-0.05) and per["0002"]["val_gap_chg"] == pytest.approx(0.05)
    assert s["lagging"][0]["dico"] == "0001" and s["lagging"][0]["name"] == "Um"
    # com volume, concelhos pequenos saem das listas (não dos números por concelho)
    vol = pd.Series({f"{i + 1:04d}": (5.0 if i == 0 else 50.0) for i in range(12)})
    s2, per2 = market.valuation_gap(pd.DataFrame(sales), pd.DataFrame(val), None, vol)
    assert all(x["dico"] != "0001" for x in s2["lagging"]) and "0001" in per2


def test_price_volume_cycle_phases_and_volume_floor():
    feats = pd.DataFrame({
        "dico": [f"{i:04d}" for i in range(12)], "name": [f"C{i}" for i in range(12)],
        "price_growth_1y": [0.1] * 6 + [-0.05] * 6,
        "val_count_growth_1y": [0.2, 0.2, 0.2, -0.3, -0.1, -0.2, -0.1, -0.1, 0.1, 0.1, 0.1, 0.1],
        "val_count": [100.0] * 11 + [5.0],
    })
    s, per = market.price_volume_cycle(feats)
    assert s["n"] == 11 and s["counts"] == {"up_up": 3, "up_down": 3, "down_down": 2, "down_up": 3}
    assert per["0003"]["cycle_phase"] == "up_down" and "0011" not in per
    assert [x["dico"] for x in s["late"]] == ["0003", "0005", "0004"]


def test_national_cycle_quarterly_yoy():
    val = pd.DataFrame(_monthly("PT", "national", 2023, [100.0] * 12 + [110.0] * 12))
    cnt = pd.DataFrame(_monthly("PT", "national", 2023, [300.0] * 12 + [240.0] * 12))
    nat = market.national_cycle(val, cnt)
    assert nat[0][0] == "2024Q1" and nat[0][1] == pytest.approx(0.10) and nat[0][2] == pytest.approx(-0.20)


def test_build_outputs_has_cycle_and_valuation_gap(tmp_path):
    frames, macro_frames = demo.demo_frames()
    pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path, None, demo=True)
    ol = json.loads((tmp_path / "outlook.json").read_text(encoding="utf-8"))
    assert "cycle" in ol and "val_gap" in ol, ol["errors"]
    m = json.loads((tmp_path / "municipalities.json").read_text(encoding="utf-8"))
    assert any("cycle_phase" in x for x in m) and any("val_gap" in x for x in m)


def test_credit_flow_rolling_sum_and_renegotiation_share():
    months = [f"{y}-{m:02d}" for y in (2023, 2024, 2025) for m in range(1, 13)]
    vol = pd.DataFrame({"period": months, "value": [100.0] * 24 + [120.0] * 12})
    pure = pd.DataFrame({"period": months, "value": [80.0] * 24 + [90.0] * 12})
    c = market.credit_flow(vol, pure)
    assert c["until"] == "2025-12" and c["last12"] == 1440.0 and c["change"] == pytest.approx(0.2)
    assert c["reneg_share"] == pytest.approx(1 - 1080 / 1440) and c["series"][-1] == ["2025-12", 1440.0]
    assert market.credit_flow(vol.head(10)) is None
