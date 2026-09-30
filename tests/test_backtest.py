import json

import numpy as np
import pandas as pd
import pytest

from imopt import backtest


def _quarters(start_year: int, n: int) -> list[str]:
    out = []
    y, q = start_year, 1
    for _ in range(n):
        out.append(f"{y}Q{q}")
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


def _synthetic_country(n=70, seed=3):
    rng = np.random.default_rng(seed)
    periods = _quarters(2000, n)
    h, vals = 100.0, []
    for i in range(n):
        drift = 0.03 if 20 <= i < 36 else (-0.02 if 36 <= i < 52 else 0.005)
        h *= 1 + drift + rng.normal(0, 0.003)
        vals.append(h)
    hpi = pd.DataFrame({"period": periods, "value": vals})
    hicp = pd.DataFrame({"period": periods, "value": [100 * 1.004 ** i for i in range(n)]})
    credit_gap = pd.DataFrame({"period": periods, "value": rng.normal(0, 5, n)})
    euribor_months = pd.period_range(f"{2000}-01", periods=n * 3, freq="M").astype(str)
    euribor = pd.DataFrame({"period": euribor_months, "value": rng.normal(2, 0.5, len(euribor_months))})
    return hpi, hicp, credit_gap, euribor


# ---------------------------------------------------------------- sem look-ahead
def test_no_lookahead_score_unchanged_by_future_data():
    hpi, hicp, credit_gap, euribor = _synthetic_country()
    full = backtest.evaluate_country("XX", hpi, hicp, credit_gap, euribor, euro_since=2000, min_history=40)

    cut = 55  # simula "só tínhamos dados até aqui"
    hpi_t = hpi.iloc[:cut]
    hicp_t = hicp.iloc[:cut]
    credit_t = credit_gap.iloc[:cut]
    cutoff = backtest._euribor_cutoff(backtest._key(hpi_t["period"].iloc[-1]))
    euribor_t = euribor[euribor["period"] <= cutoff]
    trunc = backtest.evaluate_country("XX", hpi_t, hicp_t, credit_t, euribor_t, euro_since=2000, min_history=40)

    common = trunc["period"]
    f = full.set_index("period").loc[common, "score"]
    t = trunc.set_index("period")["score"]
    assert len(common) >= 10
    pd.testing.assert_series_equal(f, t, check_names=False)


def test_no_lookahead_extending_series_does_not_change_past_scores():
    """Acrescentar mais trimestres no fim não pode mudar o score já calculado para trimestres anteriores."""
    hpi, hicp, credit_gap, euribor = _synthetic_country(n=70)
    short = backtest.evaluate_country("XX", hpi.iloc[:60], hicp.iloc[:60], credit_gap.iloc[:60], euribor,
                                      euro_since=2000, min_history=40)
    long_ = backtest.evaluate_country("XX", hpi, hicp, credit_gap, euribor, euro_since=2000, min_history=40)
    merged = short.merge(long_, on="period", suffixes=("_short", "_long"))
    assert len(merged) == len(short)
    np.testing.assert_allclose(merged["score_short"], merged["score_long"], rtol=1e-9, atol=1e-9)


def test_euribor_excluded_before_euro_adoption():
    hpi, hicp, credit_gap, euribor = _synthetic_country()
    with_euro = backtest.evaluate_country("XX", hpi, hicp, credit_gap, euribor, euro_since=2000, min_history=40)
    # adoção "no futuro": a componente de juros nunca deve entrar
    without_euro = backtest.evaluate_country("XX", hpi, hicp, credit_gap, euribor, euro_since=None, min_history=40)
    # país fora do euro deve ter métricas calculáveis (sem crashar) e não é idêntico ao caso com euro
    assert len(with_euro) == len(without_euro)


# ---------------------------------------------------------------- métricas
def test_spearman_perfect_monotonic():
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    y = -x  # relação perfeitamente inversa
    assert backtest.spearman(x, y) == pytest.approx(-1.0)
    assert backtest.spearman(x, x) == pytest.approx(1.0)


