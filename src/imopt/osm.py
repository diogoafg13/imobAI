"""Escolas, saúde e estações por freguesia, do OpenStreetMap (© contribuidores do OpenStreetMap, licença ODbL).

Três consultas à API Overpass (uma por tipo), no máximo uma vez por semana; os pontos ficam em
data/clean/osm_points.parquet e são contados por freguesia com as fronteiras do painel.
- escolas: amenity=school (do pré-escolar ao secundário; o OSM não distingue sempre o nível);
- saúde: amenity=hospital, clinic ou doctors (hospitais, centros de saúde, clínicas, consultórios);
- estações: railway=station ou halt (comboio e metro; inclui apeadeiros).
O OpenStreetMap é feito por voluntários: está quase completo nas cidades e pode faltar coisas no interior. Por isso
a medida é "o que está no mapa", não um censo oficial.
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger("imopt")
UA = {"User-Agent": "imobiliario-pt/0.1 (dados abertos; painel de risco imobiliário)"}
MAX_AGE_DAYS = 7
KINDS = {
    "school": 'nwr["amenity"="school"](area.a);',
    "health": 'nwr["amenity"~"^(hospital|clinic|doctors)$"](area.a);',
    "station": 'nwr["railway"~"^(station|halt)$"](area.a);',
}


def query(body: str) -> str:
    return f'[out:json][timeout:600];area["ISO3166-1"="PT"]["admin_level"="2"]->.a;({body});out center qt;'


def parse(js: dict, kind: str) -> pd.DataFrame:
    rows = []
    for e in js.get("elements", []):
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        lon = e.get("lon", (e.get("center") or {}).get("lon"))
        if lat is not None and lon is not None:
            rows.append((float(lat), float(lon), kind))
    return pd.DataFrame(rows, columns=["lat", "lon", "kind"])


def ingest(cfg: dict | None, data_dir: Path) -> tuple[pd.DataFrame | None, str]:
    path = data_dir / "clean" / "osm_points.parquet"
    cached = pd.read_parquet(path) if path.exists() else None
    if not cfg:
        return cached, "sem configuração"
    if cached is not None and len(cached) and "fetched" in cached:
        age = (dt.date.today() - dt.date.fromisoformat(str(cached["fetched"].iloc[0]))).days
        if age < MAX_AGE_DAYS:
            return cached, f"ok (cache de {cached['fetched'].iloc[0]}: {len(cached)} pontos)"
    parts, errors = [], []
    for kind, body in KINDS.items():
        try:
            r = requests.post(cfg["url"], data={"data": query(body)}, headers=UA, timeout=900)
            r.raise_for_status()
            p = parse(r.json(), kind)
            if len(p) < 50:
                raise ValueError(f"só {len(p)} pontos")
            parts.append(p)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{kind}: {str(e)[:120]}")
    if len(parts) == len(KINDS):
        pts = pd.concat(parts, ignore_index=True).assign(fetched=dt.date.today().isoformat())
        path.parent.mkdir(parents=True, exist_ok=True)
        pts.to_parquet(path, index=False)
        return pts, "ok (" + ", ".join(f"{k}: {int((pts['kind'] == k).sum())}" for k in KINDS) + ")"
    log.warning("OpenStreetMap indisponível: %s", "; ".join(errors))
    if cached is not None:
        return cached, "CACHE (" + "; ".join(errors)[:200] + ")"
    return None, "ERRO: " + "; ".join(errors)[:250]


def by_parish(points: pd.DataFrame | None, parish_geo: dict | None) -> pd.DataFrame | None:
    """Contagens por freguesia (código DICOFRE) e tipo: colunas n_school, n_health, n_station."""
    if points is None or points.empty or not parish_geo:
        return None
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree
    polys, codes = [], []
    for f in parish_geo.get("features", []):
        c = (f.get("properties") or {}).get("code")
        if c and f.get("geometry"):
            try:
                polys.append(shape(f["geometry"]))
                codes.append(str(c))
            except Exception:  # noqa: BLE001
                continue
    if not polys:
        return None
    tree = STRtree(polys)
    hit_pt, hit_poly = tree.query([Point(x, y) for x, y in zip(points["lon"], points["lat"])], predicate="within")
    d = pd.DataFrame({"code": [codes[j] for j in hit_poly], "kind": points["kind"].to_numpy()[hit_pt]})
    out = d.groupby(["code", "kind"]).size().unstack(fill_value=0)
    out.columns = [f"n_{c}" for c in out.columns]
    for k in KINDS:
        if f"n_{k}" not in out:
            out[f"n_{k}"] = 0
    out.attrs["matched"] = float(len(d) / len(points))
    return out
