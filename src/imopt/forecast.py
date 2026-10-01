"""Previsões: preço de venda por concelho (nowcast + até 12 meses) e renda a 1 ano.

Ver README, secção "Perspetivas". Regras fixadas antes de olhar para resultados:

- Previsão DIRETA por horizonte h (trimestres depois do último trimestre publicado pelo INE),
  com um modelo linear regularizado (ridge, mínimos quadrados ponderados pela volatilidade de cada
  concelho) comum a todos os concelhos: concelhos com pouca informação beneficiam do que se aprende
  nos outros.
- Sinais, todos conhecidos na data da previsão: inércia do preço (último trimestre e último ano);
  avaliação bancária do concelho e do país desde o fim da janela das vendas (publicada com menos
  atraso do que o preço de venda — é o que permite estimar o presente, "nowcast"); propagação
  espacial (média dos concelhos vizinhos); convergência (nível do preço face à mediana); variação da
  Euribor 12M.
- Sem look-ahead: em cada origem do backtest, o modelo só é treinado com pares (origem, alvo) cujo
  alvo já era conhecido nessa data, e a avaliação bancária é cortada com o mesmo avanço (em meses)
  que existe hoje sobre o preço de venda.
- Intervalos conformes normalizados: quantis dos erros fora da amostra divididos pela volatilidade de
  cada concelho, reescalados pela volatilidade do concelho a prever. A cobertura é medida no próprio
  backtest, só com erros de origens anteriores (conformal sequencial).
- Comparação obrigatória com duas previsões ingénuas: "fica igual" e "continua o ritmo do último ano".
- O preço do INE é uma mediana móvel de 12 meses: parte da inércia é mecânica (a janela vai-se
  renovando). A previsão ingénua "continua o ritmo" já capta isso — é por isso que tem de ser batida.
"""
from __future__ import annotations

import datetime as dt
import logging
import math

import numpy as np
import pandas as pd

log = logging.getLogger("imopt")

RIDGE_LAMBDA = 0.05          # penalização relativa (5% de encolhimento para variáveis ortogonais)
MIN_TRAIN_ROWS = 300         # mínimo de linhas para treinar numa origem do backtest (venda)
MIN_TRAIN_ROWS_RENT = 100
MIN_CAL_RESID = 60           # mínimo de erros anteriores para calibrar um intervalo
CAL_WINDOW = 8               # só as 8 origens mais recentes calibram os intervalos (as primeiras
                             # origens do backtest têm modelos treinados com muito poucos dados)
MAX_HORIZON = 8
SIGMA_WINDOW = 12            # trimestres usados para medir a volatilidade de cada concelho
QUANTS = {"lo80": 0.10, "lo50": 0.25, "hi50": 0.75, "hi80": 0.90}
SALES_FEATURES = ["s_mom1", "s_mom4", "v_lead", "v_mom", "nat_lead", "nb_mom4", "rel_level", "eur_chg", "vol_chg"]
RENT_FEATURES = ["r_mom", "s_yoy", "yield_gap", "v_lead"]
FEATURE_LABELS = {
    "s_mom1": "variação do preço no último trimestre",
    "s_mom4": "variação do preço no último ano",
    "v_lead": "avaliação bancária do concelho desde o último preço publicado",
    "v_mom": "avaliação bancária do concelho no último ano",
    "nat_lead": "avaliação bancária nacional desde o último preço publicado",
    "nb_mom4": "variação do preço nos concelhos vizinhos",
    "rel_level": "nível do preço face à mediana (convergência)",
    "eur_chg": "variação da Euribor 12M no último ano",
    "vol_chg": "variação anual do número de avaliações bancárias (volume)",
    "r_mom": "variação da renda no último ano",
    "s_yoy": "variação do preço de venda no último ano",
    "yield_gap": "rendibilidade face à mediana",
}


# ---------------------------------------------------------------- índices de tempo
def q_index(sort_key: int) -> int:
    y, q = divmod(int(sort_key), 100)
    return y * 4 + q - 1


def q_label(qi: int) -> str:
    return f"{qi // 4}Q{qi % 4 + 1}"


def m_index(sort_key: int) -> int:
    y, m = divmod(int(sort_key), 100)
    return y * 12 + m - 1


