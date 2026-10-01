"""O que mudou desde o trimestre anterior: preço, score e faixa de risco por concelho.

O score do trimestre anterior é recalculado com o mesmo método (scoring.municipal_features) e os dados de
vendas cortados nesse trimestre; a renda é a mesma nos dois cálculos, por isso as mudanças de score vêm dos
preços. O preço do INE é uma mediana móvel de 12 meses: a variação trimestral é suave e atrasada.
"""
from __future__ import annotations

import pandas as pd

from . import scoring
from .scoring import _shift_key

BAND_ORDER = {"green": 0, "amber": 1, "red": 2}
TOP = 10
MIN_VOLUME = 20


def quarter_changes(sales: pd.DataFrame | None, rent: pd.DataFrame | None, feats: pd.DataFrame) -> tuple[dict | None, dict]:
    if sales is None or sales.empty or feats.empty:
        return None, {}
    now_key = int(sales["sort_key"].max())
    prev_key = _shift_key(now_key, "quarter", 1)
    prev_sales = sales[sales["sort_key"] <= prev_key]
    if prev_sales.empty or prev_sales["sort_key"].max() != prev_key:
        return None, {}
    prev = scoring.municipal_features(prev_sales, rent).set_index("dico")
    now = feats.set_index("dico")
    d = pd.DataFrame({"name": now["name"], "price": now["price"], "price_prev": prev["price"].reindex(now.index),
                      "score": now["score_overall"], "score_prev": prev["score_overall"].reindex(now.index),
                      "band": now["band"], "band_prev": prev["band"].reindex(now.index),
                      "volatile": now["volatile"].fillna(False) if "volatile" in now else False})
    d["qoq"] = d["price"] / d["price_prev"] - 1
    d["dscore"] = d["score"] - d["score_prev"]
    label = lambda k: f"{k // 100}Q{k % 100}"  # noqa: E731
    stable = d[~d["volatile"].astype(bool)]
    if "val_count" in now and now["val_count"].notna().sum() >= 10:
        # listas de maiores movimentos só com mercado suficiente (>= MIN_VOLUME avaliações em 3 meses)
        stable = stable[now["val_count"].reindex(stable.index) >= MIN_VOLUME]

    def rows(df, col, asc):
        df = df.dropna(subset=[col]).sort_values(col, ascending=asc).head(TOP)
        return [{"dico": str(i), "name": str(r["name"]), "value": float(r[col]), "price": float(r["price"]),
                 "score": None if pd.isna(r["score"]) else float(r["score"]),
                 "score_prev": None if pd.isna(r["score_prev"]) else float(r["score_prev"])} for i, r in df.iterrows()]

    moved = d.dropna(subset=["band", "band_prev"])
    moved = moved[moved["band"] != moved["band_prev"]]
    changes = [{"dico": str(i), "name": str(r["name"]), "from": r["band_prev"], "to": r["band"],
                "score_prev": float(r["score_prev"]), "score": float(r["score"])}
               for i, r in moved.sort_values("dscore", ascending=False).iterrows()]
    up = [c for c in changes if BAND_ORDER[c["to"]] > BAND_ORDER[c["from"]]]
    q = d["qoq"].dropna()
    summary = {
        "period": label(now_key), "prev_period": label(prev_key), "n": int(len(q)),
        "median_qoq": float(q.median()) if len(q) else None, "share_up": float((q > 0).mean()) if len(q) else None,
        "n_band_up": len(up), "n_band_down": len(changes) - len(up),
        "min_volume": MIN_VOLUME if "val_count" in now else None,
        "n_red": int((d["band"] == "red").sum()), "n_red_prev": int((d["band_prev"] == "red").sum()),
        "band_changes": changes,
        "price_up": rows(stable, "qoq", False), "price_down": rows(stable, "qoq", True),
        "score_up": rows(stable, "dscore", False), "score_down": rows(stable, "dscore", True),
    }
    per = {str(i): {"price_qoq": round(float(r["qoq"]), 4), "score_prev": round(float(r["score_prev"]), 2),
                    "band_prev": r["band_prev"]}
           for i, r in d.iterrows() if pd.notna(r["qoq"]) and pd.notna(r["score_prev"]) and isinstance(r["band_prev"], str)}
    return summary, per

