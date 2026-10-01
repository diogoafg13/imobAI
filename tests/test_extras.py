import json

import numpy as np
import pandas as pd
import pytest

from imopt import demo, ine, outlook, pipeline, scoring


def _q(d, p, v):
    y, q = p.split("Q")
    return dict(dico=d, period=p, sort_key=int(y) * 100 + int(q), value=v, level="municipality")


def _m(d, y, mth, v):
    return dict(dico=d, period=f"{y}-{mth:02d}", sort_key=y * 100 + mth, value=v, level="municipality")


def _y(d, y, v):
    return dict(dico=d, period=str(y), sort_key=y * 100, value=v, level="municipality")


def test_extra_features_premium_valuation_growth_and_rent_spread():
    frames = {
        "sales_price_new": pd.DataFrame([_q("0001", "2026Q1", 3000.0)]),
        "sales_price_existing": pd.DataFrame([_q("0001", "2026Q1", 2400.0), _q("0002", "2026Q1", 1000.0)]),
        "valuation_apartments": pd.DataFrame([_m("0001", 2025, m, 100.0) for m in (6, 7, 8)] +
                                             [_m("0001", 2026, m, 110.0) for m in (6, 7, 8)]),
        "rent_q1": pd.DataFrame([_y("0001", 2025, 8.0)]),
        "rent_q3": pd.DataFrame([_y("0001", 2025, 12.0)]),
        "rent_contracts": pd.DataFrame([_y("0001", 2023, 100.0), _y("0001", 2024, 150.0)]),
    }
    x = scoring.extra_features(frames).set_index("dico")
    assert x.at["0001", "new_premium"] == pytest.approx(0.25)
    assert pd.isna(x.at["0002", "price_new"]) and x.at["0002", "price_existing"] == 1000.0
    assert x.at["0001", "val_apt"] == pytest.approx(110.0) and x.at["0001", "val_apt_growth_1y"] == pytest.approx(0.10)
    assert x.at["0001", "rent_spread"] == pytest.approx(1.5)
    assert x.at["0001", "rent_contracts_growth"] == pytest.approx(0.5) and x.at["0001", "rent_contracts_year"] == 2024
    assert scoring.extra_features({}).empty


def test_foreign_premium_tipologia_and_volume():
    frames = {
        "sales_price_domestic": pd.DataFrame([_q("0001", "2026Q1", 2000.0)]),
        "sales_price_foreign": pd.DataFrame([_q("0001", "2026Q1", 3000.0)]),
        "sales_price_t2": pd.DataFrame([_q("0001", "2026Q1", 2100.0)]),
        "valuation_count": pd.DataFrame([_m("0001", 2025, 8, 80.0), _m("0001", 2026, 8, 60.0)]),
    }
    x = scoring.extra_features(frames).set_index("dico")
    assert x.at["0001", "foreign_premium"] == pytest.approx(0.5) and x.at["0001", "price_t2"] == 2100.0
    assert x.at["0001", "val_count"] == 60.0 and x.at["0001", "val_count_growth_1y"] == pytest.approx(-0.25)
    d = outlook.demand(x.reset_index().assign(name="A"))
    assert d is None                                           # menos de 5 concelhos: sem resumo nacional
    many = pd.concat([x.reset_index().assign(dico=f"{i:04d}", name=f"C{i}") for i in range(6)])
    d = outlook.demand(many)
    assert d["foreign"]["median_premium"] == pytest.approx(0.5) and d["volume"]["total_growth_1y"] == pytest.approx(-0.25)
    assert d["volume"]["share_falling"] == 1.0 and len(d["foreign"]["top"]) == 6


def test_same_indicator_other_category_is_fetched_once(monkeypatch, tmp_path):
    calls = []
    payload = [{"Dados": {"2026T1": [
        {"geocod": "1701106", "geodsg": "Lisboa", "valor": "5000", "dim_3": "H1", "dim_3_t": "Total"},
        {"geocod": "1701106", "geodsg": "Lisboa", "valor": "6000", "dim_3": "H11", "dim_3_t": "Novos"}]}}]
    monkeypatch.setattr(ine, "fetch", lambda *a, **k: calls.append(a[1]) or payload)
    cfg = {"ine": {"base_url": "x", "indicators": {
        "sales_price_12m": {"varcd": "0012234", "dims": {"dim_3": "H1"}},
        "sales_price_new": {"varcd": "0012234", "dims": {"dim_3": "H11"}, "optional": True}}}}
    frames, status = pipeline.ingest_ine(cfg, tmp_path, "20261001")
    assert calls == ["0012234"]
    assert frames["sales_price_12m"]["value"].iloc[0] == 5000 and frames["sales_price_new"]["value"].iloc[0] == 6000


def test_rate_scenarios_use_observed_spread_only_when_sane():
    months = [f"{y}-{m:02d}" for y in range(2024, 2027) for m in range(1, 13)][:-4]
    eur = pd.DataFrame({"period": months, "value": 2.0})
    ok = outlook.rate_scenarios(eur, None, mortgage=pd.DataFrame({"period": months, "value": 3.2}))
    assert ok["spread"] == pytest.approx(1.2) and ok["spread_source"].startswith("BCE") and ok["rate_now"] == pytest.approx(3.2)
    odd = outlook.rate_scenarios(eur, None, mortgage=pd.DataFrame({"period": months, "value": 12.0}))
    assert odd["spread"] == outlook.MORTGAGE_SPREAD and odd["spread_source"] == "assumed"


def test_monthly_to_quarterly_needs_two_months():
    df = pd.DataFrame([_m("0001", 2026, 7, 100.0), _m("0001", 2026, 8, 110.0), _m("0001", 2026, 4, 90.0)])
    q = outlook.monthly_to_quarterly_muni(df)
    assert q["period"].tolist() == ["2026Q3"] and q["value"].iloc[0] == pytest.approx(105.0)


def test_build_outputs_has_type_forecasts_and_context(tmp_path):
    frames, macro_frames = demo.demo_frames()
    pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path, demo.demo_geojson(), demo=True)
    ol = json.loads((tmp_path / "outlook.json").read_text(encoding="utf-8"))
    assert {"fc_apt", "fc_house"} <= set(ol) and ol["fc_apt"]["backtest"]
    assert "log_tourism" in {e["feature"] for e in ol["fair_value"]["effects"]}
    munis = {m["dico"]: m for m in json.loads((tmp_path / "municipalities.json").read_text(encoding="utf-8"))}
    m = munis["0002"]
    assert m["apt_fc_growth_12m"] is not None and m["new_premium"] == pytest.approx(1.25 / 0.95 - 1, abs=1e-3)
    assert m["tourism_pc"] > 0 and m["rent_spread"] == pytest.approx(1.3 / 0.75, abs=1e-3)
    assert "house_fc_growth_12m" not in munis["0003"]          # sem dados de moradias neste concelho sintético
    assert munis["0004"]["foreign_premium"] == pytest.approx(1.4 / 0.97 - 1, abs=1e-3) and munis["0003"]["foreign_premium"] is None
    assert {"foreign", "volume"} <= set(ol["demand"])
