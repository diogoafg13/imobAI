"""Cálculo de indicadores e scores.

Convenção: scores em 0-100, onde MAIS ALTO = mais esticado/arriscado.

IMPORTANTE (honestidade metodológica):
- Os scores municipais são RELATIVOS (percentis entre concelhos no último período).
  Dizem "este concelho está mais esticado do que os outros", não "vai corrigir".
- O score nacional compara com a própria história (z-scores) e é o único com leitura
  temporal. Nenhum dos dois foi validado por backtest: ver docs/methodology.md.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def pct_rank(s: pd.Series) -> pd.Series:
    """Percentil 0-100 (NaN preservados)."""
    return s.rank(pct=True, method="average") * 100


def logistic_score(z: float | None, scale: float = 1.0) -> float | None:
    """z-score -> 0-100 (50 = média histórica)."""
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return None
    return float(100 / (1 + math.exp(-z / scale)))


def _pivot(df: pd.DataFrame) -> pd.DataFrame:
    p = df.pivot_table(index="dico", columns="sort_key", values="value", aggfunc="last")
    return p.sort_index(axis=1)


def _shift_key(sort_key: int, kind: str, back: int) -> int:
    """Chave de período `back` períodos atrás (trimestres ou anos)."""
    year, sub = divmod(sort_key, 100)
    if kind == "quarter":
        total = year * 4 + (sub - 1) - back
        y, q = divmod(total, 4)
        return y * 100 + q + 1
    if kind == "month":
        total = year * 12 + (sub - 1) - back
        y, m = divmod(total, 12)
        return y * 100 + m + 1
    return (year - back) * 100


def latest_with_lags(df: pd.DataFrame, kind: str, lags: dict[str, int]) -> pd.DataFrame:
    """Último valor por concelho e valores desfasados (nomes -> nº de períodos)."""
    if df.empty:
        return pd.DataFrame(columns=["dico", "latest", "latest_key"])
    p = _pivot(df)
    latest_key = int(p.columns.max())
    out = pd.DataFrame({"latest": p[latest_key]})
    out["latest_key"] = latest_key
    for name, back in lags.items():
        k = _shift_key(latest_key, kind, back)
        out[name] = p[k] if k in p.columns else np.nan
    return out.reset_index()


def municipal_features(sales: pd.DataFrame, rent: pd.DataFrame | None,
                       permits: pd.DataFrame | None = None,
                       completed: pd.DataFrame | None = None) -> pd.DataFrame:
    """Uma linha por concelho com níveis, variações e sub-scores."""
    s = latest_with_lags(sales, "quarter", {"p_1y": 4, "p_3y": 12, "p_5y": 20})
    s = s.rename(columns={"latest": "price"})
    names = sales.drop_duplicates("dico").set_index("dico")["geoname"]
    s["name"] = s["dico"].map(names)
    s["price_growth_1y"] = s["price"] / s["p_1y"] - 1
    s["price_growth_3y"] = s["price"] / s["p_3y"] - 1
    s["price_growth_5y"] = s["price"] / s["p_5y"] - 1

    if rent is not None and not rent.empty:
        r = latest_with_lags(rent, "year", {"r_1y": 1})
        r = r.rename(columns={"latest": "rent", "latest_key": "rent_year"})
        s = s.merge(r[["dico", "rent", "r_1y", "rent_year"]], on="dico", how="left")
        s["rent_growth_1y"] = s["rent"] / s["r_1y"] - 1
        s["gross_yield"] = s["rent"] * 12 / s["price"]
        s["price_to_rent_years"] = s["price"] / (s["rent"] * 12)
    else:
        for c in ("rent", "rent_growth_1y", "gross_yield", "price_to_rent_years"):
            s[c] = np.nan

    # Sub-score de valorização: crescimento recente + rendibilidade baixa.
    parts = [pct_rank(s["price_growth_1y"]), pct_rank(s["price_growth_3y"]), 100 - pct_rank(s["gross_yield"])]
    s["score_valuation"] = pd.concat(parts, axis=1).mean(axis=1, skipna=True)
    s.loc[pd.concat(parts, axis=1).isna().all(axis=1), "score_valuation"] = np.nan

    # Sub-score de oferta (só se existirem dados): licenças e concluídos a crescer = mais oferta futura.
    supply_parts = []
    for name, df in (("permits", permits), ("completed", completed)):
        if df is not None and not df.empty:
            f = latest_with_lags(df, "year", {"prev": 3}).rename(columns={"latest": name})
            f[f"{name}_growth"] = f[name] / f["prev"] - 1
            s = s.merge(f[["dico", name, f"{name}_growth"]], on="dico", how="left")
            supply_parts.append(100 - pct_rank(s[f"{name}_growth"]))  # mais oferta nova alivia pressão
    s["score_supply"] = pd.concat(supply_parts, axis=1).mean(axis=1) if supply_parts else np.nan

    sub = s[["score_valuation", "score_supply"]]
    s["score_overall"] = sub.mean(axis=1, skipna=True)
    s.loc[sub.isna().all(axis=1), "score_overall"] = np.nan
    s["band"] = pd.cut(s["score_overall"], [-1, 40, 70, 101], labels=["green", "amber", "red"]).astype("object")
    return s.drop(columns=["p_1y", "p_3y", "p_5y", "r_1y"], errors="ignore")


def _yoy(series: pd.Series, periods: int) -> pd.Series:
    return series / series.shift(periods) - 1


def detrend_z(series: pd.Series) -> float | None:
    """z-score do desvio do log da série face a uma tendência linear (último ponto)."""
    y = np.log(series.dropna().astype(float))
    if len(y) < 12:
        return None
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y.values, 1)
    resid = y.values - (slope * x + intercept)
    sd = resid.std(ddof=1)
    return float(resid[-1] / sd) if sd > 0 else None


def zscore_last(series: pd.Series) -> float | None:
    s = series.dropna()
    if len(s) < 8 or s.std(ddof=1) == 0:
        return None
    return float((s.iloc[-1] - s.mean()) / s.std(ddof=1))


def national_scores(hpi: pd.DataFrame | None, euribor: pd.DataFrame | None,
                    credit_gap: pd.DataFrame | None) -> dict:
    """Score nacional por componentes. Cada componente é opcional."""
    comps: dict[str, dict] = {}

    if hpi is not None and len(hpi) >= 20:
        h = hpi.sort_values("period").set_index("period")["value"]
        yoy = _yoy(h, 4)
        comps["hpi_yoy"] = {
            "label": "Crescimento anual do índice de preços",
            "value": None if yoy.dropna().empty else float(yoy.dropna().iloc[-1]),
            "z": zscore_last(yoy),
        }
        comps["hpi_trend_dev"] = {
            "label": "Desvio do índice face à tendência de longo prazo",
            "value": detrend_z(h),
            "z": detrend_z(h),
        }

    if euribor is not None and len(euribor) >= 24:
        e = euribor.sort_values("period").set_index("period")["value"]
        chg = e - e.shift(12)
        # Juros a subir rapidamente = risco maior (sinal +).
        comps["euribor_change_12m"] = {
            "label": "Variação da Euribor 12M em 12 meses (p.p.)",
            "value": None if chg.dropna().empty else float(chg.dropna().iloc[-1]),
            "z": zscore_last(chg),
        }

    if credit_gap is not None and len(credit_gap) >= 8:
        g = credit_gap.sort_values("period").set_index("period")["value"]
        comps["credit_gap"] = {
            "label": "Desvio crédito/PIB face à tendência (p.p., BIS)",
            "value": float(g.iloc[-1]),
            "z": zscore_last(g),
        }

    for c in comps.values():
        c["score"] = logistic_score(c["z"])
    scores = [c["score"] for c in comps.values() if c["score"] is not None]
    overall = float(np.mean(scores)) if scores else None
    band = None if overall is None else ("green" if overall < 40 else "amber" if overall < 70 else "red")
    return {"components": comps, "overall": overall, "band": band}
