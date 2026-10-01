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


def _census_rows(df: pd.DataFrame | None) -> pd.Series | None:
    """Censos 2021: freguesia com geocod de 6 dígitos (DICOFRE)."""
    if df is None or df.empty or "geocod" not in df:
        return None
    g = df["geocod"].astype(str).str.strip()
    d = df[g.str.fullmatch(r"\d{6}")].dropna(subset=["value"])
    return d.assign(code=d["geocod"].astype(str).str.strip()).drop_duplicates("code", keep="last").set_index("code") if len(d) else None


def rent_table(rent: pd.DataFrame | None, contracts: pd.DataFrame | None = None) -> pd.DataFrame | None:
    """Renda mediana de novos contratos por freguesia (anual), variação a 1 e 3 anos e n.º de contratos."""
    r = _parish_rows(rent)
    if r is None:
        return None
    ly = int(r["sort_key"].max())
    piv = r.pivot_table(index="code", columns="sort_key", values="value", aggfunc="last")
    out = pd.DataFrame({"rent": piv[ly], "rent_year": ly // 100})
    for name, back in (("rent_g1y", 1), ("rent_g3y", 3)):
        k = _shift_key(ly, "year", back)
        out[name] = piv[ly] / piv[k] - 1 if k in piv.columns else np.nan
    c = _parish_rows(contracts)
    if c is not None:
        cc = c[c["sort_key"] == int(c["sort_key"].max())].drop_duplicates("code", keep="last").set_index("code")["value"]
        out["rent_contracts"] = cc.reindex(out.index)
    return out.dropna(subset=["rent"])


def table(sales: pd.DataFrame | None, rent: pd.DataFrame | None, muni_price: dict[str, float],
          irs: pd.DataFrame | None = None, census: dict[str, pd.DataFrame | None] | None = None,
          contracts: pd.DataFrame | None = None) -> pd.DataFrame:
    """Uma linha por freguesia com preço (INE publica ~400), renda, rendimento do IRS ou Censos (quase todas)."""
    out = _price_table(sales, None, muni_price)
    period = out.attrs.get("period")
    rt = rent_table(rent, contracts)
    if rt is not None:
        out = rt if out.empty else out.join(rt, how="outer")
    names = {} if out.empty or "name" not in out else {k: v for k, v in zip(out.index, out["name"]) if isinstance(v, str)}
    extra = pd.DataFrame()
    r = _parish_rows(irs)
    if r is not None:
        ly = int(r["sort_key"].max())
        piv = r.pivot_table(index="code", columns="sort_key", values="value", aggfunc="last")
        extra = pd.DataFrame({"irs_median": piv[ly], "irs_year": ly // 100})
        prev = _shift_key(ly, "year", 1)
        if prev in piv.columns:
            extra["irs_growth_1y"] = piv[ly] / piv[prev] - 1
        extra = extra.dropna(subset=["irs_median"])
        names.update({c: n for c, n in r.drop_duplicates("code", keep="last").set_index("code")["geoname"].items() if c not in names})
    rr = _parish_rows(rent)
    if rr is not None:
        names.update({c: n for c, n in rr.drop_duplicates("code", keep="last").set_index("code")["geoname"].items() if c not in names})
    c = {k: _census_rows((census or {}).get(k)) for k in ("total", "secondary", "vacant_market", "vacant_other")}
    if c["total"] is not None:
        tot = c["total"]["value"]
        cen = pd.DataFrame({"census_total": tot})
        if c["secondary"] is not None:
            cen["secondary_share"] = c["secondary"]["value"].reindex(tot.index) / tot
        if c["vacant_market"] is not None and c["vacant_other"] is not None:
            cen["vacant_share"] = (c["vacant_market"]["value"].reindex(tot.index) + c["vacant_other"]["value"].reindex(tot.index)) / tot
        cen = cen[cen["census_total"] > 0]
        extra = cen if extra.empty else extra.join(cen, how="outer")
        names.update({k: n for k, n in c["total"]["geoname"].items() if k not in names})
    if not extra.empty:
        out = extra if out.empty else out.join(extra, how="outer")
    if out.empty:
        return pd.DataFrame()
    out["name"] = [names.get(k) for k in out.index]
    out["dico"] = out.index.str[:4]
    out.attrs["period"] = period
    return out.rename_axis("code").reset_index()


def _price_table(sales, rent, muni_price) -> pd.DataFrame:
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
    rt = rent_table(rent)
    if rt is not None:
        out = out.join(rt, how="left")
    out.attrs["period"] = s.loc[s["sort_key"] == latest, "period"].iloc[0]
    return out.rename_axis("code")


def add_neighbours(t: pd.DataFrame, parish_geo: dict | None) -> pd.DataFrame:
    """Preço face à mediana das freguesias vizinhas com dados (pelo menos MIN_NEIGHBOURS)."""
    if t.empty or not parish_geo:
        return t
    t = t.copy()
    codes = set(t.loc[t["price"].notna(), "code"]) if "price" in t else set()
    sub = {"type": "FeatureCollection",
           "features": [f for f in parish_geo.get("features", []) if (f.get("properties") or {}).get("code") in codes]}
    _, nbrs = geo.spatial_index(sub, key="code", touch_deg=0.003)
    price = t.set_index("code")["price"].dropna()
    rel, n_nb = [], []
    for c in t["code"]:
        if c not in price.index:
            rel.append(np.nan)
            n_nb.append(0)
            continue
        vals = [price[n] for n in nbrs.get(c, []) if n in price.index]
        n_nb.append(len(vals))
        rel.append(price[c] / float(np.median(vals)) - 1 if len(vals) >= MIN_NEIGHBOURS else np.nan)
    return t.assign(rel_nb=rel, n_nb=n_nb)


def geojson_out(t: pd.DataFrame, parish_geo: dict | None) -> dict | None:
    if t.empty or not parish_geo:
        return None
    g = lambda r, k: _r(getattr(r, k, None))  # noqa: E731
    keep = {r.code: {"name": r.name, "price": g(r, "price"), "g1y": g(r, "g1y"), "rel_muni": g(r, "rel_muni"),
                     "rel_nb": g(r, "rel_nb"), "irs": g(r, "irs_median"), "vac": g(r, "vacant_share"),
                     "sec": g(r, "secondary_share")} for r in t.itertuples()}
    # todas as freguesias (as que não têm dados ficam a cinzento em vez de buracos no mapa)
    gj = geo.slim_geojson(parish_geo, keep, tolerance=0.0008, key="code", only_kept=False)
    return gj if any(f["properties"]["code"] in keep for f in gj["features"]) else None


def _r(v):
    if v is None:
        return None
    v = float(v)
    return None if not np.isfinite(v) else round(v, 4)
