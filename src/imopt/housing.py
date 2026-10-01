"""Rendimento de quem vive no concelho (IRS), oferta nova, parque habitacional e alojamento turístico, e a
evolução do esforço de compra no tempo. Só contexto: nada disto entra em nenhum score.

Todos os indicadores são opcionais; cada função devolve vazio/None se faltar o que precisa.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .scoring import latest_with_lags

AREA_M2, LTV, YEARS = 90, 0.9, 30          # casa e crédito de referência (os mesmos da calculadora do site)


def to_annual(df: pd.DataFrame | None, how: str = "sum") -> pd.DataFrame | None:
    """Mensal/trimestral -> anual (só anos completos); anual fica igual. Formato: dico, sort_key (AAAA00), value."""
    if df is None or df.empty:
        return None
    kind = str(df["period_kind"].iloc[0]) if "period_kind" in df else "year"
    if kind == "year" or (df["sort_key"] % 100 == 0).all():
        return df
    need = 12 if kind == "month" else 4
    d = df.assign(y=df["sort_key"] // 100)
    g = d.groupby(["dico", "y"])["value"].agg([how, "count"]).reset_index()
    g = g[g["count"] == need]
    keep = ["level"] if "level" in df else []
    out = pd.DataFrame({"dico": g["dico"], "sort_key": g["y"] * 100, "period": g["y"].astype(str), "value": g[how]})
    for c in keep:
        out[c] = "municipality"
    return out


def dico4(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Censos 2021: o concelho vem com geocod de 4 dígitos (o próprio DICO), que o parser classifica como 'other'."""
    if df is None or df.empty or "geocod" not in df:
        return df
    g = df["geocod"].astype(str).str.strip()
    m = g.str.fullmatch(r"\d{4}") & df["dico"].isna()
    if not m.any():
        return df
    df = df.copy()
    df.loc[m, "dico"], df.loc[m, "level"] = g[m], "municipality"
    return df


