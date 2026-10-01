"""Leituras do mercado com os dados já recolhidos (só contexto, não entram em nenhum score).

- Avaliação bancária vs preço de venda: a avaliação média dos 12 meses que o preço de venda do INE cobre,
  face a esse preço. O nível da diferença é sobretudo composição (a avaliação só cobre casas com crédito,
  normalmente melhores do que a média das vendas); a VARIAÇÃO da diferença num ano é o sinal: avaliações a
  ficar para trás dos preços pagos = bancos mais cautelosos ou mais compras sem crédito.
- Ciclo preço–volume: variação do preço a 12 meses contra a variação do número de avaliações bancárias
  (compras com crédito). Preço a subir com volume a cair é a fase típica de fim de ciclo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_VOLUME = 20     # avaliações em 3 meses: abaixo disto a variação do volume é ruído
MIN_MONTHS = 9      # meses de avaliação publicados na janela de 12 meses
TOP = 10

PHASES = {
    "up_up": "Preço a subir, mais compras",
    "up_down": "Preço a subir, menos compras",
    "down_down": "Preço a descer, menos compras",
    "down_up": "Preço a descer, mais compras",
}


def _qlabel(k: int) -> str:
    return f"{k // 100}Q{k % 100}"


def _window_mean(val: pd.DataFrame, q_key: int) -> pd.DataFrame:
    """Média da avaliação mensal nos 12 meses que terminam no fim do trimestre q_key (sort_key AAAAQQ)."""
    y, q = divmod(q_key, 100)
    end = y * 100 + 3 * q
    start = (y - 1) * 100 + 3 * q + 1 if q < 4 else y * 100 + 1
    w = val[(val["sort_key"] >= start) & (val["sort_key"] <= end)]
    g = w.groupby("dico")["value"].agg(["mean", "count"])
    return g[g["count"] >= MIN_MONTHS]


def valuation_gap(sales: pd.DataFrame | None, valuation: pd.DataFrame | None,
                  names: dict[str, str] | None = None, volume: pd.Series | None = None) -> tuple[dict | None, dict]:
    """volume (avaliações em 3 meses por concelho): as listas só incluem concelhos com >= MIN_VOLUME."""
    if sales is None or sales.empty or valuation is None or valuation.empty:
        return None, {}
    names = names or {}
    val = valuation.dropna(subset=["value"])
    muni_v = val[val["level"] == "municipality"].dropna(subset=["dico"])
    muni_s = sales[sales["level"] == "municipality"].dropna(subset=["dico", "value"]) if "level" in sales else sales
    now = int(muni_s["sort_key"].max())
    ago = (now // 100 - 1) * 100 + now % 100

    def gap_at(k):
        s = muni_s[muni_s["sort_key"] == k].set_index("dico")["value"]
        v = _window_mean(muni_v, k)["mean"]
        return (v / s - 1).dropna()

    g_now, g_ago = gap_at(now), gap_at(ago)
    if len(g_now) < 10:
        return None, {}
    chg = (g_now - g_ago.reindex(g_now.index)).dropna()

    # série nacional (vendas do INE desde 2019) para ver a tendência da diferença
    nat_v = val[val["level"] == "national"].assign(dico="PT")
    nat_s = sales[sales["level"] == "national"] if "level" in sales else pd.DataFrame()
    series = []
    for k in sorted(nat_s["sort_key"].unique()) if len(nat_s) else []:
        v = _window_mean(nat_v, int(k))
        s = nat_s.loc[nat_s["sort_key"] == k, "value"]
        if len(v) and len(s):
            series.append([_qlabel(int(k)), float(v["mean"].iloc[0] / s.iloc[0] - 1)])

    listed = chg if volume is None else chg[volume.reindex(chg.index).fillna(0) >= MIN_VOLUME]

    def rows(sr, asc):
        return [{"dico": str(d), "name": names.get(str(d), str(d)), "value": float(x), "gap": float(g_now[d])}
                for d, x in sr.sort_values(ascending=asc).head(TOP).items()]

    summary = {"period": _qlabel(now), "prev_period": _qlabel(ago), "n": int(len(g_now)),
               "median_gap": float(g_now.median()), "median_change": float(chg.median()) if len(chg) else None,
               "share_widening": float((chg > 0).mean()) if len(chg) else None, "n_change": int(len(chg)),
               "series": series, "lagging": rows(listed, True), "leading": rows(listed, False),
               "min_volume": MIN_VOLUME if volume is not None else None}
    per = {str(d): {"val_gap": round(float(x), 4)} for d, x in g_now.items()}
    for d, x in chg.items():
        per[str(d)]["val_gap_chg"] = round(float(x), 4)
    return summary, per


def price_volume_cycle(feats: pd.DataFrame | None, valuation: pd.DataFrame | None = None,
                       counts: pd.DataFrame | None = None) -> tuple[dict | None, dict]:
    need = ("price_growth_1y", "val_count", "val_count_growth_1y")
    if feats is None or any(c not in feats for c in need):
        return None, {}
    f = feats.dropna(subset=list(need))
    f = f[np.isfinite(f["val_count_growth_1y"]) & (f["val_count"] >= MIN_VOLUME)]
    if len(f) < 10:
        return None, {}
    up_p, up_v = f["price_growth_1y"] > 0, f["val_count_growth_1y"] > 0
    phase = np.select([up_p & up_v, up_p & ~up_v, ~up_p & ~up_v], ["up_up", "up_down", "down_down"], "down_up")
    f = f.assign(phase=phase)
    pts = [{"dico": str(r.dico), "name": str(r.name), "g": float(r.price_growth_1y), "v": float(r.val_count_growth_1y),
            "n": float(r.val_count), "phase": r.phase} for r in f.itertuples()]
    late = f[f["phase"] == "up_down"].sort_values("val_count_growth_1y").head(TOP)
    summary = {"n": int(len(f)), "min_volume": MIN_VOLUME, "phases": PHASES,
               "counts": {k: int((f["phase"] == k).sum()) for k in PHASES},
               "median_price_growth": float(f["price_growth_1y"].median()),
               "median_volume_growth": float(f["val_count_growth_1y"].median()),
               "points": pts,
               "late": [{"dico": p["dico"], "name": p["name"], "g": p["g"], "v": p["v"], "n": p["n"]}
                        for p in (x for x in pts if x["dico"] in set(late["dico"].astype(str)))]}
    summary["late"].sort(key=lambda x: x["v"])
    nat = national_cycle(valuation, counts)
    if nat:
        summary["national"] = nat
    return summary, {str(r.dico): {"cycle_phase": r.phase} for r in f.itertuples()}


def national_cycle(valuation: pd.DataFrame | None, counts: pd.DataFrame | None) -> list | None:
    """Trajetória nacional por trimestre: variação anual da avaliação (preço) e do número de avaliações."""
    if valuation is None or counts is None or valuation.empty or counts.empty:
        return None

    def quarterly(df, how):
        d = df[df["level"] == "national"].dropna(subset=["value"]).sort_values("sort_key")
        if d.empty:
            return None
        k = d["sort_key"]
        d = d.assign(q=(k // 100) * 100 + ((k % 100) - 1) // 3 + 1, m=(k % 100))
        if how == "mean":
            g = d.groupby("q").filter(lambda x: len(x) == 3).groupby("q")["value"].mean()
        else:   # contagem de 3 meses: o valor do último mês do trimestre cobre o trimestre inteiro
            g = d[d["m"] % 3 == 0].set_index("q")["value"]
        return g.astype(float)

    p, v = quarterly(valuation, "mean"), quarterly(counts, "end")
    if p is None or v is None:
        return None
    out = []
    for q in p.index:
        qa = (q // 100 - 1) * 100 + q % 100
        if qa in p.index and q in v.index and qa in v.index and v[qa] > 0:
            out.append([_qlabel(int(q)), float(p[q] / p[qa] - 1), float(v[q] / v[qa] - 1)])
    return out or None
