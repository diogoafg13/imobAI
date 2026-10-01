"""Secção "Perspetivas": previsões (forecast.py) + padrões nos dados. Ver README.

Nada disto altera os scores do painel. Cada parte é independente e não-fatal: se falhar ou não tiver
dados suficientes, fica ausente do outlook.json e o site mostra o resto.

Padrões (regras fixadas antes de ver resultados):
- Regimes: regressão linear por troços sobre o log do HPI nacional; pontos de quebra ótimos por
  programação dinâmica, número de troços pelo BIC, mínimo de 6 trimestres por troço.
- Tipologias: k-means (k entre 3 e 6, escolhido pela silhueta) sobre três características de cada
  concelho: nível do preço face à mediana, ritmo de subida antes e depois do início da subida dos
  juros do BCE (2022T2). Winsorizadas a 2,5%/97,5% para concelhos muito ruidosos não formarem grupos
  próprios.
- Propagação: correlação entre a variação anual da avaliação bancária de cada concelho e a de
  Lisboa/Porto (a metrópole mais próxima) com desfasamentos de 0 a 24 meses, agregada por faixa de
  distância. Ilhas excluídas.
- Valor justo: regressão transversal do log do preço em rendimento, densidade, envelhecimento,
  migração, distância à metrópole e região (NUTS II). O desvio de cada concelho usa a previsão
  fora da amostra (validação cruzada em 10 partes): não é "bolha", pode ser o que o modelo não vê.
- Juros: aritmética da prestação (capacidade de endividamento com a mesma prestação) + sensibilidade
  histórica do HPI à Euribor, com intervalo por bootstrap em blocos. A sensibilidade só é usada nos
  cenários se o intervalo excluir zero com o sinal esperado.
"""
from __future__ import annotations

import datetime as dt
import logging
import math

import numpy as np
import pandas as pd

from . import forecast as fc
from .geo import haversine_km

log = logging.getLogger("imopt")

NUTS2 = {"11": "Norte", "19": "Centro", "1A": "Grande Lisboa", "1B": "Península de Setúbal", "1C": "Alentejo",
         "1D": "Oeste e Vale do Tejo", "15": "Algarve", "20": "Açores", "30": "Madeira"}
ISLANDS = {"20", "30"}
METROS = {"1106": "Lisboa", "1312": "Porto"}
BANDS = [(0, 25), (25, 50), (50, 100), (100, 200), (200, math.inf)]
RATE_HIKE_START = "2022Q2"
MORTGAGE_SPREAD = 1.0     # p.p. sobre a Euribor (ordem de grandeza dos spreads recentes em Portugal)
MORTGAGE_YEARS = 30


def region_codes(sales: pd.DataFrame | None) -> dict[str, str]:
    """dico -> código NUTS II (primeiros 2 caracteres do geocod do INE)."""
    if sales is None or sales.empty or "geocod" not in sales:
        return {}
    m = sales[sales["level"] == "municipality"].dropna(subset=["dico", "geocod"]).drop_duplicates("dico")
    return {str(d): str(g)[:2] for d, g in zip(m["dico"], m["geocod"]) if len(str(g)) >= 7}


def _band_label(lo, hi) -> str:
    return f"{lo}–{hi} km" if hi != math.inf else f"mais de {lo} km"