def context_features(frames: dict[str, pd.DataFrame | None]) -> pd.DataFrame:
    """Uma linha por concelho (municipais já filtrados). Colunas só aparecem se houver dados."""
    out = pd.DataFrame(columns=["dico"])

    def add(df):
        nonlocal out
        out = df if out.empty else out.merge(df, on="dico", how="outer")

    def latest(key, how="mean", lags=None):
        df = frames.get(key)
        if df is None or df.empty:
            return None
        return latest_with_lags(to_annual(df, how), "year", lags or {})

    if (d := latest("irs_median", lags={"y1": 1})) is not None:
        add(pd.DataFrame({"dico": d["dico"], "irs_median": d["latest"], "irs_year": d["latest_key"] // 100,
                          "irs_growth_1y": d["latest"] / d["y1"] - 1}))
    if (d := latest("dwellings_stock")) is not None:
        add(pd.DataFrame({"dico": d["dico"], "dwellings": d["latest"], "dwellings_year": d["latest_key"] // 100}))
    for key, name in (("tourism_beds", "tourism_beds"), ("tourism_beds_al", "al_beds")):
        if (d := latest(key)) is not None:
            add(pd.DataFrame({"dico": d["dico"], name: d["latest"], f"{name}_year": d["latest_key"] // 100}))
    census = {k: latest(f"census_{k}") for k in ("total", "secondary", "vacant_market", "vacant_other")}
    if census["total"] is not None:
        c = census["total"][["dico", "latest", "latest_key"]].rename(columns={"latest": "census_total"})
        c["census_year"] = c.pop("latest_key") // 100
        for k in ("secondary", "vacant_market", "vacant_other"):
            if census[k] is not None:
                c = c.merge(census[k][["dico", "latest"]].rename(columns={"latest": k}), on="dico", how="left")
        if "secondary" in c:
            c["secondary_share"] = c["secondary"] / c["census_total"]
        if "vacant_market" in c and "vacant_other" in c:
            c["vacant_share"] = (c["vacant_market"] + c["vacant_other"]) / c["census_total"]
            c["vacant_market_share"] = c["vacant_market"] / c["census_total"]
        add(c.drop(columns=[k for k in ("secondary", "vacant_market", "vacant_other") if k in c]))
    if out.empty:
        return out
    if "dwellings" in out:
        for name, col in (("tourism_beds", "beds_per_100"), ("al_beds", "al_beds_per_100")):
            if name in out:
                out[col] = out[name] / out["dwellings"] * 100
    return out


def supply(licensed: pd.DataFrame | None, completed: pd.DataFrame | None,
           stock: pd.DataFrame | None = None) -> dict | None:
    """Construção nova no país: o INE publica licenças (mensal) e conclusões (trimestral) só até às regiões, não por
    concelho. Série anual (anos completos), por 1000 alojamentos, e os últimos 12 meses face aos 12 anteriores."""
    def nat(df):
        if df is None or df.empty:
            return None
        d = df[df["level"] == "national"].dropna(subset=["value"]) if "level" in df else df
        return None if d.empty else d.assign(dico="PT").sort_values("sort_key")

    stock_a = _national_annual(stock)
    out: dict = {"series": {}, "recent": {}}
    for key, df in (("licensed", nat(licensed)), ("completed", nat(completed))):
        if df is None:
            continue
        a = to_annual(df, "sum")
        if a is not None and not a.empty:
            rows = []
            for k, v in zip(a["sort_key"], a["value"]):
                y = int(k) // 100
                st = None
                if stock_a is not None and len(stock_a[stock_a.index <= y]):
                    st = float(stock_a[stock_a.index <= y].iloc[-1])
                rows.append([str(y), float(v), float(v) / st * 1000 if st else None])
            out["series"][key] = rows
        n = 12 if str(df["period_kind"].iloc[0]) == "month" else 4
        if len(df) >= 2 * n:
            last, prev = df["value"].iloc[-n:].sum(), df["value"].iloc[-2 * n:-n].sum()
            out["recent"][key] = {"until": str(df["period"].iloc[-1]), "last12": float(last),
                                  "change": float(last / prev - 1) if prev > 0 else None}
    if not out["series"]:
        return None
    if stock_a is not None:
        out["stock"] = {"year": int(stock_a.index[-1]), "value": float(stock_a.iloc[-1])}
    return out


def _annuity(loan, rate_pct, years=YEARS):
    r, n = np.asarray(rate_pct, float) / 1200, years * 12
    return np.where(np.abs(r) < 1e-12, loan / n, loan * r / (1 - (1 + r) ** -n))


def _national_annual(df: pd.DataFrame | None) -> pd.Series | None:
    if df is None or df.empty or "level" not in df:
        return None
    d = df[df["level"] == "national"].dropna(subset=["value"])
    if d.empty:
        return None
    a = to_annual(d.assign(dico="PT"), "mean")
    return a.set_index(a["sort_key"] // 100)["value"].astype(float).sort_index()


def affordability_history(valuation: pd.DataFrame | None, mortgage: pd.DataFrame | None,
                          wages: pd.DataFrame | None = None, irs: pd.DataFrame | None = None) -> dict | None:
    """Esforço nacional por trimestre: casa de 90 m² à avaliação bancária mediana do país, 90% financiado a 30 anos
    à taxa média dos novos créditos (BCE), a dividir pelo salário médio (bruto, mensal) e pela mediana do IRS (após
    imposto, anual/12) do país. O rendimento do último ano publicado é usado nos trimestres seguintes (marcado)."""
    if valuation is None or mortgage is None or valuation.empty or mortgage.empty:
        return None
    v = valuation[valuation["level"] == "national"].dropna(subset=["value"]) if "level" in valuation else valuation
    if v.empty:
        return None
    k = v["sort_key"].astype(int)
    vq = v.assign(q=(k // 100) * 100 + ((k % 100) - 1) // 3 + 1).groupby("q")["value"].agg(["mean", "count"])
    vq = vq[vq["count"] == 3]["mean"]
    m = mortgage.dropna(subset=["value"])
    mk = np.array([int(str(p)[:4]) * 100 + int(str(p)[5:7]) for p in m["period"]])
    mq = pd.Series(m["value"].astype(float).to_numpy(), index=(mk // 100) * 100 + ((mk % 100) - 1) // 3 + 1)
    mq = mq.groupby(level=0).mean()
    common = [q for q in vq.index if q in mq.index]
    if len(common) < 8:
        return None
    w, i = _national_annual(wages), _national_annual(irs)

    def asof(s, year):
        if s is None:
            return np.nan, None
        prior = s[s.index <= year]
        return (float(prior.iloc[-1]), int(prior.index[-1])) if len(prior) and year - int(prior.index[-1]) <= 2 else (np.nan, None)

    rows = []
    for q in common:
        y = q // 100
        pay = float(_annuity(vq[q] * AREA_M2 * LTV, mq[q]))
        wv, wy = asof(w, y)
        iv, iy = asof(i, y)
        rows.append({"period": f"{y}Q{q % 100}", "price": float(vq[q]), "rate": float(mq[q]), "payment": pay,
                     "effort_wage": pay / wv if wv == wv else None, "wage_year": wy,
                     "effort_irs": pay / (iv / 12) if iv == iv else None, "irs_year": iy})
    df = pd.DataFrame(rows)
    out = {"area": AREA_M2, "ltv": LTV, "years": YEARS, "series": rows,
           "last": rows[-1], "first": rows[0]}
    for col in ("effort_wage", "effort_irs"):
        s = df.dropna(subset=[col])
        if len(s):
            out[f"{col}_min"] = {"period": s.loc[s[col].idxmin(), "period"], "value": float(s[col].min())}
            out[f"{col}_max"] = {"period": s.loc[s[col].idxmax(), "period"], "value": float(s[col].max())}
    pay = df.set_index("period")["payment"]
    out["payment_max"] = {"period": pay.idxmax(), "value": float(pay.max())}
    out["payment_min"] = {"period": pay.idxmin(), "value": float(pay.min())}
    return out
