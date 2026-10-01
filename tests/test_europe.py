import pandas as pd
import pytest

from imopt import macro


def _js(times, geos, values, extra=("freq", "unit")):
    ids = list(extra) + ["geo", "time"]
    dims = {d: {"category": {"index": {"X": 0}}} for d in extra}
    dims["geo"] = {"category": {"index": {g: i for i, g in enumerate(geos)}}}
    dims["time"] = {"category": {"index": {t: i for i, t in enumerate(times)}}}
    return {"id": ids, "size": [1] * len(extra) + [len(geos), len(times)], "dimension": dims, "value": values}


def test_parse_jsonstat_panel_row_major_and_sparse():
    js = _js(["2024-Q1", "2024-Q2"], ["PT", "ES"], {"0": 100.0, "1": 101.0, "3": 99.0})
    df = macro.parse_jsonstat_panel(js)
    assert df.to_dict("records") == [
        {"geo": "PT", "period": "2024Q1", "value": 100.0}, {"geo": "PT", "period": "2024Q2", "value": 101.0},
        {"geo": "ES", "period": "2024Q2", "value": 99.0}]


def test_parse_jsonstat_panel_rejects_unfiltered():
    js = _js(["2024-Q1"], ["PT"], [1.0])
    js["size"][0] = 2
    with pytest.raises(ValueError):
        macro.parse_jsonstat_panel(js)


def _panel(rates, years=range(2014, 2026), infl=0.0):
    rows_h, rows_c = [], []
    for g, r in rates.items():
        for y in years:
            for q in range(1, 5):
                k = (y - 2015) + (q - 1) / 4
                rows_h.append((g, f"{y}Q{q}", 100 * (1 + r) ** k))
                rows_c.append((g, f"{y}Q{q}", 100 * (1 + infl) ** k))
    return pd.DataFrame(rows_h, columns=["geo", "period", "value"]), pd.DataFrame(rows_c, columns=["geo", "period", "value"])


def test_compare_ranks_portugal_and_deflates():
    from imopt import europe
    rates = {g: 0.01 * i for i, g in enumerate(["DE", "FR", "IT", "AT", "BE", "NL", "ES", "IE", "PL", "LT", "EE"])}
    rates["PT"] = 0.20
    h, c = _panel(rates, infl=0.02)
    e = europe.compare(h, c)
    assert e["period"] == "2025Q4" and e["rank"] == 1 and e["n"] == 12
    # 2015 = 100 nos dois índices: real = (1,2/1,02)^(anos) - 1, com a média de 2015 como base
    pt = e["pt"]
    assert pt["real_1y"] == pytest.approx(1.20 / 1.02 - 1, rel=1e-6) and pt["from_peak"] == pytest.approx(0.0)
    assert e["series"]["PT"][0][0] == "2014Q1" or e["series"]["PT"][0][0] >= "2010Q1"
    assert europe.compare(h[h["geo"] != "PT"], c) is None
