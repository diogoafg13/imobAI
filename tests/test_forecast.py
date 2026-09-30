import datetime as dt

import numpy as np
import pandas as pd
import pytest

from imopt import forecast as fc

TODAY = dt.date(2026, 9, 30)


def _quarters(n, start=(2019, 4)):
    y, q = start
    out = []
    for _ in range(n):
        out.append((y, q))
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


def _synthetic(n=60, nq=26, seed=0, lead=True):
    """Preços com inércia e um ciclo comum; a avaliação bancária antecipa o preço em 1 trimestre."""
    rng = np.random.default_rng(seed)
    qs = _quarters(nq + 3)
    common = 0.02 + 0.015 * np.sin(np.arange(len(qs)) / 3)
    sales, val = [], []
    for i in range(n):
        d = f"{i + 1:04d}"
        g, lv = 0.0, np.log(rng.uniform(800, 3000))
        path = []
        for t in range(len(qs)):
            g = 0.6 * g + 0.4 * common[t] + rng.normal(0, 0.01)
            lv += g
            path.append(lv)
        for t, (y, q) in enumerate(qs[:nq]):
            sales.append(dict(dico=d, sort_key=y * 100 + q, period=f"{y}Q{q}", value=float(np.exp(path[t])), level="municipality"))
        for t, (y, q) in enumerate(qs):
            src = path[min(t + 1, len(path) - 1)] if lead else path[t]
            for m in range(3):
                month = (q - 1) * 3 + m + 1
                if y * 100 + month > 202608:
                    continue
                val.append(dict(dico=d, sort_key=y * 100 + month, period=f"{y}-{month:02d}",
                                value=float(np.exp(src + rng.normal(0, 0.005))), level="municipality"))
    v = pd.DataFrame(val)
    nat = v.groupby(["sort_key", "period"], as_index=False)["value"].median().assign(dico="PT", level="national")
    return pd.DataFrame(sales), pd.concat([v, nat], ignore_index=True)


def _capture(monkeypatch):
    box = {}
    orig = fc._sales_metrics

    def spy(res, horizons, min_origins=3):
        box["res"] = res.copy()
        return orig(res, horizons, min_origins)
    monkeypatch.setattr(fc, "_sales_metrics", spy)
    return box


def test_ridge_recovers_coefficients_and_never_extrapolates():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(800, 3))
    y = 1 + x @ np.array([0.5, -0.2, 0.0]) + rng.normal(0, 0.01, 800)
    m = fc.ridge_fit(x, y, lam=1e-6)
    assert fc.ridge_predict(m, np.array([[1.0, 1.0, 0.0]]))[0] == pytest.approx(1.3, abs=0.01)
    far = fc.ridge_predict(m, np.array([[100.0, 0.0, 0.0]]))[0]
    edge = fc.ridge_predict(m, np.array([[x[:, 0].max(), 0.0, 0.0]]))[0]
    assert far == pytest.approx(edge)          # fora do intervalo do treino: limitado, não extrapolado


def test_sales_forecast_beats_naive_when_valuation_leads(monkeypatch):
    sales, val = _synthetic()
    summary, per = fc.forecast_sales(sales, val, today=TODAY)
    m1 = summary["backtest"]["1"]
    assert m1["skill"] > 0.1
    assert 0.6 <= m1["coverage80"] <= 0.97
    assert summary["h_now"] == 2 and summary["nowcast_period"] == "2026Q3" and summary["target_period"] == "2027Q3"
    d = per["0001"]
    assert d["fc_lo80"] < d["fc_price"] < d["fc_hi80"]
    assert [k for k in d["fc"]["kind"]] == ["nowcast", "nowcast", "forecast", "forecast", "forecast", "forecast"]


def test_sales_backtest_has_no_lookahead(monkeypatch):
    sales, val = _synthetic(n=40)
    box = _capture(monkeypatch)
    fc.forecast_sales(sales, val, today=TODAY)
    res = box["res"]
    q0 = sorted(res["origin"].unique())[3]
    lead = 5                                        # avaliação até 2026-08 vs vendas até 2026Q1
    cut_month = fc.q_end_month(q0) + lead
    rng = np.random.default_rng(9)
    s2, v2 = sales.copy(), val.copy()
    fut_s = s2["sort_key"].map(fc.q_index) > q0
    s2.loc[fut_s, "value"] *= rng.uniform(0.5, 1.5, fut_s.sum())
    fut_v = v2["sort_key"].map(fc.m_index) > cut_month
    v2.loc[fut_v, "value"] *= rng.uniform(0.5, 1.5, fut_v.sum())
    box2 = _capture(monkeypatch)
    fc.forecast_sales(s2, v2, today=TODAY)
    def preds(r, q):
        return r[r["origin"] == q].sort_values(["h", "dico"])["pred"].to_numpy()
    a, b = preds(res, q0), preds(box2["res"], q0)
    assert len(a) > 0 and np.allclose(a, b)
    q_late = res["origin"].max()                    # controlo: a perturbação muda origens posteriores
    assert not np.allclose(preds(res, q_late), preds(box2["res"], q_late))


def test_intervals_widen_with_common_shocks():
    rng = np.random.default_rng(2)
    u, sig = rng.normal(size=500), np.full(10, 0.05)
    narrow = fc.interval_quantiles(np.zeros(5), u, sig)
    wide = fc.interval_quantiles(np.full(5, 0.2), u, sig)
    assert (wide["hi80"] - wide["lo80"]).min() > (narrow["hi80"] - narrow["lo80"]).max()


def test_common_idio_splits_origin_mean():
    r = pd.DataFrame({"origin": [1, 1, 2, 2], "y": [0.1, 0.3, 0.0, 0.0], "pred": [0.0, 0.0, 0.0, 0.0], "sigma": [0.1] * 4})
    c, u = fc.common_idio(r)
    assert c.tolist() == pytest.approx([0.2, 0.0])
    assert u.tolist() == pytest.approx([-1.0, 1.0, 0.0, 0.0])


def test_sales_forecast_degrades_without_valuation():
    sales, _ = _synthetic(n=30)
    summary, per = fc.forecast_sales(sales, today=TODAY)
    assert summary is not None and per
    assert not {"v_lead", "v_mom", "nat_lead", "eur_chg"} & set(summary["features"])
    assert fc.forecast_sales(sales.iloc[:0], today=TODAY) == (None, {})


def test_rent_forecast_one_year_with_interval():
    rng = np.random.default_rng(3)
    sales, val = _synthetic(n=50)
    rows = []
    for i in range(50):
        d, lr, g = f"{i + 1:04d}", np.log(rng.uniform(5, 15)), 0.05
        for y in range(2020, 2026):
            g = 0.03 + 0.5 * (g - 0.03) + rng.normal(0, 0.01)
            lr += g
            rows.append(dict(dico=d, sort_key=y * 100, period=str(y), value=float(np.exp(lr)), level="municipality"))
    summary, per = fc.forecast_rent(pd.DataFrame(rows), sales, val, today=TODAY)
    assert summary["target_year"] == "2026" and summary["target_in_progress"]
    assert summary["backtest"]["n_origins"] >= 2
    d = per["0001"]
    assert d["rent_fc_lo80"] < d["rent_fc"] < d["rent_fc_hi80"] and d["rent_fc_year"] == "2026"
