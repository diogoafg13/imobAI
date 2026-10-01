"""Rendimento de quem vive no concelho (IRS), oferta nova, parque habitacional e alojamento turístico, e a
evolução do esforço de compra no tempo. Só contexto: nada disto entra em nenhum score.

Todos os indicadores são opcionais; cada função devolve vazio/None se faltar o que precisa.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .scoring import latest_with_lags

AREA_M2, LTV, YEARS = 90, 0.9, 30          # casa e crédito de referência (os mesmos da calculadora do site)
TOP = 10


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


def context_features(frames: dict[str, pd.DataFrame | None]) -> pd.DataFrame:
    """Uma linha por concelho (municipais já filtrados). Colunas só aparecem se houver dados."""
    out = pd.DataFrame(columns=["dico"])

    def add(df):
        nonlocal out
        out = df if out.empty else out.merge(df, on="dico", how="outer")

    irs = frames.get("irs_median")
    if irs is not None and not irs.empty:
        d = latest_with_lags(to_annual(irs, "mean"), "year", {"y1": 1})
        add(pd.DataFrame({"dico": d["dico"], "irs_median": d["latest"], "irs_year": d["latest_key"] // 100,
                          "irs_growth_1y": d["latest"] / d["y1"] - 1}))
    for key, name in (("dwellings_licensed", "lic"), ("dwellings_completed", "comp")):
        a = to_annual(frames.get(key), "sum")
        if a is None or a.empty:
            continue
        d = latest_with_lags(a, "year", {"p1": 1, "p2": 2, "p3": 3, "p4": 4, "p5": 5})
        avg3 = d[["latest", "p1", "p2"]].mean(axis=1, skipna=False)
        prev3 = d[["p3", "p4", "p5"]].mean(axis=1, skipna=False)
        add(pd.DataFrame({"dico": d["dico"], f"{name}_avg3": avg3, f"{name}_year": d["latest_key"] // 100,
                          f"{name}_growth_3y": (avg3 / prev3 - 1).where(prev3 > 0)}))
    stock = frames.get("dwellings_stock")
    if stock is not None and not stock.empty:
        d = latest_with_lags(to_annual(stock, "mean"), "year", {})
        add(pd.DataFrame({"dico": d["dico"], "dwellings": d["latest"], "dwellings_year": d["latest_key"] // 100}))
    beds = frames.get("tourism_beds")
    if beds is not None and not beds.empty:
        d = latest_with_lags(to_annual(beds, "mean"), "year", {})
        add(pd.DataFrame({"dico": d["dico"], "tourism_beds": d["latest"], "tourism_beds_year": d["latest_key"] // 100}))
    if out.empty:
        return out
    if "dwellings" in out:
        for name in ("lic", "comp"):
            if f"{name}_avg3" in out:
                out[f"{name}_per_1000"] = out[f"{name}_avg3"] / out["dwellings"] * 1000
        if "tourism_beds" in out:
            out["beds_per_100"] = out["tourism_beds"] / out["dwellings"] * 100
    return out


def supply(feats: pd.DataFrame | None, licensed: pd.DataFrame | None = None,
           completed: pd.DataFrame | None = None) -> dict | None:
    """Construção nova: série nacional (soma dos concelhos com ano completo), relação com os preços e listas."""
    if feats is None or "lic_per_1000" not in feats:
        return None
    f = feats.dropna(subset=["lic_per_1000"])
    if len(f) < 10:
        return None
    out: dict = {"n": int(len(f)), "year": int(f["lic_year"].max()),
                 "median_lic_per_1000": float(f["lic_per_1000"].median())}
    if "comp_per_1000" in f:
        out["median_comp_per_1000"] = float(f["comp_per_1000"].median())
    series = {}
    for key, df in (("licensed", licensed), ("completed", completed)):
        a = to_annual(df, "sum")
        if a is not None and not a.empty:
            # só anos em que pelo menos 90% dos concelhos do ano mais completo têm valor (evita anos parciais)
            cnt = a.groupby("sort_key")["dico"].nunique()
            ok = cnt[cnt >= 0.9 * cnt.max()].index
            s = a[a["sort_key"].isin(ok)].groupby("sort_key")["value"].sum()
            series[key] = [[str(k // 100), float(v)] for k, v in s.items()]
    if series:
        out["series"] = series
    if "price_growth_3y" in f:
        g = f.dropna(subset=["price_growth_3y"])
        if len(g) >= 20:
            out["spearman_price_3y"] = float(g["lic_per_1000"].rank().corr(g["price_growth_3y"].rank()))
            # preço a subir muito (quartil de cima) com pouca construção nova (quartil de baixo)
            hi_p, lo_l = g["price_growth_3y"].quantile(0.75), g["lic_per_1000"].quantile(0.25)
            tight = g[(g["price_growth_3y"] >= hi_p) & (g["lic_per_1000"] <= lo_l)]
            if "val_count" in tight:
                tight = tight[tight["val_count"].fillna(0) >= 20]
            out["tight"] = [{"dico": str(r.dico), "name": str(r.name), "lic": float(r.lic_per_1000),
                             "g3": float(r.price_growth_3y)} for r in tight.sort_values("price_growth_3y", ascending=False).head(TOP).itertuples()]
    top = f.sort_values("lic_per_1000", ascending=False)
    if "dwellings" in top:
        top = top[top["dwellings"] >= 2000]     # concelhos muito pequenos saltam com um só empreendimento
    out["top"] = [{"dico": str(r.dico), "name": str(r.name), "lic": float(r.lic_per_1000),
                   "g3": None if pd.isna(getattr(r, "price_growth_3y", np.nan)) else float(r.price_growth_3y)}
                  for r in top.head(TOP).itertuples()]
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
