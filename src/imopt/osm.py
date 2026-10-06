"""Escolas, saúde e estações por freguesia, do OpenStreetMap (© contribuidores do OpenStreetMap, licença ODbL).

Consultas à API Overpass por quadrículas de 1°×1° (o país inteiro de uma vez dá timeout no servidor), com os três
tipos na mesma consulta; no máximo uma vez por semana. Só se grava se todas as quadrículas responderem (uma parte do
país em falta daria contagens a zero onde há escolas). Os pontos ficam em data/clean/osm_points.parquet e são
contados por freguesia com as fronteiras do painel (os pontos de Espanha que caem nas quadrículas não batem com
nenhuma freguesia).
- escolas: amenity=school (do pré-escolar ao secundário; o OSM não distingue sempre o nível);
- saúde: amenity=hospital, clinic ou doctors (hospitais, centros de saúde, clínicas, consultórios);
- estações: railway=station ou halt (comboio e metro; inclui apeadeiros).
O OpenStreetMap é feito por voluntários: está quase completo nas cidades e pode faltar coisas no interior. Por isso
a medida é "o que está no mapa", não um censo oficial.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger("imopt")
UA = {"User-Agent": "imobiliario-pt/0.1 (dados abertos; painel de risco imobiliário)"}
MAX_AGE_DAYS = 7
KINDS = ("school", "health", "station")
FILTERS = ('nwr["amenity"~"^(school|hospital|clinic|doctors)$"];', 'nwr["railway"~"^(station|halt)$"];')
# (sul, oeste, norte, este): continente em quadrículas de 1°, Madeira e Açores numa cada (grupos de ilhas)
BOXES = [(la, lo, la + 1, lo + 1) for la in range(36, 43) for lo in range(-10, -6)] + [
    (32.3, -17.4, 33.2, -16.2), (36.8, -25.9, 38.0, -24.9), (37.5, -29.0, 39.2, -27.0), (39.3, -31.4, 39.8, -31.0)]


def query(box: tuple) -> str:
    s, w, n, e = box
    return f'[out:json][timeout:300][bbox:{s},{w},{n},{e}];({"".join(FILTERS)});out center tags qt;'


def kind_of(tags: dict) -> str | None:
    a, r = tags.get("amenity"), tags.get("railway")
    if a == "school":
        return "school"
    if a in ("hospital", "clinic", "doctors"):
        return "health"
    if r in ("station", "halt"):
        return "station"
    return None


def parse(js: dict) -> pd.DataFrame:
    rows = []
    for e in js.get("elements", []):
        k = kind_of(e.get("tags") or {})
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        lon = e.get("lon", (e.get("center") or {}).get("lon"))
        if k and lat is not None and lon is not None:
            rows.append((float(lat), float(lon), k))
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
    urls = cfg.get("urls") or [cfg["url"]]
    parts, errors = [], []
    for box in BOXES:
        got = None
        for attempt in range(4):           # servidores alternados; 429/504 = ocupado, espera e tenta outra vez
            url = urls[attempt % len(urls)]
            try:
                r = requests.post(url, data={"data": query(box)}, headers=UA, timeout=400)
                r.raise_for_status()
                got = parse(r.json())
                break
            except Exception as e:  # noqa: BLE001
                err = f"{box}: {str(e)[:100]}"
                time.sleep(float(cfg.get("retry_wait", 20)))
        if got is None:
            errors.append(err)
            break
        parts.append(got)
        time.sleep(float(cfg.get("delay", 2)))
    if not errors:
        pts = pd.concat(parts, ignore_index=True).drop_duplicates().assign(fetched=dt.date.today().isoformat())
        if len(pts) >= 1000:
            path.parent.mkdir(parents=True, exist_ok=True)
            pts.to_parquet(path, index=False)
            return pts, "ok (" + ", ".join(f"{k}: {int((pts['kind'] == k).sum())}" for k in KINDS) + ")"
        errors.append(f"só {len(pts)} pontos")
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
