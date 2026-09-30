import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from imopt import demo, pipeline, tracking


def _outlook(origin="2026Q1", val="2026-08"):
    return {"sales": {"origin": origin, "last_valuation": val}}


def _per(mid=110.0):
    return {"0001": {"fc": {"periods": ["2026Q2", "2026Q3"], "mid": [mid, mid * 1.02], "lo50": [mid - 5, mid - 5],
                            "hi50": [mid + 5, mid + 5], "lo80": [mid - 10, mid - 10], "hi80": [mid + 10, mid + 10]}}}


FEATS = pd.DataFrame({"dico": ["0001"], "price": [100.0], "rent": [np.nan]})


def test_record_archives_each_vintage_once():
    a = tracking.record(tracking.load(None), _outlook(), _per(), FEATS, dt.date(2026, 9, 30))
    assert len(a) == 2 and set(a["h"]) == {1, 2} and a["last_actual"].iloc[0] == 100.0
    again = tracking.record(a, _outlook(), _per(mid=999), FEATS, dt.date(2026, 10, 7))
    assert len(again) == 2 and again["mid"].iloc[0] == 110.0          # a primeira emissão é a que conta
    newer = tracking.record(a, _outlook(val="2026-09"), _per(), FEATS, dt.date(2026, 10, 30))
    assert len(newer) == 4 and newer["vintage"].nunique() == 2


def test_evaluate_against_published_values():
    a = tracking.record(tracking.load(None), _outlook(), _per(), FEATS, dt.date(2026, 9, 30))
    sales = pd.DataFrame({"dico": ["0001"], "period": ["2026Q2"], "value": [116.0]})
    out, per = tracking.evaluate(a, sales, None)
    assert out["n_evaluated"] == 1 and out["n_pending"] == 1 and out["next_targets"] == ["2026Q3"]
    m = out["sales"][0]
    assert m["h"] == 1 and m["mae_model"] == pytest.approx(np.log(116 / 110))
    assert m["mae_naive"] == pytest.approx(np.log(116 / 100)) and m["skill"] > 0
    assert m["coverage80"] == 1.0 and m["coverage50"] == 0.0 and m["bias"] < 0
    assert per["0001"]["fc_past"][0] == pytest.approx({"target": "2026Q2", "issued": "2026-09-30", "h": 1, "mid": 110.0,
                                                       "lo80": 100.0, "hi80": 120.0, "actual": 116.0})


def test_evaluate_empty_archive():
    out, per = tracking.evaluate(tracking.load(None), None, None)
    assert out["n_archived"] == 0 and per == {}


def test_two_builds_evaluate_the_first_forecast(tmp_path):
    frames, macro_frames = demo.demo_frames()
    log_path = tmp_path / "clean" / "forecast_log.parquet"
    early = {k: v for k, v in frames.items()}
    early["sales_price_12m"] = frames["sales_price_12m"][frames["sales_price_12m"]["period"] != "2026Q2"]
    pipeline.build_outputs(early, macro_frames, {}, {}, tmp_path / "a", None, forecast_log=log_path)
    n1 = len(pd.read_parquet(log_path))
    pipeline.build_outputs(early, macro_frames, {}, {}, tmp_path / "a", None, forecast_log=log_path)
    assert len(pd.read_parquet(log_path)) == n1                       # mesmo conjunto de dados: sem duplicados
    pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path / "b", None, forecast_log=log_path)
    ol = json.loads((tmp_path / "b" / "outlook.json").read_text(encoding="utf-8"))
    t = ol["tracking"]
    assert t["n_vintages"] >= 2 and t["n_evaluated"] >= 48          # 2026Q2 previsto a 1 trimestre, para os 48 concelhos
    assert t["sales"][0]["h"] == 1 and t["sales"][0]["targets"] == ["2026Q2"]
    munis = json.loads((tmp_path / "b" / "municipalities.json").read_text(encoding="utf-8"))
    assert all(m["fc_past"][0]["target"] == "2026Q2" for m in munis)
