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


def last12(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Série mensal por concelho -> soma dos últimos 12 meses publicados e variação face aos 12 anteriores."""
    if df is None or df.empty:
        return None
    k = df["sort_key"].astype(int)
    idx = (k // 100) * 12 + (k % 100) - 1
    end = int(idx.max())
    d = df.assign(i=idx)
    now = d[d["i"] > end - 12].groupby("dico")["value"].agg(["sum", "count"])
    prev = d[(d["i"] <= end - 12) & (d["i"] > end - 24)].groupby("dico")["value"].agg(["sum", "count"])
    now = now[now["count"] == 12]["sum"]
    if now.empty:
        return None
    prev = prev[prev["count"] == 12]["sum"].reindex(now.index)
    return pd.DataFrame({"dico": now.index, "now": now.to_numpy(), "growth": (now / prev - 1).where(prev > 0).to_numpy(),
                         "until": f"{end // 12}-{end % 12 + 1:02d}"})


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
    if (d := latest("population")) is not None:
        add(pd.DataFrame({"dico": d["dico"], "population": d["latest"], "population_year": d["latest_key"] // 100}))
    if (d := latest("dwellings_stock")) is not None:
        add(pd.DataFrame({"dico": d["dico"], "dwellings": d["latest"], "dwellings_year": d["latest_key"] // 100}))
    for key, name in (("tourism_beds", "tourism_beds"), ("tourism_beds_al", "al_beds")):
        if (d := latest(key)) is not None:
            add(pd.DataFrame({"dico": d["dico"], name: d["latest"], f"{name}_year": d["latest_key"] // 100}))
    g = last12(frames.get("tourism_guests"))
    if g is not None:
        add(g.rename(columns={"now": "guests_12m", "growth": "guests_growth_1y", "until": "guests_until"}))
        ga = last12(frames.get("tourism_guests_al"))
        if ga is not None:
            add(ga[["dico", "now"]].rename(columns={"now": "guests_al_12m"}))
    if (d := latest("tourism_occupancy", lags={"y1": 1})) is not None:
        add(pd.DataFrame({"dico": d["dico"], "occupancy": d["latest"] / 100, "occupancy_year": d["latest_key"] // 100,
                          "occupancy_chg": (d["latest"] - d["y1"]) / 100}))
    br = [latest(f"tax_households_{k}") for k in range(1, 7)]
    if all(b is not None for b in br):
        t = br[0][["dico", "latest_key"]].rename(columns={"latest_key": "k"})
        for i, b in enumerate(br, 1):
            t = t.merge(b[["dico", "latest"]].rename(columns={"latest": f"n{i}"}), on="dico", how="inner")
        tot = t[[f"n{i}" for i in range(1, 7)]].sum(axis=1)
        sh = pd.DataFrame({"dico": t["dico"], "tax_hh_year": t["k"] // 100, "tax_hh_total": tot})
        for i in range(1, 7):
            sh[f"tax_hh_{i}"] = (t[f"n{i}"] / tot).where(tot > 0)
        add(sh)
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
    if "guests_al_12m" in out:
        out["guests_al_share"] = (out["guests_al_12m"] / out["guests_12m"]).where(out["guests_12m"] > 0)
    if "dwellings" in out:
        for name, col in (("tourism_beds", "beds_per_100"), ("al_beds", "al_beds_per_100")):
            if name in out:
                out[col] = out[name] / out["dwellings"] * 100
    return out


TYPOLOGIES = (("t01", "T0/T1"), ("t2", "T2"), ("t3", "T3"), ("t4", "T4+"))


def typology_mix(by_type: dict[str, pd.DataFrame | None], prices: dict[str, pd.DataFrame | None]) -> dict | None:
    """Que casas se licenciam (peso de cada tipologia nas licenças do país) face à subida do preço de cada uma."""
    ann = {}
    for k, _ in TYPOLOGIES:
        df = by_type.get(k)
        if df is None or df.empty:
            return None
        d = df[df["level"] == "national"] if "level" in df else df
        a = to_annual(d.assign(dico="PT"), "sum")
        if a is None or a.empty:
            return None
        ann[k] = a.set_index(a["sort_key"] // 100)["value"].astype(float)
    tab = pd.DataFrame(ann).dropna()
    if len(tab) < 6:
        return None
    share = tab.div(tab.sum(axis=1), axis=0)
    y1, y0 = int(share.index.max()), int(share.index.max()) - 5
    if y0 not in share.index:
        return None
    rows = []
    for k, label in TYPOLOGIES:
        g = None
        pdf = prices.get(k)
        if pdf is not None and not pdf.empty and "level" in pdf:
            n = pdf[pdf["level"] == "national"].sort_values("sort_key")
            if len(n) >= 5:
                g = float(n["value"].iloc[-1] / n["value"].iloc[-5] - 1)
        rows.append({"key": k, "label": label, "share_now": float(share.at[y1, k]), "share_before": float(share.at[y0, k]),
                     "price_growth_1y": g})
    return {"year": y1, "year_before": y0, "rows": rows,
            "series": {k: [[str(y), round(float(v), 4)] for y, v in share[k].items()] for k, _ in TYPOLOGIES}}


def supply(licensed: pd.DataFrame | None, completed: pd.DataFrame | None,
           stock: pd.DataFrame | None = None, by_type: dict | None = None, prices: dict | None = None) -> dict | None:
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
    mix = typology_mix(by_type or {}, prices or {})
    if mix:
        out["mix"] = mix
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
    mq = _quarterly_rate(mortgage)
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


def _quarterly_rate(mortgage: pd.DataFrame | None) -> pd.Series | None:
    """Taxa média dos novos créditos (mensal, 'AAAA-MM') -> média por trimestre, índice AAAAQQ."""
    if mortgage is None or mortgage.empty:
        return None
    m = mortgage.dropna(subset=["value"])
    mk = np.array([int(str(p)[:4]) * 100 + int(str(p)[5:7]) for p in m["period"]])
    q = (mk // 100) * 100 + ((mk % 100) - 1) // 3 + 1
    return pd.Series(m["value"].astype(float).to_numpy(), index=q).groupby(level=0).mean()


def _asof_year(piv: pd.DataFrame | None, dico: str, year: int, max_lag: int = 2) -> float:
    if piv is None or dico not in piv.index:
        return np.nan
    row = piv.loc[dico].dropna()
    row = row[row.index <= year]
    return float(row.iloc[-1]) if len(row) and year - int(row.index[-1]) <= max_lag else np.nan


def effort_history_muni(sales: pd.DataFrame | None, mortgage: pd.DataFrame | None, irs: pd.DataFrame | None = None,
                        wages: pd.DataFrame | None = None, names: dict | None = None,
                        volume: pd.Series | None = None) -> tuple[dict | None, dict]:
    """Esforço de compra por concelho e trimestre: 90 m² ao preço mediano de venda do INE, 90% a 30 anos à taxa
    média dos novos créditos desse trimestre, ÷ rendimento do concelho (IRS de quem vive ÷ 12 e salário médio de
    quem trabalha), o do próprio ano ou o último publicado até 2 anos antes."""
    rq = _quarterly_rate(mortgage)
    if sales is None or sales.empty or rq is None:
        return None, {}

    def yearly(df):
        if df is None or df.empty:
            return None
        d = df.dropna(subset=["dico", "value"])
        return d.assign(y=d["sort_key"] // 100).pivot_table(index="dico", columns="y", values="value", aggfunc="last")

    pi, pw = yearly(irs), yearly(wages)
    if pi is None and pw is None:
        return None, {}
    s = sales.dropna(subset=["dico", "value"])
    per, rows = {}, []
    for d, g in s.groupby("dico"):
        pts = []
        for k, v in zip(g["sort_key"], g["value"]):
            k = int(k)
            if k not in rq.index:
                continue
            pay = float(_annuity(float(v) * AREA_M2 * LTV, rq[k]))
            y = k // 100
            i, w = _asof_year(pi, d, y), _asof_year(pw, d, y)
            ei = pay / (i / 12) if i == i and i > 0 else None
            ew = pay / w if w == w and w > 0 else None
            if ei is not None or ew is not None:
                pts.append([f"{y}Q{k % 100}", None if ei is None else round(ei, 4), None if ew is None else round(ew, 4)])
                rows.append({"dico": str(d), "q": k, "ei": ei, "ew": ew})
        if pts:
            per[str(d)] = {"effort_hist": sorted(pts)}
    if not rows:
        return None, {}
    df = pd.DataFrame(rows)
    med = df.groupby("q")[["ei", "ew"]].median()
    first, last = int(df["q"].min()), int(df["q"].max())
    summary = {"area": AREA_M2, "ltv": LTV, "years": YEARS, "first": f"{first // 100}Q{first % 100}",
               "last": f"{last // 100}Q{last % 100}",
               "median": [[f"{q // 100}Q{q % 100}", None if pd.isna(r.ei) else round(float(r.ei), 4),
                           None if pd.isna(r.ew) else round(float(r.ew), 4)] for q, r in med.iterrows()]}
    a, b = df[df["q"] == first].set_index("dico")["ei"], df[df["q"] == last].set_index("dico")["ei"]
    chg = (b - a.reindex(b.index)).dropna()
    if volume is not None:
        chg = chg[volume.reindex(chg.index).fillna(0) >= 20]
    if len(chg) >= 10:
        summary["risers"] = [{"dico": d, "name": (names or {}).get(d, d), "from": float(a[d]), "to": float(b[d]),
                              "change": float(x)} for d, x in chg.sort_values(ascending=False).head(10).items()]
        summary["n_doubled"] = int(((b / a.reindex(b.index)) >= 2).sum())
        summary["n_compared"] = int(b.notna().sum())
    return summary, per


def construction_costs(cost: dict[str, pd.DataFrame | None], price_new: pd.DataFrame | None = None,
                       price_existing: pd.DataFrame | None = None) -> dict | None:
    """Custo de construção de habitação nova (INE, mensal, nacional) face ao preço de venda das casas novas e
    usadas (INE, mediana de 12 meses, nacional): variação a 1 ano e desde 2021 (base do índice)."""
    def nat_m(df):
        if df is None or df.empty:
            return None
        d = df[df["level"] == "national"] if "level" in df else df
        d = d.dropna(subset=["value"])
        return None if d.empty else pd.Series(d["value"].astype(float).to_numpy(), index=d["sort_key"].astype(int)).sort_index()

    tot = nat_m(cost.get("total"))
    if tot is None or len(tot) < 24:
        return None

    def yoy_m(s):
        k = int(s.index.max())
        b = (k // 100 - 1) * 100 + k % 100
        return float(s[k] / s[b] - 1) if b in s.index else None

    def since(s, start):
        base = s[(s.index >= start) & (s.index < start + 100)]
        return float(s.iloc[-1] / base.mean() - 1) if len(base) else None

    k = int(tot.index.max())
    out = {"until": f"{k // 100}-{k % 100:02d}", "yoy": yoy_m(tot), "since_2021": since(tot, 202100),
           "parts": {}, "prices": {},
           "series": [[f"{i // 100}-{i % 100:02d}", round(float(v), 1)] for i, v in tot.items() if i >= 201501 and i % 100 in (3, 6, 9, 12)]}
    for key in ("materials", "labour"):
        s = nat_m(cost.get(key))
        if s is not None and len(s) >= 13:
            out["parts"][key] = {"yoy": yoy_m(s), "since_2021": since(s, 202100)}
    for key, df in (("new", price_new), ("existing", price_existing)):
        s = nat_m(df)
        if s is not None and len(s) >= 5:
            kq = int(s.index.max())
            b = (kq // 100 - 1) * 100 + kq % 100
            out["prices"][key] = {"until": f"{kq // 100}Q{kq % 100}", "yoy": float(s[kq] / s[b] - 1) if b in s.index else None,
                                  "since_2021": since(s, 202100)}
    return out


def history_export(sales: pd.DataFrame | None, val_apt: pd.DataFrame | None, val_house: pd.DataFrame | None,
                   hicp: pd.DataFrame | None, val_all: pd.DataFrame | None = None) -> dict:
    """Séries para a análise "O meu imóvel" (carregadas pelo site só quando é usada): preço mediano de venda por
    freguesia (INE, trimestral desde 2019), avaliação bancária trimestral por concelho e tipo de casa (desde 2011)
    e IHPC trimestral (para descontar a inflação)."""
    from . import parishes
    from .outlook import monthly_to_quarterly_muni
    out: dict = {"parish": {}, "val": {}, "hicp": []}
    p = parishes._parish_rows(sales)
    if p is not None:
        for code, g in p.sort_values("sort_key").groupby("code"):
            out["parish"][code] = [[str(a), round(float(b))] for a, b in zip(g["period"], g["value"])]
    for key, df in (("apt", val_apt), ("house", val_house), ("all", val_all)):
        d = None if df is None or df.empty else df[df["level"] == "municipality"].dropna(subset=["dico", "value"])
        q = monthly_to_quarterly_muni(d) if d is not None and not d.empty else None
        if q is not None:
            out["val"][key] = {str(dico): [[str(a), round(float(b))] for a, b in zip(g["period"], g["value"])]
                               for dico, g in q.sort_values("sort_key").groupby("dico")}
    if hicp is not None and not hicp.empty:
        out["hicp"] = [[str(a), round(float(b), 2)] for a, b in zip(hicp["period"], hicp["value"])]
    return out
