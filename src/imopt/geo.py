"""Fronteiras dos concelhos: descarga, ligação ao código DICO do INE e simplificação."""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

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
