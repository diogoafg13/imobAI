import datetime as dt

import pandas as pd

from imopt import freshness


def test_period_end_and_stale_detection():
    assert freshness.period_end("2026-02") == (dt.date(2026, 2, 28), "month")
    assert freshness.period_end("2025Q4") == (dt.date(2025, 12, 31), "quarter")
    assert freshness.period_end("2024") == (dt.date(2024, 12, 31), "year")
    cfg = {"ine": {"indicators": {"a": {}, "b": {"max_age_months": 3}, "c": {"static": True}}},
           "macro": {"hicp": {}}}
    frames = {"a": pd.DataFrame({"period": ["2025T4"], "period_kind": ["quarter"], "sort_key": [202504], "value": [1.0]}),
              "b": pd.DataFrame({"period": ["2026-06"], "period_kind": ["month"], "sort_key": [202606], "value": [1.0]}),
              "c": pd.DataFrame({"period": ["2021"], "period_kind": ["year"], "sort_key": [202100], "value": [1.0]})}
    macro = {"hicp": pd.DataFrame({"period": ["2025Q4"], "value": [1.0]})}
    out = freshness.check(frames, macro, cfg, dt.date(2026, 10, 6))
    keys = {r["key"]: r for r in out}
    # 2025T4 acabou há 10 meses (> 9): parada; 2026-06 há 4 meses (> 3 do config): parada; Censos estáticos: não
    assert set(keys) == {"a", "b", "hicp"} and keys["a"]["months"] == 10 and keys["b"]["limit"] == 3
    assert freshness.check(frames, macro, cfg, dt.date(2026, 6, 1)) == []