# ---------------------------------------------------------------- regimes
def regimes(hpi: pd.DataFrame | None, hpi_real: pd.DataFrame | None = None, min_len: int = 6,
            max_segments: int = 6) -> dict | None:
    if hpi is None or len(hpi) < 2 * min_len:
        return None
    h = hpi.dropna(subset=["value"]).sort_values("period")
    per = h["period"].astype(str).tolist()
    y = np.log(h["value"].astype(float).to_numpy())
    n = len(y)
    t = np.arange(n, dtype=float)
    cs = {k: np.concatenate([[0.0], np.cumsum(v)]) for k, v in
          {"1": np.ones(n), "t": t, "tt": t * t, "y": y, "yy": y * y, "ty": t * y}.items()}

    def cost(i, j):
        m = cs["1"][j] - cs["1"][i]
        st, stt, sy = cs["t"][j] - cs["t"][i], cs["tt"][j] - cs["tt"][i], cs["y"][j] - cs["y"][i]
        syy, sty = cs["yy"][j] - cs["yy"][i], cs["ty"][j] - cs["ty"][i]
        vtt, vty, vyy = stt - st * st / m, sty - st * sy / m, syy - sy * sy / m
        return max(vyy - (vty * vty / vtt if vtt > 0 else 0.0), 0.0)

    inf = float("inf")
    best = {0: {0: (0.0, None)}}
    results = {}
    for k in range(1, max_segments + 1):
        best[k] = {}
        for j in range(k * min_len, n + 1):
            cands = [(best[k - 1][i][0] + cost(i, j), i) for i in best[k - 1] if j - i >= min_len]
            if cands:
                best[k][j] = min(cands)
        if n in best[k]:
            sse = best[k][n][0]
            results[k] = n * math.log(max(sse, 1e-12) / n) + 3 * k * math.log(n)
    if not results:
        return None
    k = min(results, key=results.get)
    bounds, j = [], n
    for kk in range(k, 0, -1):
        i = best[kk][j][1]
        bounds.append((i, j))
        j = i
    bounds.reverse()
    real = None
    if hpi_real is not None and len(hpi_real):
        real = pd.Series(np.log(hpi_real["value"].astype(float).to_numpy()), index=hpi_real["period"].astype(str))
    segs, fit = [], []
    for si, (i, j) in enumerate(bounds):
        b, a = np.polyfit(t[i:j], y[i:j], 1)
        seg = {"start": per[i], "end": per[j - 1], "quarters": j - i, "growth_ann": float(math.exp(4 * b) - 1)}
        if real is not None:
            rr = real.reindex(per[i:j]).dropna()
            if len(rr) >= 4:
                rb = np.polyfit(np.array([per.index(p) for p in rr.index], dtype=float), rr.to_numpy(), 1)[0]
                seg["growth_ann_real"] = float(math.exp(4 * rb) - 1)
        segs.append(seg)
        fit += [[per[x], round(float(math.exp(a + b * t[x])), 2), si] for x in range(i, j)]
    return {"segments": segs, "fit": fit, "n_segments": k, "series": [[p, round(float(v), 2)] for p, v in
                                                                      zip(per, h["value"].astype(float))]}


# ---------------------------------------------------------------- tipologias
def _kmeans(x: np.ndarray, k: int, seed: int = 0, n_init: int = 20, iters: int = 200):
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(n_init):
        c = [x[rng.integers(len(x))]]
        for _ in range(1, k):
            d2 = np.min(((x[:, None, :] - np.array(c)[None]) ** 2).sum(-1), axis=1)
            c.append(x[rng.choice(len(x), p=d2 / d2.sum())] if d2.sum() > 0 else x[rng.integers(len(x))])
        cen = np.array(c)
        for _ in range(iters):
            lab = np.argmin(((x[:, None, :] - cen[None]) ** 2).sum(-1), axis=1)
            new = np.array([x[lab == j].mean(0) if (lab == j).any() else cen[j] for j in range(k)])
            if np.allclose(new, cen):
                break
            cen = new
        inertia = float(((x - cen[lab]) ** 2).sum())
        if best is None or inertia < best[0]:
            best = (inertia, lab, cen)
    return best[1], best[2]


def silhouette(x: np.ndarray, lab: np.ndarray) -> float:
    d = np.sqrt(((x[:, None, :] - x[None]) ** 2).sum(-1))
    s = []
    for i in range(len(x)):
        same = lab == lab[i]
        if same.sum() <= 1:
            s.append(0.0)
            continue
        a = d[i, same].sum() / (same.sum() - 1)
        b = min(d[i, lab == c].mean() for c in np.unique(lab) if c != lab[i])
        s.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
    return float(np.mean(s))


def _cluster_name(lvl: float, g_a: float, g_b: float, med_a: float, med_b: float, split: str) -> str:
    level = "Mais caros" if lvl > 0.25 else "Mais baratos" if lvl < -0.25 else "Preço médio"
    if g_a < 0.02 and g_b > med_b:
        dyn = f"arranque tardio (parados até {split}, a subir depois)"
    elif g_b > g_a + 0.03:
        dyn = "subida a acelerar"
    elif g_b < g_a - 0.03:
        dyn = f"boom até {split}, agora a abrandar" if g_a > med_a + 0.03 else "subida a abrandar"
    else:
        dyn = "subida estável e " + ("forte" if g_b > med_b + 0.02 else "fraca" if g_b < med_b - 0.02 else "moderada")
    return f"{level}, {dyn}"


