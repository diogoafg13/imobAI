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