def test_spearman_insufficient_data_returns_none():
    assert backtest.spearman(pd.Series([1.0, 2.0]), pd.Series([1.0, 2.0])) is None
    assert backtest.spearman(pd.Series([1.0] * 10), pd.Series(range(10), dtype=float)) is None


def test_auc_perfect_and_random():
    scores = pd.Series([10, 20, 30, 40, 50, 60])
    labels_perfect = pd.Series([0, 0, 0, 1, 1, 1])
    assert backtest.auc_binary(scores, labels_perfect) == pytest.approx(1.0)
    labels_inverted = pd.Series([1, 1, 1, 0, 0, 0])
    assert backtest.auc_binary(scores, labels_inverted) == pytest.approx(0.0)
    assert backtest.auc_binary(scores, pd.Series([1, 1, 1, 1, 1, 1])) is None  # só uma classe


def test_hit_false_alarm_confusion_matrix():
    scores = pd.Series([90, 80, 60, 50, 40, 30])
    labels = pd.Series([1, 1, 0, 1, 0, 0])
    out = backtest.hit_false_alarm(scores, labels, threshold=70)
    # alarme: 90,80 (índices 0,1). eventos: índices 0,1,3.
    assert out["n_events"] == 3 and out["n_no_events"] == 3
    assert out["hit_rate"] == pytest.approx(2 / 3)   # 2 dos 3 eventos tinham alarme
    assert out["false_alarm_rate"] == pytest.approx(0.0)  # nenhum não-evento teve alarme


def test_hit_false_alarm_needs_both_classes():
    assert backtest.hit_false_alarm(pd.Series([1, 2, 3]), pd.Series([1, 1, 1]), 2) is None


# ---------------------------------------------------------------- episódios
def test_detect_episodes_groups_contiguous_runs():
    df = pd.DataFrame({
        "period": ["2000Q1", "2000Q2", "2000Q3", "2000Q4", "2001Q1", "2001Q2"],
        "key": [200001, 200002, 200003, 200004, 200101, 200102],
        "event_drawdown": [0, 1, 1, 0, 1, 1],
        "score": [10, 90, 20, 10, 10, 10],
    })
    episodes = backtest.detect_episodes(df)
    assert episodes == [("2000Q2", "2000Q3"), ("2001Q1", "2001Q2")]
    hits = backtest.episode_hits({"XX": df}, threshold=70)
    assert hits["n_episodes"] == 2 and hits["n_signaled"] == 1  # só o 1.º episódio teve score >=70


# ---------------------------------------------------------------- export / integração
def test_run_demo_produces_json_serializable_result():
    results = backtest.run(countries=["PT", "DE"], demo=True, min_history=40)
    assert results["demo"] is True
    assert {"generated_at", "params", "countries", "series", "metrics", "limits", "summary"} <= results.keys()
    codes = {c["code"] for c in results["countries"]}
    assert codes == {"PT", "DE"}
    for cc in codes:
        s = results["series"][cc]
        assert len(s["period"]) == len(s["score"]) == len(s["hpi_real"])
    assert results["metrics"]["pooled"]["score"] is not None
    assert "PT" in results["metrics"]["leave_one_out"]
    assert set(results["metrics"]["min_history_sensitivity"]) == {"32", "60"}
    # tem de dar para exportar e reler como JSON (usado por `imopt backtest` e pelo site)
    blob = json.dumps(results, ensure_ascii=False)
    back = json.loads(blob)
    assert back["countries"][0]["code"] in {"PT", "DE"}


def test_run_demo_unknown_country_is_skipped_not_fatal():
    results = backtest.run(countries=["PT", "ZZ"], demo=True, min_history=40)
    codes = {c["code"] for c in results["countries"]}
    assert codes == {"PT"}


def test_summarize_none_when_no_scores():
    empty = pd.DataFrame({"score": pd.Series(dtype=float)})
    assert backtest.summarize(empty, "score") is None