def typologies(sales: pd.DataFrame, valuation: pd.DataFrame | None = None, names: dict[str, str] | None = None,
               k_range=(3, 4, 5, 6), seed: int = 0) -> tuple[dict | None, dict]:
    s = fc.log_grid(sales, fc.q_index)
    if s is None:
        return None, {}
    qmax = int(max(k for k in s.columns if s[k].notna().any()))
    q0 = int(s.columns.min())
    qs = fc.q_index(int(RATE_HIKE_START[:4]) * 100 + int(RATE_HIKE_START[-1]))
    if qs - q0 < 4 or qmax - qs < 4:
        qs = (q0 + qmax) // 2
    need = s[[q0, qs, qmax]].notna().all(axis=1)
    s = s[need]
    if len(s) < 20:
        return None, {}
    lvl = s[qmax] - s[qmax].median()
    g_a = np.exp((s[qs] - s[q0]) * 4 / (qs - q0)) - 1
    g_b = np.exp((s[qmax] - s[qs]) * 4 / (qmax - qs)) - 1
    raw = pd.DataFrame({"lvl": lvl, "g_a": g_a, "g_b": g_b})
    w = raw.clip(raw.quantile(0.025), raw.quantile(0.975), axis=1)
    z = ((w - w.mean()) / w.std(ddof=0).replace(0, 1)).to_numpy()
    fits = {}
    for k in k_range:
        if len(z) > 3 * k:
            lab, cen = _kmeans(z, k, seed)
            fits[k] = (silhouette(z, lab), lab, cen)
    if not fits:
        return None, {}
    k = max(fits, key=lambda kk: fits[kk][0])
    sil, lab, cen = fits[k]
    v3, _ = fc.valuation_grids(valuation)
    med_a, med_b = float(raw["g_a"].median()), float(raw["g_b"].median())
    split_pt = fc.q_label(qs).replace("Q", "T")
    clusters, per = [], {}
    order = np.argsort([-raw["lvl"][lab == c].median() for c in range(k)])
    for rank, c in enumerate(order):
        mem = raw.index[lab == c]
        sub = raw.loc[mem]
        dist = ((z[lab == c] - cen[c]) ** 2).sum(1)
        typical = [str(d) for d in mem[np.argsort(dist)][:6]]
        item = {"id": rank + 1, "n": int(len(mem)),
                "name": _cluster_name(float(sub["lvl"].median()), float(sub["g_a"].median()),
                                      float(sub["g_b"].median()), med_a, med_b, split_pt),
                "price_median": float(np.exp(s.loc[mem, qmax]).median()),
                "level_vs_median": float(np.exp(sub["lvl"].median()) - 1),
                "growth_before": float(sub["g_a"].median()), "growth_after": float(sub["g_b"].median()),
                "examples": [{"dico": d, "name": (names or {}).get(d, d)} for d in typical]}
        if v3 is not None:
            yr = {y: np.log(np.exp(v3.loc[:, [c2 for c2 in v3.columns if c2 // 12 == y]]).mean(axis=1))
                  for y in (2011, 2013, 2019)}
            crisis = (yr[2013] - yr[2011]).reindex(mem).dropna()
            recov = (yr[2019] - yr[2013]).reindex(mem).dropna()
            if len(crisis) >= 3:
                item["valuation_2011_2013"] = float(np.exp(crisis.median()) - 1)
                item["valuation_2011_2013_n"] = int(len(crisis))
            if len(recov) >= 3:
                item["valuation_2013_2019"] = float(np.exp(recov.median()) - 1)
                item["valuation_2013_2019_n"] = int(len(recov))
        clusters.append(item)
        for d in mem:
            per[str(d)] = {"typology": rank + 1}
    seen = {}
    for cl in clusters:
        seen[cl["name"]] = seen.get(cl["name"], 0) + 1
        if seen[cl["name"]] > 1:
            cl["name"] += f" ({seen[cl['name']]})"
    for d, v in per.items():
        v["typology_name"] = clusters[v["typology"] - 1]["name"]
    summary = {"k": k, "silhouette": sil, "split": fc.q_label(qs), "start": fc.q_label(q0), "end": fc.q_label(qmax),
               "n": int(len(raw)), "clusters": clusters,
               "silhouette_by_k": {str(kk): round(v[0], 3) for kk, v in fits.items()}}
    return summary, per


# ---------------------------------------------------------------- distâncias / propagação
def metro_distances(spatial: pd.DataFrame, regions: dict[str, str]) -> pd.DataFrame | None:
    if spatial is None or spatial.empty or not all(m in set(spatial["dico"]) for m in METROS):
        return None
    sp = spatial.set_index("dico")
    out = pd.DataFrame(index=sp.index)
    for code, name in METROS.items():
        out[name] = haversine_km(sp["lon"], sp["lat"], sp.at[code, "lon"], sp.at[code, "lat"])
    out["metro"] = out[list(METROS.values())].idxmin(axis=1)
    out["dist_km"] = out[list(METROS.values())].min(axis=1)
    out["island"] = [regions.get(d) in ISLANDS for d in out.index]
    return out


def ripple(valuation: pd.DataFrame | None, sales: pd.DataFrame | None, dist: pd.DataFrame | None,
           max_lag: int = 24, min_points: int = 60) -> dict | None:
    if dist is None:
        return None
    out: dict = {"bands": []}
    main = dist[~dist["island"] & ~dist.index.isin(list(METROS))]
    s = fc.log_grid(sales, fc.q_index) if sales is not None else None
    if s is not None:
        qmax = int(max(k for k in s.columns if s[k].notna().any()))
        q0 = int(s.columns.min())
        qs = fc.q_index(int(RATE_HIKE_START[:4]) * 100 + int(RATE_HIKE_START[-1]))
        if qs - q0 >= 4 and qmax - qs >= 4:
            out["split"], out["start"], out["end"] = fc.q_label(qs), fc.q_label(q0), fc.q_label(qmax)
            g_a = (np.exp((s[qs] - s[q0]) * 4 / (qs - q0)) - 1).rename("g_a")
            g_b = (np.exp((s[qmax] - s[qs]) * 4 / (qmax - qs)) - 1).rename("g_b")
            gg = main.join(g_a, how="inner").join(g_b, how="inner")
        else:
            gg = None
    else:
        gg = None
    v3, _ = fc.valuation_grids(valuation)
    corr_by_band = {}
    if v3 is not None and all(m in v3.index for m in METROS):
        g12 = v3 - v3.shift(12, axis=1)
        for d, row in main.iterrows():
            if d not in g12.index:
                continue
            gi = g12.loc[d]
            gm = g12.loc[[k for k, v in METROS.items() if v == row["metro"]][0]]
            curve = []
            for lag in range(max_lag + 1):
                pair = pd.concat([gi, gm.shift(lag)], axis=1).dropna()
                curve.append(pair.iloc[:, 0].corr(pair.iloc[:, 1]) if len(pair) >= min_points else np.nan)
            if not np.all(np.isnan(curve)):
                corr_by_band.setdefault(_band_of(row["dist_km"]), []).append(curve)
    for lo, hi in BANDS:
        lbl = _band_label(lo, hi)
        members = main[(main["dist_km"] >= lo) & (main["dist_km"] < hi)]
        b = {"band": lbl, "n": int(len(members))}
        if gg is not None:
            gm = gg[(gg["dist_km"] >= lo) & (gg["dist_km"] < hi)]
            if len(gm) >= 3:
                b["growth_before"], b["growth_after"], b["n_growth"] = float(gm["g_a"].median()), float(gm["g_b"].median()), int(len(gm))
        curves = corr_by_band.get(lbl)
        if curves and len(curves) >= 3:
            mc = np.nanmean(np.array(curves, dtype=float), axis=0)
            b["best_lag_months"], b["peak_corr"], b["n_lag"] = int(np.nanargmax(mc)), float(np.nanmax(mc)), len(curves)
            b["corr_curve"] = [round(float(v), 3) for v in mc]
        out["bands"].append(b)
    return out if any(len(b) > 2 for b in out["bands"]) else None


def _band_of(dist: float) -> str:
    for lo, hi in BANDS:
        if lo <= dist < hi:
            return _band_label(lo, hi)
    return _band_label(*BANDS[-1])


# ---------------------------------------------------------------- valor justo
def fair_value(feats: pd.DataFrame | None, spatial: pd.DataFrame | None, dist: pd.DataFrame | None,
               regions: dict[str, str], n_folds: int = 10, seed: int = 0) -> tuple[dict | None, dict]:
    need = ["price", "income", "density", "ageing_index"]
    if feats is None or any(c not in feats or feats[c].notna().sum() < 30 for c in need):
        return None, {}
    df = feats.assign(dico=feats["dico"].astype(str)).set_index("dico")
    x = pd.DataFrame(index=df.index)
    x["log_income"] = np.log(df["income"].where(df["income"] > 0))
    x["log_density"] = np.log(df["density"].where(df["density"] > 0))
    x["log_ageing"] = np.log(df["ageing_index"].where(df["ageing_index"] > 0))
    if spatial is not None and not spatial.empty and "migration_balance" in df and df["migration_balance"].notna().sum() >= 30:
        pop = df["density"] * spatial.set_index("dico")["area_km2"].reindex(df.index)
        mr = df["migration_balance"] / pop * 1000
        x["mig_rate"] = mr.clip(mr.quantile(0.025), mr.quantile(0.975))
    if dist is not None:
        x["log_dist"] = np.log1p(dist["dist_km"].reindex(df.index))
    if spatial is not None and not spatial.empty and spatial["coastal"].any():
        x["coastal"] = spatial.set_index("dico")["coastal"].reindex(df.index).astype(float)
    if (spatial is not None and not spatial.empty and "tourism_nights" in df
            and df["tourism_nights"].notna().sum() >= 30):
        pop = df["density"] * spatial.set_index("dico")["area_km2"].reindex(df.index)
        # concelhos sem dormidas publicadas (sigilo/sem oferta) contam como 0: quase sempre é pouco turismo
        x["log_tourism"] = np.log1p((df["tourism_nights"].fillna(0) / pop).clip(lower=0))
    reg = pd.Series({d: regions.get(d, "?") for d in df.index})
    dummies = pd.get_dummies(reg, prefix="r", dtype=float)
    if dummies.shape[1] > 1:
        dummies = dummies.drop(columns=dummies.sum().idxmax())
    data = x.join(dummies).assign(y=np.log(df["price"].where(df["price"] > 0))).dropna()
    if len(data) < 30:
        return None, {}
    cols = [c for c in data.columns if c != "y"]
    xm, y = data[cols].to_numpy(float), data["y"].to_numpy(float)
    full = fc.ridge_fit(xm, y, lam=0.01)
    oof = np.empty(len(y))
    folds = np.random.default_rng(seed).permutation(len(y)) % n_folds
    for k in range(n_folds):
        m = fc.ridge_fit(xm[folds != k], y[folds != k], lam=0.01)
        oof[folds == k] = fc.ridge_predict(m, xm[folds == k])
    sst = float(((y - y.mean()) ** 2).sum())
    r2_in = 1 - float(((y - fc.ridge_predict(full, xm)) ** 2).sum()) / sst
    r2_cv = 1 - float(((y - oof) ** 2).sum()) / sst
    raw_b = dict(zip(cols, full["b"] / full["sd"]))
    effects = []
    for c, label, kind in (("log_income", "rendimento médio", "elasticity"), ("log_density", "densidade populacional", "elasticity"),
                           ("log_ageing", "índice de envelhecimento", "elasticity"),
                           ("mig_rate", "saldo migratório (+1 por mil habitantes)", "per_unit"),
                           ("coastal", "estar no litoral", "per_unit"),
                           ("log_tourism", "dormidas turísticas por habitante (+1, em log)", "per_unit"),
                           ("log_dist", "distância a Lisboa/Porto", "elasticity")):
        if c in raw_b:
            b = float(raw_b[c])
            effects.append({"feature": c, "label": label, "kind": kind,
                            "effect_10pct": float(1.1 ** b - 1) if kind == "elasticity" else None,
                            "effect_unit": float(math.exp(b) - 1) if kind == "per_unit" else None})
    gap = pd.Series(np.exp(y - oof) - 1, index=data.index)
    fair = pd.Series(np.exp(oof), index=data.index)
    per = {d: {"fv_gap": round(float(gap[d]), 4), "fv_price": round(float(fair[d]), 1)} for d in data.index}

    def top(asc):
        sel = gap.sort_values(ascending=asc).head(10)
        return [{"dico": d, "name": str(df.at[d, "name"]), "price": float(df.at[d, "price"]), "fv_price": float(fair[d]),
                 "gap": float(g), "volatile": bool(df.at[d, "volatile"]) if "volatile" in df else False,
                 "coastal": bool(x.at[d, "coastal"]) if "coastal" in x else None} for d, g in sel.items()]

    summary = {"n": int(len(data)), "r2_in": r2_in, "r2_cv": r2_cv, "effects": effects,
               "regions_as_controls": dummies.shape[1] > 0, "top_above": top(False), "top_below": top(True),
               "share_within_20pct": float((gap.abs() <= 0.2).mean())}
    return summary, per


# ---------------------------------------------------------------- procura
def demand(feats: pd.DataFrame | None) -> dict | None:
    """Procura externa (prémio pago por compradores com domicílio no estrangeiro) e volume (avaliações bancárias)."""
    if feats is None:
        return None
    out: dict = {}
    if "foreign_premium" in feats:
        fp = feats.dropna(subset=["foreign_premium"])
        if len(fp) >= 5:
            top = fp.sort_values("foreign_premium", ascending=False).head(10)
            out["foreign"] = {"n": int(len(fp)), "median_premium": float(fp["foreign_premium"].median()),
                              "share_above": float((fp["foreign_premium"] > 0).mean()),
                              "top": [{"dico": str(r.dico), "name": str(r.name), "premium": float(r.foreign_premium),
                                       "price_foreign": float(r.price_foreign), "price_domestic": float(r.price_domestic)}
                                      for r in top.itertuples()]}
    if "companies_premium" in feats:
        cp = feats.dropna(subset=["companies_premium"])
        if len(cp) >= 5:
            top = cp.sort_values("companies_premium", ascending=False).head(10)
            out["companies"] = {"n": int(len(cp)), "median_premium": float(cp["companies_premium"].median()),
                                "share_above": float((cp["companies_premium"] > 0).mean()),
                                "top": [{"dico": str(r.dico), "name": str(r.name), "premium": float(r.companies_premium),
                                         "price_companies": float(r.price_companies),
                                         "price_households": float(r.price_households)} for r in top.itertuples()]}

    def volume(col):
        if col not in feats:
            return None
        g = f"{col}_growth_1y"
        vc = feats.dropna(subset=[col, g])
        vc = vc[np.isfinite(vc[g])]
        if len(vc) < 5:
            return None
        now, ago = float(vc[col].sum()), float((vc[col] / (1 + vc[g])).sum())
        return {"n": int(len(vc)), "total": now, "total_growth_1y": now / ago - 1 if ago > 0 else None,
                "median_growth_1y": float(vc[g].median()), "share_falling": float((vc[g] < 0).mean())}

    if (v := volume("val_count")) is not None:
        out["volume"] = v
        by_type = {k: volume(c) for k, c in (("apartments", "val_count_apt"), ("houses", "val_count_house"))}
        if any(by_type.values()):
            out["volume"]["by_type"] = {k: x for k, x in by_type.items() if x}
    return out or None


# ---------------------------------------------------------------- juros
def _annuity_capacity(rate: float, years: int) -> float:
    n, r = years * 12, rate / 12
    return float(n) if abs(r) < 1e-12 else (1 - (1 + r) ** (-n)) / r


def rate_scenarios(euribor: pd.DataFrame | None, hpi: pd.DataFrame | None, shocks=(-1.0, 1.0),
                   spread: float = MORTGAGE_SPREAD, years: int = MORTGAGE_YEARS, n_boot: int = 1000,
                   block: int = 8, seed: int = 0, mortgage: pd.DataFrame | None = None) -> dict | None:
    e = fc.euribor_series(euribor)
    if e is None or e.empty:
        return None
    e_now, e_month = float(e.iloc[-1]), fc.m_label(int(e.index[-1]))
    source = "assumed"
    m = fc.euribor_series(mortgage)
    if m is not None and len(m) and int(m.index[-1]) in e.index:
        obs = float(m.iloc[-1]) - float(e[int(m.index[-1])])
        if 0 <= obs <= 4:          # sanidade: se a série não for o que se espera, mantém o pressuposto
            spread, source = obs, f"BCE ({fc.m_label(int(m.index[-1]))})"
    r0 = (e_now + spread) / 100
    out = {"euribor_now": e_now, "euribor_month": e_month, "spread": spread, "spread_source": source,
           "years": years, "rate_now": r0 * 100, "shocks": []}
    if source != "assumed":
        out["mortgage_rate_now"] = float(m.iloc[-1])
    beta = ci = None
    if hpi is not None and len(hpi) >= 32:
        h = hpi.dropna(subset=["value"]).assign(qi=lambda d: [int(str(p)[:4]) * 4 + int(str(p)[-1]) - 1 for p in d["period"]])
        hs = pd.Series(np.log(h["value"].astype(float).to_numpy()), index=h["qi"].to_numpy()).sort_index()
        eq = e.groupby(e.index // 3).mean()
        rows = [(hs[t + 4] - hs[t], eq.get(t + 4, np.nan) - eq.get(t, np.nan), hs[t] - hs[t - 4])
                for t in hs.index if t + 4 in hs.index and t - 4 in hs.index]
        arr = np.array([r for r in rows if not np.isnan(r).any()])
        if len(arr) >= 24:
            def ols(a):
                xx = np.column_stack([np.ones(len(a)), a[:, 1], a[:, 2]])
                return float(np.linalg.lstsq(xx, a[:, 0], rcond=None)[0][1])
            beta = ols(arr)
            rng = np.random.default_rng(seed)
            nb = int(math.ceil(len(arr) / block))
            boots = []
            for _ in range(n_boot):
                starts = rng.integers(0, len(arr) - block + 1, nb)
                boots.append(ols(np.concatenate([arr[s:s + block] for s in starts])[:len(arr)]))
            ci = (float(np.quantile(boots, 0.05)), float(np.quantile(boots, 0.95)))
            out.update({"beta": beta, "beta_ci90": ci, "n_obs": int(len(arr)),
                        "hpi_start": str(h["period"].iloc[0]), "hpi_end": str(h["period"].iloc[-1])})
    credible = beta is not None and ci[1] < 0
    out["credible"] = credible
    for s in shocks:
        cap = _annuity_capacity(r0 + s / 100, years) / _annuity_capacity(r0, years) - 1
        item = {"shock": s, "capacity_change": cap, "payment_change": 1 / (1 + cap) - 1}
        if credible:
            item["price_effect_12m"] = float(math.exp(beta * s) - 1)
            item["price_effect_12m_ci90"] = sorted([float(math.exp(ci[0] * s) - 1), float(math.exp(ci[1] * s) - 1)])
        out["shocks"].append(item)
    return out


# ---------------------------------------------------------------- orquestração
LIMITS = [
    "Os preços da habitação são difíceis de prever nos pontos de viragem: os intervalos mostram a incerteza "
    "típica do passado recente, não o pior cenário possível.",
    "O preço do INE é uma mediana móvel de 12 meses: suaviza e atrasa a realidade. Parte do que parece "
    "previsível é essa inércia — por isso o modelo é sempre comparado com a regra «continua o ritmo».",
    "A avaliação bancária (que permite estimar o presente) não é o preço de transação: só cobre casas com "
    "crédito, é mais suave, e pode divergir.",
    "O backtest das vendas cobre poucos anos (dados do INE por concelho desde 2019) e um único ciclo de juros; "
    "o erro futuro pode ser maior do que o medido.",
    "Rendas: só há 6 anos de dados anuais por concelho — previsão de confiança baixa.",
    "O backtest usa as séries tal como estão hoje (com revisões), não os valores publicados na altura — "
    "isso favorece ligeiramente os resultados face a um uso em tempo real.",
    "Valor justo: um desvio positivo pode refletir praia, turismo ou qualidade das casas, que o modelo não vê. "
    "Não é prova de bolha.",
    "Nada disto altera os scores do painel, nem é aconselhamento financeiro.",
]


def build(frames: dict, macro_frames: dict, feats: pd.DataFrame | None, geojson: dict | None,
          hpi: pd.DataFrame | None, hpi_real: pd.DataFrame | None, today: dt.date | None = None,
          demo: bool = False) -> tuple[dict, dict[str, dict]]:
    from . import geo
    today = today or dt.date.today()

    def muni(df):
        return None if df is None or df.empty else df[df["level"] == "municipality"].dropna(subset=["dico", "value"])

    sales = muni(frames.get("sales_price_12m"))
    rent = muni(frames.get("rent_new_contracts"))
    valuation = frames.get("bank_valuation")
    euribor = macro_frames.get("euribor_12m")
    regions = region_codes(sales)
    region_names = {d: NUTS2.get(c, c) for d, c in regions.items()}
    names = {} if sales is None else dict(zip(sales["dico"].astype(str), sales["geoname"]))
    spatial, nbrs = geo.spatial_index(geojson)
    dist = metro_distances(spatial, regions)

    out: dict = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "demo": demo,
                 "build_date": today.isoformat(), "limits": LIMITS, "errors": {}}
    per: dict[str, dict] = {}

    def merge(p):
        for d, v in (p or {}).items():
            per.setdefault(str(d), {}).update(v)

    def part(name, fn):
        try:
            res = fn()
            if isinstance(res, tuple):
                summary, p = res
                merge(p)
            else:
                summary = res
            if summary is not None:
                out[name] = summary
        except Exception as e:  # noqa: BLE001
            log.warning("perspetivas/%s falhou: %s", name, e)
            out["errors"][name] = str(e)[:200]

    if sales is not None:
        part("sales", lambda: fc.forecast_sales(sales, valuation, euribor, nbrs, region_names, today))
        part("typologies", lambda: typologies(sales, valuation, names))
    part("rent", lambda: fc.forecast_rent(rent, sales, valuation, today))
    part("regimes", lambda: regimes(hpi, hpi_real))
    part("ripple", lambda: ripple(valuation, sales, dist))
    part("fair_value", lambda: fair_value(feats, spatial, dist, regions))
    part("demand", lambda: demand(feats))
    part("rates", lambda: rate_scenarios(euribor, hpi, mortgage=macro_frames.get("mortgage_rate_pt")))
    # O volume de avaliações (variação anual) entra só nas previsões por tipo: no backtest melhorou-as em todos os
    # horizontes (15 anos de histórico), mas não melhorou a previsão das vendas do INE (só desde 2019). Ver README.
    for key, vkey, prefix in (("valuation_apartments", "valuation_count_apartments", "apt"),
                              ("valuation_houses", "valuation_count_houses", "house")):
        q = monthly_to_quarterly_muni(muni(frames.get(key)))
        if q is not None:
            part(f"fc_{prefix}", lambda q=q, prefix=prefix, vol=muni(frames.get(vkey)): _prefixed(
                fc.forecast_sales(q, None, euribor, nbrs, region_names, today, volume=vol), prefix))
    if dist is not None:
        merge({d: {"dist_metro_km": round(float(r["dist_km"]), 1), "metro": r["metro"]}
               for d, r in dist.iterrows() if not r["island"]})
    if not spatial.empty:
        merge({str(d): {"coastal": bool(c)} for d, c in zip(spatial["dico"], spatial["coastal"])})
        if feats is not None and "tourism_nights" in feats:
            area = spatial.set_index("dico")["area_km2"]
            pop = feats.set_index(feats["dico"].astype(str))["density"] * area
            tpc = (feats.set_index(feats["dico"].astype(str))["tourism_nights"] / pop).dropna()
            merge({d: {"tourism_pc": round(float(v), 2)} for d, v in tpc.items() if np.isfinite(v)})
    return sanitize(out), sanitize(per)


def monthly_to_quarterly_muni(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Mensal por concelho -> média trimestral (pelo menos 2 dos 3 meses), no formato das vendas."""
    if df is None or df.empty:
        return None
    y, mth = df["sort_key"] // 100, df["sort_key"] % 100
    d = df.assign(q=y * 100 + (mth - 1) // 3 + 1)
    g = d.groupby(["dico", "q"])["value"].agg(["mean", "count"]).reset_index()
    g = g[g["count"] >= 2]
    if g.empty:
        return None
    return pd.DataFrame({"dico": g["dico"], "sort_key": g["q"], "period": [f"{k // 100}Q{k % 100}" for k in g["q"]],
                         "value": g["mean"], "level": "municipality"})


def _prefixed(res: tuple[dict | None, dict], prefix: str) -> tuple[dict | None, dict]:
    """Previsão por tipo de casa: só os campos de resumo, com prefixo (ex.: apt_fc_growth_12m)."""
    summary, per = res
    keep = ("fc_period", "fc_price", "fc_lo80", "fc_hi80", "fc_growth_12m", "fc_mae")
    return summary, {d: {f"{prefix}_{k}": v[k] for k in keep if k in v} for d, v in per.items()}


def sanitize(obj):
    """JSON válido para o browser: NaN/inf -> null, tipos numpy -> Python."""
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return None if not math.isfinite(float(obj)) else float(obj)
    return obj
