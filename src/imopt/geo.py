"""Fronteiras dos concelhos: descarga, ligação ao código DICO do INE e simplificação."""
from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Any

import numpy as np
import pandas as pd
import requests


def norm_name(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def download_geojson(url: str) -> dict:
    r = requests.get(url, timeout=120, headers={"User-Agent": "imobiliario-pt/0.1"})
    r.raise_for_status()
    return r.json()


def _first(props: dict, candidates: list[str]) -> Any:
    lower = {k.lower(): v for k, v in props.items()}
    for c in candidates:
        if c.lower() in lower and lower[c.lower()] not in (None, ""):
            return lower[c.lower()]
    return None


def attach_dico(geojson: dict, dico_props: list[str], name_props: list[str],
                dico_by_name: dict[str, str]) -> tuple[dict, list[str]]:
    """Garante `properties.dico` em cada feature. Devolve (geojson, nomes por ligar)."""
    unmatched = []
    for f in geojson.get("features", []):
        props = f.setdefault("properties", {})
        d = _first(props, dico_props)
        if d is not None and re.fullmatch(r"\d{3,4}", str(d).strip()):
            props["dico"] = str(d).strip().zfill(4)
            continue
        nm = _first(props, name_props)
        d2 = dico_by_name.get(norm_name(nm)) if nm else None
        if d2:
            props["dico"] = d2
        else:
            unmatched.append(str(nm))
    return geojson, unmatched


def _round(coords: Any, nd: int) -> Any:
    if isinstance(coords, (int, float)):
        return round(coords, nd)
    return [_round(c, nd) for c in coords]


def slim_geojson(geojson: dict, keep_props: dict[str, dict], tolerance: float = 0.002,
                 ndigits: int = 4) -> dict:
    """Reduz tamanho: simplifica geometrias (se shapely existir), arredonda e limita propriedades."""
    try:
        from shapely.geometry import mapping, shape
    except ImportError:  # sem shapely: só arredonda
        shape = None
    feats = []
    for f in geojson["features"]:
        d = f.get("properties", {}).get("dico")
        if not d:
            continue
        geom = f["geometry"]
        if shape is not None:
            g = shape(geom).simplify(tolerance, preserve_topology=True)
            geom = mapping(g)
        geom = {"type": geom["type"], "coordinates": _round(geom["coordinates"], ndigits)}
        feats.append({"type": "Feature", "properties": {"dico": d, **keep_props.get(d, {})}, "geometry": geom})
    return {"type": "FeatureCollection", "features": feats}


def dump(obj: Any, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))


def haversine_km(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = (np.radians(np.asarray(v, dtype=float)) for v in (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def spatial_index(geojson: dict | None, touch_deg: float = 0.01) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Centróide (lon, lat), área (km²), extensão de costa e vizinhos de cada concelho.

    Vizinhos = polígonos a menos de `touch_deg` graus (~1 km): as geometrias publicadas são
    simplificadas, por isso fronteiras comuns nem sempre coincidem exatamente. Costa = fronteira sem
    concelho vizinho do lado do mar (inclui estuários e a Ria de Aveiro); litoral se >= 1 km.
    """
    empty = pd.DataFrame(columns=["dico", "lon", "lat", "area_km2", "coast_km", "coastal"])
    if not geojson or not geojson.get("features"):
        return empty, {}
    from shapely.geometry import shape
    from shapely.ops import transform, unary_union
    from shapely.strtree import STRtree

    parts: dict[str, list] = {}
    for f in geojson["features"]:
        d = (f.get("properties") or {}).get("dico")
        if not d or not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        g = g.simplify(0.002, preserve_topology=True)  # igual às geometrias publicadas (e rápido)
        if not g.is_empty:
            parts.setdefault(str(d), []).append(g)
    if not parts:
        return empty, {}
    dicos = sorted(parts)
    geoms = [unary_union(parts[d]) for d in dicos]
    tree = STRtree(geoms)
    pos = {d: i for i, d in enumerate(dicos)}
    nbrs = {d: [dicos[j] for j in tree.query(g.buffer(touch_deg), predicate="intersects") if dicos[j] != d]
            for d, g in zip(dicos, geoms)}
    rows = []
    for d, g in zip(dicos, geoms):
        c = g.centroid
        kx, ky = 111.32 * math.cos(math.radians(c.y)), 110.57
        area = transform(lambda x, y, z=None: (np.asarray(x) * kx, np.asarray(y) * ky), g).area
        others = [geoms[pos[n]].buffer(touch_deg) for n in nbrs[d]]
        exposed = g.boundary.difference(unary_union(others)) if others else g.boundary
        rows.append({"dico": d, "lon": c.x, "lat": c.y, "area_km2": area, "coast_km": _sea_length_km(exposed)})
    df = pd.DataFrame(rows)
    df["coastal"] = df["coast_km"] >= 1.0
    return df, nbrs


def _is_sea(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Fronteira exposta (sem concelho vizinho) do lado do mar: ilhas, costa oeste (a sul da foz do
    Minho) e costa sul do Algarve. O resto da fronteira exposta é a raia com Espanha."""
    return (lon < -15) | ((lon < -8.55) & (lat < 41.87)) | ((lat < 37.25) & (lon < -7.42))


def _sea_length_km(geom) -> float:
    lines = getattr(geom, "geoms", [geom])
    total = 0.0
    for ln in lines:
        if ln.is_empty or ln.geom_type not in ("LineString", "LinearRing"):
            continue
        xy = np.asarray(ln.coords)
        if len(xy) < 2:
            continue
        mid = (xy[1:] + xy[:-1]) / 2
        seg = haversine_km(xy[:-1, 0], xy[:-1, 1], xy[1:, 0], xy[1:, 1])
        total += float(seg[_is_sea(mid[:, 0], mid[:, 1])].sum())
    return total
