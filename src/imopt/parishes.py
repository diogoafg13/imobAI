"""Freguesias: preço de venda (INE 0012234, nível freguesia) e renda (0012600), comparados com o concelho e
com as freguesias vizinhas. Só leitura.

O INE só publica a mediana onde há vendas suficientes (~400 de ~3000 freguesias, quase todas urbanas). As
medianas de freguesia assentam em poucas vendas: um valor extremo pode ser só a composição das casas
vendidas (tamanho, estado), não a freguesia ser cara ou barata.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import geo
from .scoring import _shift_key

log = logging.getLogger("imopt")
MIN_NEIGHBOURS = 2


def _parish_rows(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty or "geocod" not in df:
        return None
    g = df["geocod"].astype(str)
    d = df[df["level"].isin(["parish", "other"]) & g.str.len().eq(9) & g.str[-6:].str.isdigit()].dropna(subset=["value"])
    return d.assign(code=d["geocod"].astype(str).str[-6:]) if len(d) else None


def table(sales: pd.DataFrame | None, rent: pd.DataFrame | None, muni_price: dict[str, float]) -> pd.DataFrame:
    s = _parish_rows(sales)
    if s is None:
        return pd.DataFrame()
    latest = int(s["sort_key"].max())
    prev = _shift_key(latest, "quarter", 4)
    p = s.pivot_table(index="code", columns="sort_key", values="value", aggfunc="last")
    names = s.sort_values("sort_key").drop_duplicates("code", keep="last").set_index("code")["geoname"]
    out = pd.DataFrame({"price": p.get(latest)}).dropna()
    out["g1y"] = (p[latest] / p[prev] - 1) if prev in p.columns else np.nan
    out["name"] = names.reindex(out.index)
    out["dico"] = out.index.str[:4]
    out["rel_muni"] = out["price"] / out["dico"].map(muni_price) - 1
    r = _parish_rows(rent)
    if r is not None:
        ly = int(r["sort_key"].max())
        rr = r[r["sort_key"] == ly].drop_duplicates("code", keep="last").set_index("code")["value"]
        out["rent"] = rr.reindex(out.index)
        out["rent_year"] = ly // 100
    out.attrs["period"] = s.loc[s["sort_key"] == latest, "period"].iloc[0]
    return out.rename_axis("code").reset_index()


def add_neighbours(t: pd.DataFrame, parish_geo: dict | None) -> pd.DataFrame:
    """Preço face à mediana das freguesias vizinhas com dados (pelo menos MIN_NEIGHBOURS)."""
    if t.empty or not parish_geo:
        return t
    codes = set(t["code"])
    sub = {"type": "FeatureCollection",
           "features": [f for f in parish_geo.get("features", []) if (f.get("properties") or {}).get("code") in codes]}
    _, nbrs = geo.spatial_index(sub, key="code", touch_deg=0.003)
    price = t.set_index("code")["price"]
    rel, n_nb = [], []
    for c, v in price.items():
        vals = [price[n] for n in nbrs.get(c, []) if n in price.index]
        n_nb.append(len(vals))
        rel.append(v / float(np.median(vals)) - 1 if len(vals) >= MIN_NEIGHBOURS else np.nan)
    return t.assign(rel_nb=rel, n_nb=n_nb)


def geojson_out(t: pd.DataFrame, parish_geo: dict | None) -> dict | None:
    if t.empty or not parish_geo:
        return None
    keep = {r.code: {"name": r.name, "price": _r(r.price), "g1y": _r(r.g1y), "rel_muni": _r(r.rel_muni),
                     "rel_nb": _r(getattr(r, "rel_nb", None))} for r in t.itertuples()}
    gj = geo.slim_geojson(parish_geo, keep, tolerance=0.0008, key="code", only_kept=True)
    return gj if gj["features"] else None


def _r(v):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), 4)
