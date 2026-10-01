"""Portugal face aos outros países da UE: preços da habitação (HPI do Eurostat, 2015 = 100) descontada a inflação
(IHPC de cada país). Só contexto: não entra em nenhum score.

O HPI do Eurostat mede a variação dos preços dentro de cada país; não compara níveis (€/m²) entre países.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NAMES = {"AT": "Áustria", "BE": "Bélgica", "BG": "Bulgária", "CY": "Chipre", "CZ": "Chéquia", "DE": "Alemanha",
         "DK": "Dinamarca", "EE": "Estónia", "EL": "Grécia", "ES": "Espanha", "FI": "Finlândia", "FR": "França",
         "HR": "Croácia", "HU": "Hungria", "IE": "Irlanda", "IT": "Itália", "LT": "Lituânia", "LU": "Luxemburgo",
         "LV": "Letónia", "MT": "Malta", "NL": "Países Baixos", "PL": "Polónia", "PT": "Portugal", "RO": "Roménia",
         "SE": "Suécia", "SI": "Eslovénia", "SK": "Eslováquia"}
MIN_COUNTRIES = 10


def _qi(period: str) -> int:
    return int(period[:4]) * 4 + int(period[-1]) - 1


def _ql(i: int) -> str:
    return f"{i // 4}Q{i % 4 + 1}"


def real_indices(hpi: pd.DataFrame, hicp: pd.DataFrame) -> dict[str, pd.Series]:
    """Índice real por país (2015 = 100): HPI ÷ IHPC, rebaseado à média de 2015."""
    out = {}
    for geo, h in hpi.groupby("geo"):
        c = hicp[hicp["geo"] == geo]
        if c.empty:
            continue
        hs = pd.Series(h["value"].astype(float).to_numpy(), index=[_qi(p) for p in h["period"]]).sort_index()
        cs = pd.Series(c["value"].astype(float).to_numpy(), index=[_qi(p) for p in c["period"]]).sort_index()
        r = (hs / cs.reindex(hs.index)).dropna()
        base = r[(r.index >= 2015 * 4) & (r.index < 2016 * 4)]
        if len(base) == 4 and len(r) >= 20:
            out[geo] = r / base.mean() * 100
    return out


def compare(hpi: pd.DataFrame | None, hicp: pd.DataFrame | None) -> dict | None:
    if hpi is None or hicp is None or hpi.empty or hicp.empty:
        return None
    real = real_indices(hpi, hicp)
    if len(real) < MIN_COUNTRIES or "PT" not in real:
        return None
    # último trimestre com dados em pelo menos 2/3 dos países (o HPI sai com atrasos diferentes)
    last = {g: int(s.index.max()) for g, s in real.items()}
    counts = pd.Series(list(last.values())).value_counts().sort_index(ascending=False).cumsum()
    t = int(counts[counts >= len(real) * 2 / 3].index[0])
    nominal = {g: hpi[(hpi["geo"] == g)] for g in real}
    rows = []
    for g, s in real.items():
        if t not in s.index:
            continue
        n = nominal[g]
        nv = n.loc[n["period"] == _ql(t), "value"]
        rows.append({"geo": g, "name": NAMES.get(g, g), "real_2015": float(s[t] / 100 - 1),
                     "nominal_2015": float(nv.iloc[0] / 100 - 1) if len(nv) else None,
                     "real_1y": float(s[t] / s[t - 4] - 1) if t - 4 in s.index else None,
                     "real_5y": float(s[t] / s[t - 20] - 1) if t - 20 in s.index else None,
                     "from_peak": float(s[t] / s[s.index <= t].max() - 1)})
    df = pd.DataFrame(rows).sort_values("real_2015", ascending=False).reset_index(drop=True)
    if "PT" not in set(df["geo"]):
        return None
    pt = df[df["geo"] == "PT"].iloc[0]
    rank = int(df.index[df["geo"] == "PT"][0]) + 1
    d1 = df.dropna(subset=["real_1y"]).sort_values("real_1y", ascending=False).reset_index(drop=True)
    rank_1y = int(d1.index[d1["geo"] == "PT"][0]) + 1 if "PT" in set(d1["geo"]) else None
    panel = pd.DataFrame(real)
    med = panel[panel.index >= 2010 * 4].median(axis=1, skipna=True)
    series = {"PT": [[_ql(int(i)), round(float(v), 1)] for i, v in real["PT"][real["PT"].index >= 2010 * 4].items()],
              "median": [[_ql(int(i)), round(float(v), 1)] for i, v in med.items() if panel.loc[i].notna().sum() >= MIN_COUNTRIES]}
    return {"period": _ql(t), "n": int(len(df)), "rank": rank, "rank_1y": rank_1y, "n_1y": int(len(d1)),
            "pt": {k: (None if pd.isna(v) else (float(v) if not isinstance(v, str) else v)) for k, v in pt.items()},
            "median_real_2015": float(df["real_2015"].median()), "median_real_1y": float(df["real_1y"].median()),
            "countries": df.replace({np.nan: None}).to_dict("records"), "series": series}