def m_label(mi: int) -> str:
    return f"{mi // 12}-{mi % 12 + 1:02d}"


def q_end_month(qi: int) -> int:
    return (qi // 4) * 12 + (qi % 4) * 3 + 2


def _month_of_label(p: str) -> int:
    return int(p[:4]) * 12 + int(p[5:7]) - 1


# ---------------------------------------------------------------- grelhas
def log_grid(df: pd.DataFrame | None, index_fn) -> pd.DataFrame | None:
    """dico x período (índice inteiro contínuo) com log(valor)."""
    if df is None or df.empty:
        return None
    d = df.dropna(subset=["dico", "value"])
    d = d[d["value"].astype(float) > 0]
    if d.empty:
        return None
    g = pd.DataFrame({"dico": d["dico"].astype(str).values, "k": d["sort_key"].map(index_fn).values,
                      "v": np.log(d["value"].astype(float).values)})
    p = g.pivot_table(index="dico", columns="k", values="v", aggfunc="last")
    return p.reindex(columns=range(int(p.columns.min()), int(p.columns.max()) + 1))


def valuation_grids(valuation: pd.DataFrame | None) -> tuple[pd.DataFrame | None, pd.Series | None]:
    """Avaliação bancária mensal -> média móvel de 3 meses (em log), por concelho e nacional."""
    if valuation is None or valuation.empty:
        return None, None

    def smooth(frame):
        g = log_grid(frame, m_index)
        if g is None:
            return None
        lv = np.exp(g).T.rolling(3, min_periods=2).mean().T
        return np.log(lv)

    muni = smooth(valuation[valuation["level"] == "municipality"])
    nat = smooth(valuation[valuation["level"] == "national"].assign(dico="PT"))
    return muni, (nat.iloc[0] if nat is not None and len(nat) else None)


def euribor_series(euribor: pd.DataFrame | None) -> pd.Series | None:
    if euribor is None or euribor.empty:
        return None
    s = pd.Series(euribor["value"].astype(float).values, index=[_month_of_label(str(p)) for p in euribor["period"]])
    return s[~s.index.duplicated(keep="last")].sort_index()


def _c(df: pd.DataFrame | None, k: int, index=None) -> pd.Series:
    if df is None:
        return pd.Series(np.nan, index=index)
    s = df[k] if k in df.columns else pd.Series(np.nan, index=df.index)
    return s.reindex(index) if index is not None else s


def _g(s: pd.Series | None, k: int) -> float:
    if s is None:
        return np.nan
    return float(s.get(k, np.nan))


def adjacency(dicos: pd.Index, nbrs: dict[str, list[str]] | None) -> np.ndarray | None:
    if not nbrs:
        return None
    pos = {d: i for i, d in enumerate(dicos)}
    a = np.zeros((len(dicos), len(dicos)))
    for d, ns in nbrs.items():
        if d in pos:
            for n in ns:
                if n in pos:
                    a[pos[d], pos[n]] = 1.0
    return a if a.any() else None


def nb_mean(x: pd.Series, a: np.ndarray | None) -> pd.Series:
    if a is None:
        return pd.Series(np.nan, index=x.index)
    v = x.to_numpy(float)
    ok = ~np.isnan(v)
    num, den = a @ np.where(ok, v, 0.0), a @ ok.astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return pd.Series(np.where(den > 0, num / np.where(den > 0, den, 1), np.nan), index=x.index)


def robust_sigma(s: pd.DataFrame, q: int, window: int = SIGMA_WINDOW) -> pd.Series:
    """Escala robusta (MAD) das variações trimestrais até à origem `q` (inclusive)."""
    cols = [k for k in range(q - window, q + 1) if k in s.columns]
    d = s[cols].diff(axis=1).iloc[:, 1:]
    mad = d.sub(d.median(axis=1), axis=0).abs().median(axis=1) * 1.4826
    good = mad[mad > 0]
    floor = float(np.nanpercentile(good, 10)) if len(good) else 0.01
    return mad.clip(lower=max(floor, 1e-3)).fillna(float(good.median()) if len(good) else 0.02)


# ---------------------------------------------------------------- regressão
def ridge_fit(x: np.ndarray, y: np.ndarray, w: np.ndarray | None = None, lam: float = RIDGE_LAMBDA) -> dict:
    w = np.ones(len(y)) if w is None else w / w.mean()
    mu = np.average(x, axis=0, weights=w)
    sd = np.sqrt(np.average((x - mu) ** 2, axis=0, weights=w))
    sd[sd < 1e-12] = 1.0
    z = (x - mu) / sd
    ym = float(np.average(y, weights=w))
    sw = np.sqrt(w)
    zw, yw = z * sw[:, None], (y - ym) * sw
    b = np.linalg.solve(zw.T @ zw + lam * w.sum() * np.eye(z.shape[1]), zw.T @ yw)
    return {"mu": mu, "sd": sd, "b": b, "ym": ym, "lo": x.min(axis=0), "hi": x.max(axis=0)}


def ridge_predict(m: dict, x: np.ndarray) -> np.ndarray:
    # Sem extrapolação: cada variável fica limitada ao intervalo visto no treino (ex.: a subida de juros
    # de 2022 estava muito fora do que os modelos treinados só com 2020-21 tinham visto).
    return m["ym"] + ((np.clip(x, m["lo"], m["hi"]) - m["mu"]) / m["sd"]) @ m["b"]


def common_idio(r: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Separa o erro em choque comum a todos os concelhos de cada origem (média ponderada pela
    precisão) e resíduo idiossincrático normalizado pela volatilidade do concelho. Os erros de uma
    mesma origem estão muito correlacionados (surpresa nacional): tratá-los como independentes dá
    intervalos demasiado estreitos."""
    err = (r["y"] - r["pred"]).astype(float)
    w = 1 / r["sigma"].astype(float) ** 2
    c = (err * w).groupby(r["origin"]).sum() / w.groupby(r["origin"]).sum()
    u = (err - r["origin"].map(c)) / r["sigma"].astype(float)
    return c.to_numpy(float), u.to_numpy(float)


def interval_quantiles(c: np.ndarray, u: np.ndarray, sigma: np.ndarray, n_draw: int = 4000,
                       seed: int = 0) -> dict[str, np.ndarray]:
    """Quantis de (choque comum ~ N(0, RMS dos choques passados) + resíduo idiossincrático empírico x sigma)."""
    rng = np.random.default_rng(seed)
    sc = math.sqrt(float(np.mean(c ** 2)) * (len(c) + 1) / len(c)) if len(c) else 0.0
    tot = rng.normal(0, sc, n_draw)[None, :] + rng.choice(u, n_draw)[None, :] * np.asarray(sigma, float)[:, None]
    return {k: np.quantile(tot, q, axis=1) for k, q in QUANTS.items()}


def _calibrated(r: pd.DataFrame, min_origins: int = 3) -> bool:
    return r["origin"].nunique() >= min_origins and len(r) >= MIN_CAL_RESID


def _recent(r: pd.DataFrame, window: int = CAL_WINDOW) -> pd.DataFrame:
    keep = sorted(r["origin"].unique())[-window:]
    return r[r["origin"].isin(keep)]


def _usable(panel: pd.DataFrame, feats: list[str]) -> list[str]:
    return [f for f in feats if f in panel.columns and panel[f].nunique(dropna=True) > 1]


# ---------------------------------------------------------------- venda
def _sales_features(s, v3, nat3, eur, a, q, lead, vol=None) -> pd.DataFrame:
    me = q_end_month(q)
    idx = s.index
    s0 = _c(s, q)
    f = pd.DataFrame(index=idx)
    f["s_mom1"] = s0 - _c(s, q - 1)
    f["s_mom4"] = s0 - _c(s, q - 4)
    nat_mom = _g(nat3, me) - _g(nat3, me - 12)
    f["nat_lead"] = (_g(nat3, me + lead) - _g(nat3, me)) if lead > 0 else 0.0
    if v3 is not None:
        v0 = _c(v3, me, idx)
        f["v_mom"] = v0 - _c(v3, me - 12, idx)
        f["v_lead"] = (_c(v3, me + lead, idx) - v0) if lead > 0 else 0.0
        for col, fill in (("v_mom", nat_mom), ("v_lead", f["nat_lead"])):
            f[col] = f[col].fillna(fill)
            f[col] = f[col].fillna(f[col].median())
    f["nb_mom4"] = nb_mean(f["s_mom4"], a).fillna(f["s_mom4"])
    f["rel_level"] = s0 - s0.median()
    if eur is not None:
        # último valor publicado até essa data (o trimestre mais recente pode acabar depois da última Euribor)
        asof = lambda k: float(eur[eur.index <= k].iloc[-1]) if (eur.index <= k).any() else np.nan  # noqa: E731
        f["eur_chg"] = asof(me + lead) - asof(me + lead - 12)
    if vol is not None:
        # volume (avaliações bancárias, já somadas a 3 meses pelo INE): o volume costuma mexer antes dos preços
        f["vol_chg"] = _c(vol, me + lead, idx) - _c(vol, me + lead - 12, idx)
        f["vol_chg"] = f["vol_chg"].fillna(f["vol_chg"].median())
    f["sigma"] = robust_sigma(s, q)
    return f


def _kind(qi: int, today: dt.date) -> str:
    start_month = (qi // 4) * 12 + (qi % 4) * 3
    return "nowcast" if start_month <= today.year * 12 + today.month - 1 else "forecast"


def forecast_sales(sales: pd.DataFrame, valuation: pd.DataFrame | None = None,
                   euribor: pd.DataFrame | None = None, nbrs: dict[str, list[str]] | None = None,
                   regions: dict[str, str] | None = None, today: dt.date | None = None,
                   volume: pd.DataFrame | None = None) -> tuple[dict | None, dict]:
    """Devolve (resumo para outlook.json, {dico: previsão})."""
    today = today or dt.date.today()
    s = log_grid(sales, q_index)
    if s is None or s.shape[1] < 12:
        return None, {}
    s = s[s.notna().sum(axis=1) >= 6]
    v3, nat3 = valuation_grids(valuation)
    eur = euribor_series(euribor)
    vol = log_grid(volume, m_index)
    if vol is not None:   # o último trimestre pode acabar depois do último mês publicado: usa o último valor (até 3 meses)
        vol = vol.reindex(columns=range(int(vol.columns.min()), int(vol.columns.max()) + 4)).ffill(axis=1, limit=3)
    a = adjacency(s.index, nbrs)
    qmax = int(max(k for k in s.columns if s[k].notna().any()))
    last_v = int(max(k for k in nat3.dropna().index)) if nat3 is not None and nat3.notna().any() else None
    if last_v is None and v3 is not None:
        last_v = int(max(k for k in v3.columns if v3[k].notna().any()))
    lead = max(0, last_v - q_end_month(qmax)) if last_v is not None else 0
    cur_q = today.year * 4 + (today.month - 1) // 3
    h_now = min(max(cur_q - qmax, 0), 4)
    horizons = list(range(1, min(h_now + 4, MAX_HORIZON) + 1))

    origins = [q for q in range(int(s.columns.min()) + 4, qmax + 1)]
    parts = []
    for q in origins:
        f = _sales_features(s, v3, nat3, eur, a, q, lead, vol)
        f["origin"] = q
        for h in horizons:
            f[f"y{h}"] = _c(s, q + h) - _c(s, q)
        parts.append(f.rename_axis("dico").reset_index())
    panel = pd.concat(parts, ignore_index=True)
    feats = _usable(panel, SALES_FEATURES)
    panel = panel.dropna(subset=feats + ["sigma"])

    rows, finals, models = [], {}, {}
    for h in horizons:
        yk = f"y{h}"
        for q0 in origins:
            if q0 + h > qmax:
                break
            tr = panel[(panel["origin"] + h <= q0) & panel[yk].notna()]
            if len(tr) < MIN_TRAIN_ROWS:
                continue
            te = panel[(panel["origin"] == q0) & panel[yk].notna()]
            if te.empty:
                continue
            m = ridge_fit(tr[feats].to_numpy(float), tr[yk].to_numpy(float), 1 / tr["sigma"].to_numpy(float) ** 2)
            rows.append(pd.DataFrame({
                "dico": te["dico"].values, "origin": q0, "h": h, "y": te[yk].values,
                "pred": ridge_predict(m, te[feats].to_numpy(float)), "rw": 0.0,
                "drift": te["s_mom4"].values * h / 4, "sigma": te["sigma"].values}))
        tr = panel[(panel["origin"] + h <= qmax) & panel[yk].notna()]
        if len(tr) >= MIN_TRAIN_ROWS // 2:
            models[h] = ridge_fit(tr[feats].to_numpy(float), tr[yk].to_numpy(float), 1 / tr["sigma"].to_numpy(float) ** 2)
    if not models:
        return None, {}
    res = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["dico", "origin", "h", "y", "pred", "rw", "drift", "sigma"])
    metrics = _sales_metrics(res, horizons)

    last = panel[panel["origin"] == qmax].set_index("dico")
    per: dict[str, dict] = {}
    for h in horizons:
        if h not in models:
            continue
        pred = pd.Series(ridge_predict(models[h], last[feats].to_numpy(float)), index=last.index)
        rh = _recent(res[res["h"] == h])
        qs = None
        if _calibrated(rh):
            c, u = common_idio(rh)
            qs = {k: pd.Series(v, index=last.index) for k, v in
                  interval_quantiles(c, u, last["sigma"].to_numpy(float), seed=h).items()}
        finals[h] = {"pred": pred, "q": qs}
    base = last.index.intersection(s.index[s[qmax].notna()])
    h_list = sorted(finals)
    mae4 = res[res["h"] == h_list[-1]].assign(ae=lambda d: (d["y"] - d["pred"]).abs()).groupby("dico")["ae"]
    mae4 = mae4.mean()[mae4.count() >= 2]
    for d in base:
        s_last = float(s.at[d, qmax])
        fc = {"periods": [], "kind": [], "mid": [], "lo80": [], "hi80": [], "lo50": [], "hi50": []}
        for h in h_list:
            p = float(finals[h]["pred"].get(d, np.nan))
            if np.isnan(p):
                continue
            fc["periods"].append(q_label(qmax + h))
            fc["kind"].append(_kind(qmax + h, today))
            fc["mid"].append(round(float(np.exp(s_last + p)), 1))
            qs = finals[h]["q"]
            for k in ("lo80", "hi80", "lo50", "hi50"):
                fc[k].append(round(float(np.exp(s_last + p + qs[k][d])), 1) if qs else None)
        if not fc["mid"]:
            continue
        item = {"fc": fc}
        hn, hf = h_now if h_now in finals else None, h_list[-1]
        if hn:
            item["nowcast_price"] = fc["mid"][h_list.index(hn)]
            item["nowcast_period"] = q_label(qmax + hn)
        i_f = h_list.index(hf)
        item["fc_period"] = q_label(qmax + hf)
        item["fc_price"] = fc["mid"][i_f]
        item["fc_lo80"], item["fc_hi80"] = fc["lo80"][i_f], fc["hi80"][i_f]
        ref = item.get("nowcast_price") or float(np.exp(s_last))
        item["fc_growth_12m"] = round(item["fc_price"] / ref - 1, 4)
        if d in mae4.index:
            item["fc_mae"] = round(float(mae4[d]), 4)
        per[d] = item

    summary = _sales_summary(per, regions, metrics, models, feats, horizons, h_now, qmax, lead, last_v, today)
    return summary, per


def _sales_metrics(res: pd.DataFrame, horizons: list[int], min_origins: int = 3) -> dict:
    out = {}
    for h in horizons:
        r = res[res["h"] == h].copy()
        if r.empty:
            continue
        # conformal sequencial: cada previsão só usa erros de origens cujo alvo já era conhecido
        cov50, cov80, width = [], [], []
        for q0, g in r.groupby("origin"):
            cal = _recent(r[r["origin"] + h <= q0])
            if not _calibrated(cal, min_origins):
                continue
            c, u = common_idio(cal)
            qs = interval_quantiles(c, u, g["sigma"].to_numpy(float), n_draw=2000, seed=int(q0))
            err = (g["y"] - g["pred"]).to_numpy(float)
            cov50.append((err >= qs["lo50"]) & (err <= qs["hi50"]))
            cov80.append((err >= qs["lo80"]) & (err <= qs["hi80"]))
            width.append(qs["hi80"] - qs["lo80"])
        ae = {k: (r["y"] - r[k]).abs() for k in ("pred", "rw", "drift")}
        mae = {k: float(v.mean()) for k, v in ae.items()}
        stable = r["sigma"] <= r["sigma"].median()
        best_naive = "rw" if mae["rw"] <= mae["drift"] else "drift"
        per_dico = pd.DataFrame({"dico": r["dico"], "m": ae["pred"], "n": ae[best_naive]}).groupby("dico").mean()
        by_origin = r.assign(am=ae["pred"], ar=ae["rw"], ad=ae["drift"]).groupby("origin")[["am", "ar", "ad"]].mean()
        out[str(h)] = {
            "n": int(len(r)), "n_origins": int(r["origin"].nunique()),
            "first_origin": q_label(int(r["origin"].min())), "last_origin": q_label(int(r["origin"].max())),
            "mae_model": mae["pred"], "mae_rw": mae["rw"], "mae_drift": mae["drift"],
            "mdae_model": float(ae["pred"].median()), "mdae_rw": float(ae["rw"].median()),
            "mdae_drift": float(ae["drift"].median()),
            "mae_stable_model": float(ae["pred"][stable].mean()), "mae_stable_naive": float(ae[best_naive][stable].mean()),
            "best_naive": best_naive,
            "skill": 1 - mae["pred"] / mae[best_naive] if mae[best_naive] > 0 else None,
            "share_concelhos_better": float((per_dico["m"] < per_dico["n"]).mean()),
            "bias": float((r["pred"] - r["y"]).mean()),
            "coverage50": float(np.concatenate(cov50).mean()) if cov50 else None,
            "coverage80": float(np.concatenate(cov80).mean()) if cov80 else None,
            "width80_median": float(np.median(np.concatenate(width))) if width else None,
            "by_origin": {"origin": [q_label(int(q)) for q in by_origin.index],
                          "model": by_origin["am"].round(4).tolist(), "rw": by_origin["ar"].round(4).tolist(),
                          "drift": by_origin["ad"].round(4).tolist()},
        }
    return out


def _pp(x: float) -> str:
    return f"{x * 100:.1f}".replace(".", ",")


def _verdict(m: dict | None, what: str) -> str:
    if not m or m.get("skill") is None:
        return f"Sem backtest suficiente para avaliar a previsão {what}."
    nv = m["best_naive"]
    naive = "«fica igual»" if nv == "rw" else "«continua o ritmo do último ano»"
    first, last = m["first_origin"].replace("Q", "T"), m["last_origin"].replace("Q", "T")
    base = (f"No backtest ({m['n_origins']} origens, {first} a {last}), a previsão {what} errou em média "
            f"{_pp(m['mae_model'])} p.p. (concelho típico: {_pp(m['mdae_model'])} p.p.), contra {_pp(m['mae_' + nv])} p.p. "
            f"({_pp(m['mdae_' + nv])} p.p.) da melhor regra ingénua, {naive}. ")
    sk = m["skill"]
    med_better = m["mdae_model"] < m["mdae_" + nv] * 0.95
    if sk >= 0.05:
        base += f"Ou seja, {sk * 100:.0f}% menos erro médio: acrescenta informação."
    elif sk > -0.05:
        base += ("Erro médio praticamente igual" + (", mas menor no concelho típico" if med_better else "")
                 + ": trate o valor central como indicativo.")
    else:
        base += ("Erro médio maior do que a regra ingénua" + (" (embora menor no concelho típico)" if med_better else "")
                 + ": não confie no valor central, só na ordem de grandeza e no intervalo.")
    if m.get("coverage80") is not None:
        base += (f" O intervalo de 80% conteve o valor real em {m['coverage80'] * 100:.0f}% dos casos"
                 + (" (bem calibrado)." if 0.72 <= m["coverage80"] <= 0.9 else
                    " (intervalos demasiado estreitos: a incerteza real é maior)." if m["coverage80"] < 0.72 else
                    " (intervalos conservadores: mais largos do que o necessário)."))
    return base


def _sales_summary(per, regions, metrics, models, feats, horizons, h_now, qmax, lead, last_v, today) -> dict:
    g = pd.Series({d: v["fc_growth_12m"] for d, v in per.items() if v.get("fc_growth_12m") is not None})
    by_region = []
    if regions and len(g):
        rg = g.groupby(g.index.map(lambda d: regions.get(d, "Outros")))
        by_region = sorted(({"name": k, "n": int(v.count()), "median": float(v.median()),
                             "p25": float(v.quantile(0.25)), "p75": float(v.quantile(0.75))} for k, v in rg),
                           key=lambda x: -x["median"])
    hf = max(models)
    coefs = sorted(({"feature": f, "label": FEATURE_LABELS.get(f, f), "coef_std": float(b)}
                    for f, b in zip(feats, models[hf]["b"])), key=lambda x: -abs(x["coef_std"]))
    nowcast_growth = pd.Series({d: v["nowcast_price"] for d, v in per.items() if v.get("nowcast_price")})
    return {
        "origin": q_label(qmax), "last_valuation": m_label(last_v) if last_v is not None else None,
        "valuation_lead_months": lead, "h_now": h_now,
        "nowcast_period": q_label(qmax + h_now) if h_now else None,
        "target_period": q_label(qmax + hf), "horizons": [{"h": h, "period": q_label(qmax + h),
                                                          "kind": _kind(qmax + h, today)} for h in horizons],
        "n_concelhos": len(per), "features": feats, "coefficients": coefs,
        "median_growth_12m": float(g.median()) if len(g) else None,
        "p25_growth_12m": float(g.quantile(0.25)) if len(g) else None,
        "p75_growth_12m": float(g.quantile(0.75)) if len(g) else None,
        "share_up": float((g > 0).mean()) if len(g) else None,
        "n_nowcast": int(len(nowcast_growth)),
        "by_region": by_region, "backtest": metrics,
        "verdict_nowcast_pt": _verdict(metrics.get(str(h_now)), "para o presente") if h_now else None,
        "verdict_pt": _verdict(metrics.get(str(hf)), f"a {hf} trimestres do último valor publicado"),
    }


# ---------------------------------------------------------------- rendas
def forecast_rent(rent: pd.DataFrame | None, sales: pd.DataFrame | None, valuation: pd.DataFrame | None = None,
                  today: dt.date | None = None) -> tuple[dict | None, dict]:
    today = today or dt.date.today()
    r = log_grid(rent, lambda k: int(k) // 100)
    if r is None or r.shape[1] < 3:
        return None, {}
    s = log_grid(sales, q_index)
    v3, nat3 = valuation_grids(valuation)
    ymax = int(max(k for k in r.columns if r[k].notna().any()))
    last_v = int(max(k for k in nat3.dropna().index)) if nat3 is not None and nat3.notna().any() else None
    lead = max(0, last_v - (ymax * 12 + 11)) if last_v is not None else 0

    s_qmax = int(max(k for k in s.columns if s[k].notna().any())) if s is not None else None
    origins = list(range(int(r.columns.min()) + 1, ymax + 1))
    parts = []
    for y in origins:
        idx = r.index
        f = pd.DataFrame(index=idx)
        f["r_mom"] = _c(r, y) - _c(r, y - 1)
        if s is not None:
            qy = min(y * 4 + 3, s_qmax)          # último trimestre de vendas conhecido nesse ano
            sq, sq0 = _c(s, qy, idx), _c(s, qy - 4, idx)
            f["s_yoy"] = (sq - sq0).fillna((sq - sq0).median())
            yl = _c(r, y) - sq
            f["yield_gap"] = (yl - yl.median()).fillna(0.0)
        me = y * 12 + 11
        nl = (_g(nat3, me + lead) - _g(nat3, me)) if lead > 0 else 0.0
        if v3 is not None:
            f["v_lead"] = ((_c(v3, me + lead, idx) - _c(v3, me, idx)) if lead > 0 else 0.0)
            f["v_lead"] = pd.Series(f["v_lead"], index=idx).fillna(nl)
            f["v_lead"] = f["v_lead"].fillna(f["v_lead"].median())
        f["y1"] = _c(r, y + 1) - _c(r, y)
        f["origin"] = y
        diffs = r.loc[:, [k for k in r.columns if k <= y]].diff(axis=1).iloc[:, 1:]
        n = diffs.notna().sum(axis=1)
        sd = diffs.std(axis=1, ddof=1)
        glob = float(np.nanmedian(sd)) if sd.notna().any() else 0.05
        k0 = 3.0
        f["sigma"] = np.sqrt(((n - 1).clip(lower=0) * sd.fillna(0) ** 2 + k0 * glob ** 2) / ((n - 1).clip(lower=0) + k0))
        parts.append(f.rename_axis("dico").reset_index())
    panel = pd.concat(parts, ignore_index=True)
    feats = _usable(panel, RENT_FEATURES)
    panel = panel.dropna(subset=feats + ["sigma"])
    panel = panel[panel["sigma"] > 0]

    rows = []
    for y0 in origins:
        if y0 + 1 > ymax:
            break
        tr = panel[(panel["origin"] + 1 <= y0) & panel["y1"].notna()]
        te = panel[(panel["origin"] == y0) & panel["y1"].notna()]
        if len(tr) < MIN_TRAIN_ROWS_RENT or te.empty:
            continue
        m = ridge_fit(tr[feats].to_numpy(float), tr["y1"].to_numpy(float), 1 / tr["sigma"].to_numpy(float) ** 2)
        rows.append(pd.DataFrame({"dico": te["dico"].values, "origin": y0, "h": 1, "y": te["y1"].values,
                                  "pred": ridge_predict(m, te[feats].to_numpy(float)), "rw": 0.0,
                                  "drift": te["r_mom"].values, "sigma": te["sigma"].values}))
    tr = panel[(panel["origin"] + 1 <= ymax) & panel["y1"].notna()]
    if len(tr) < MIN_TRAIN_ROWS_RENT // 2:
        return None, {}
    model = ridge_fit(tr[feats].to_numpy(float), tr["y1"].to_numpy(float), 1 / tr["sigma"].to_numpy(float) ** 2)
    res = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["dico", "origin", "h", "y", "pred", "rw", "drift", "sigma"])
    metrics = _sales_metrics(res.assign(origin=res["origin"].astype(int)), [1], min_origins=2).get("1") if len(res) else None
    if metrics:
        metrics["first_origin"], metrics["last_origin"] = str(int(res["origin"].min())), str(int(res["origin"].max()))
        metrics["by_origin"]["origin"] = [str(int(o)) for o in sorted(res["origin"].unique())]
    in_sample = not _calibrated(res, 2)
    cal = _recent(res) if not in_sample else tr.assign(y=tr["y1"], pred=ridge_predict(model, tr[feats].to_numpy(float)))

    last = panel[panel["origin"] == ymax].set_index("dico")
    pred = pd.Series(ridge_predict(model, last[feats].to_numpy(float)), index=last.index)
    c, u = common_idio(cal)
    qs = interval_quantiles(c, u, last["sigma"].to_numpy(float), seed=1)
    per = {}
    for i, (d, p) in enumerate(pred.items()):
        r0 = float(r.at[d, ymax])
        per[d] = {"rent_fc": round(float(np.exp(r0 + p)), 2), "rent_fc_year": str(ymax + 1),
                  "rent_fc_growth": round(float(np.exp(p) - 1), 4),
                  "rent_fc_lo80": round(float(np.exp(r0 + p + qs["lo80"][i])), 2),
                  "rent_fc_hi80": round(float(np.exp(r0 + p + qs["hi80"][i])), 2)}
    g = pd.Series({d: v["rent_fc_growth"] for d, v in per.items()})
    summary = {
        "origin_year": str(ymax), "target_year": str(ymax + 1),
        "target_in_progress": ymax + 1 <= today.year, "valuation_lead_months": lead,
        "n_concelhos": len(per), "features": feats,
        "coefficients": sorted(({"feature": f, "label": FEATURE_LABELS.get(f, f), "coef_std": float(b)}
                                for f, b in zip(feats, model["b"])), key=lambda x: -abs(x["coef_std"])),
        "median_growth": float(g.median()) if len(g) else None,
        "p25_growth": float(g.quantile(0.25)) if len(g) else None,
        "p75_growth": float(g.quantile(0.75)) if len(g) else None,
        "share_up": float((g > 0).mean()) if len(g) else None,
        "backtest": metrics, "intervals_in_sample": in_sample,
        "verdict_pt": _verdict(metrics, "da renda a 1 ano"),
    }
    return summary, per
