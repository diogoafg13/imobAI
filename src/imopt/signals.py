"""Que sinais ajudam a prever o preço de venda? Teste com a mesma previsão do painel (imopt/forecast.py).

Para cada sinal candidato, a previsão de vendas do INE é refeita com esse sinal a mais e comparada com a
previsão base no mesmo backtest sem olhar para o futuro (cada origem só usa dados até essa data; os sinais
usam o último valor publicado até então, com o atraso típico de publicação).

Regra fixada ANTES de ver os resultados (a mesma usada para o volume de avaliações):
  entra na previsão se reduzir o erro médio a 12 meses (horizonte da previsão publicada) em pelo menos 1%
  e não aumentar o erro a 1 trimestre em mais de 1%.
Os que entram ficam fixos em PRODUCTION (decidido uma vez e documentado no README); o teste é refeito em cada
build e mostrado no site, para se ver se a conclusão se mantém com dados novos.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import forecast as fc

log = logging.getLogger("imopt")

LABELS = {
    "x_credit": "crédito à habitação novo (BCE), variação anual do total de 12 meses",
    "x_cost": "custo de construção de habitação nova (INE), variação anual",
    "x_lic": "fogos licenciados (INE), variação anual do total de 12 meses",
    "x_vgap": "avaliação bancária face ao preço de venda do concelho",
    "x_effort": "esforço de compra do concelho (prestação ÷ rendimento do IRS)",
    "x_tourism": "dormidas turísticas do concelho, variação anual",
}
fc.FEATURE_LABELS.update(LABELS)
MIN_GAIN, MAX_LOSS_H1 = 0.01, 0.01
PRODUCTION: tuple[str, ...] = ()     # sinais que passaram a regra (ver README); vazio até haver um que passe


def _monthly_log(df: pd.DataFrame | None, roll12: bool = False) -> pd.Series | None:
    """Série nacional mensal ('AAAA-MM' ou sort_key AAAAMM) -> log, por índice de mês; roll12 = soma de 12 meses."""
    if df is None or df.empty:
        return None
    d = df.dropna(subset=["value"])
    if "level" in d:
        d = d[d["level"] == "national"]
    if d.empty:
        return None
    if "sort_key" in d and d["sort_key"].notna().all():
        idx = [fc.m_index(int(k)) for k in d["sort_key"]]
    else:
        idx = [fc._month_of_label(str(p)) for p in d["period"]]
    s = pd.Series(d["value"].astype(float).to_numpy(), index=idx).groupby(level=0).last().sort_index()
    if roll12:
        s = s.reindex(range(int(s.index.min()), int(s.index.max()) + 1)).rolling(12, min_periods=12).sum()
    s = s[s > 0]
    return np.log(s) if len(s) else None


def _asof(s: pd.Series, k: int) -> float:
    prior = s[s.index <= k]
    return float(prior.iloc[-1]) if len(prior) else np.nan


def _yoy_national(s: pd.Series | None):
    if s is None:
        return None
    return lambda q, me, idx, s0: _asof(s, me) - _asof(s, me - 12)


def _annual_grid(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    d = df[df["level"] == "municipality"].dropna(subset=["dico", "value"]) if "level" in df else df.dropna(subset=["dico", "value"])
    d = d[d["value"].astype(float) > 0]
    if d.empty:
        return None
    return np.log(d.assign(y=d["sort_key"] // 100).pivot_table(index="dico", columns="y", values="value", aggfunc="last"))


def candidates(frames: dict, macro_frames: dict, valuation: pd.DataFrame | None) -> dict:
    """{nome: função de sinal} só para os sinais com dados nesta build."""
    out = {}
    if (f := _yoy_national(_monthly_log(macro_frames.get("mortgage_volume_pt"), roll12=True))) is not None:
        out["x_credit"] = f
    if (f := _yoy_national(_monthly_log(frames.get("construction_cost")))) is not None:
        out["x_cost"] = f
    if (f := _yoy_national(_monthly_log(frames.get("dwellings_licensed"), roll12=True))) is not None:
        out["x_lic"] = f
    v3, _ = fc.valuation_grids(valuation)
    if v3 is not None:
        out["x_vgap"] = lambda q, me, idx, s0: fc._c(v3, me, idx) - s0
    tg = _annual_grid(frames.get("tourism_nights"))
    if tg is not None:
        def tourism(q, me, idx, s0):
            y, m = divmod(me, 12)
            ya = y - 1 if m >= 6 else y - 2           # o ano Y sai por volta de junho de Y+1
            if ya in tg.columns and ya - 1 in tg.columns:
                return (tg[ya] - tg[ya - 1]).reindex(idx)
            return pd.Series(np.nan, index=idx)
        out["x_tourism"] = tourism
    irs = _annual_grid(frames.get("irs_median"))
    rate = fc.euribor_series(macro_frames.get("mortgage_rate_pt"))
    if irs is not None and rate is not None:
        def effort(q, me, idx, s0):
            ya = me // 12 - 2                         # o IRS do ano Y sai cerca de 2 anos depois
            prior = [c for c in irs.columns if c <= ya]
            if not prior:
                return pd.Series(np.nan, index=idx)
            r = _asof(rate, me) / 1200
            n = 360
            factor = r / (1 - (1 + r) ** -n) if r > 1e-9 else 1 / n
            return s0 + np.log(factor) - irs[prior[-1]].reindex(idx)
        out["x_effort"] = effort
    return out


def evaluate(sales: pd.DataFrame, valuation, euribor, nbrs, cands: dict) -> dict | None:
    """Previsão base vs base + cada sinal, no mesmo backtest. Devolve a tabela para o site."""
    if sales is None or sales.empty or not cands:
        return None
    base, _ = fc.forecast_sales(sales, valuation, euribor, nbrs)
    if not base or not base.get("backtest"):
        return None
    hs = sorted(int(h) for h in base["backtest"])
    h_fc, h1 = hs[-1], hs[0]

    def mae(summary, h):
        b = (summary or {}).get("backtest", {}).get(str(h))
        return b["mae_model"] if b else None

    rows = []
    for name, fn in cands.items():
        try:
            alt, _ = fc.forecast_sales(sales, valuation, euribor, nbrs, extra={name: fn})
        except Exception as e:  # noqa: BLE001
            log.warning("sinal %s falhou: %s", name, e)
            continue
        if not alt or name not in alt.get("features", []):
            rows.append({"signal": name, "label": LABELS.get(name, name), "status": "sem variação suficiente"})
            continue
        if None in (mae(alt, h_fc), mae(base, h_fc), mae(alt, h1), mae(base, h1)):
            rows.append({"signal": name, "label": LABELS.get(name, name), "status": "sem backtest suficiente"})
            continue
        g_fc = 1 - mae(alt, h_fc) / mae(base, h_fc)
        g_1 = 1 - mae(alt, h1) / mae(base, h1)
        cov = (alt["backtest"][str(h_fc)].get("coverage80"), base["backtest"][str(h_fc)].get("coverage80"))
        passes = g_fc >= MIN_GAIN and g_1 >= -MAX_LOSS_H1
        rows.append({"signal": name, "label": LABELS.get(name, name), "gain_fc": float(g_fc), "gain_h1": float(g_1),
                     "coverage80": cov[0], "coverage80_base": cov[1], "passes": bool(passes),
                     "in_production": name in PRODUCTION, "status": "passa" if passes else "não passa"})
    return {"h_fc": h_fc, "h1": h1, "mae_base_fc": mae(base, h_fc), "mae_base_h1": mae(base, h1),
            "rule": f"entra se reduzir o erro a {h_fc} trimestres em pelo menos {MIN_GAIN:.0%} sem aumentar o erro a "
                    f"1 trimestre em mais de {MAX_LOSS_H1:.0%}",
            "first_origin": base["backtest"][str(h_fc)]["first_origin"], "last_origin": base["backtest"][str(h_fc)]["last_origin"],
            "rows": sorted(rows, key=lambda r: -(r.get("gain_fc") or -9))}


def evaluate_all(sales, valuation, euribor, nbrs, cands: dict, types: dict | None = None) -> dict | None:
    """Teste principal (vendas do INE, regra fixada antes) e exploratório (avaliação bancária de apartamentos e
    moradias, 15 anos de histórico; não decide nada — só mostra se a conclusão é a mesma)."""
    main = evaluate(sales, valuation, euribor, nbrs, cands)
    if main is None:
        return None
    explo = {}
    for key, (q, vol) in (types or {}).items():
        if q is None:
            continue
        try:
            base, _ = fc.forecast_sales(q, None, euribor, nbrs, volume=vol)
            hs = sorted(int(h) for h in base["backtest"])
            hf, h1 = str(hs[-1]), str(hs[0])
            rows = []
            for name, fn in cands.items():
                if name in ("x_vgap",):           # precisa do preço de venda do INE
                    continue
                alt, _ = fc.forecast_sales(q, None, euribor, nbrs, volume=vol, extra={name: fn})
                if name not in alt.get("features", []):
                    continue
                rows.append({"signal": name, "gain_fc": float(1 - alt["backtest"][hf]["mae_model"] / base["backtest"][hf]["mae_model"]),
                             "gain_h1": float(1 - alt["backtest"][h1]["mae_model"] / base["backtest"][h1]["mae_model"])})
            explo[key] = {"h_fc": int(hf), "n_origins": base["backtest"][hf]["n_origins"],
                          "first_origin": base["backtest"][hf]["first_origin"], "rows": rows}
        except Exception as e:  # noqa: BLE001
            log.warning("teste exploratório de sinais (%s) falhou: %s", key, e)
    if explo:
        main["exploratory"] = explo
    return main
