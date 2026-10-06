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
    return f'[out:json][timeout:180][bbox:{s},{w},{n},{e}];({"".join(FILTERS)});out center tags qt;'


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


def _tile_path(tiles: Path, box: tuple) -> Path:
    return tiles / ("_".join(f"{x:g}" for x in box) + ".parquet")


def ingest(cfg: dict | None, data_dir: Path) -> tuple[pd.DataFrame | None, str]:
    """Cada quadrícula fica guardada em data/clean/osm_tiles/ com a data; em cada build só se pedem as que faltam ou
    têm mais de MAX_AGE_DAYS, dentro de um limite de tempo (`budget_s`, 10 min por omissão) — a API Overpass pode
    estar lenta e o build não pode ficar horas à espera. As contagens só mudam quando o país inteiro está completo."""
    path = data_dir / "clean" / "osm_points.parquet"
    cached = pd.read_parquet(path) if path.exists() else None
    if not cfg:
        return cached, "sem configuração"
    tiles = data_dir / "clean" / "osm_tiles"
    tiles.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()

    def age(box) -> int | None:
        f = _tile_path(tiles, box)
        if not f.exists():
            return None
        try:
            return (today - dt.date.fromisoformat(str(pd.read_parquet(f, columns=["fetched"])["fetched"].iloc[0]))).days
        except Exception:  # noqa: BLE001
            return None

    urls = cfg.get("urls") or [cfg["url"]]
    deadline = time.monotonic() + float(cfg.get("budget_s", 600))
    todo = [b for b in BOXES if (a := age(b)) is None or a >= MAX_AGE_DAYS]
    got_n, errors = 0, []
    for box in todo:
        if time.monotonic() > deadline:
            errors.append("limite de tempo")
            break
        for attempt in range(2):            # servidores alternados; 429/504 = ocupado
            url = urls[attempt % len(urls)]
            try:
                r = requests.post(url, data={"data": query(box)}, headers=UA, timeout=200)
                r.raise_for_status()
                js = r.json()
                if js.get("remark") and "error" in str(js["remark"]).lower():
                    raise ValueError(str(js["remark"])[:100])
                parse(js).assign(fetched=today.isoformat()).to_parquet(_tile_path(tiles, box), index=False)
                got_n += 1
                break
            except Exception as e:  # noqa: BLE001
                err = f"{box}: {str(e)[:90]}"
                if attempt == 0:
                    time.sleep(float(cfg.get("retry_wait", 10)))
        else:
            errors.append(err)
        time.sleep(float(cfg.get("delay", 1)))
    missing = [b for b in BOXES if age(b) is None]
    note = f"{got_n} quadrículas novas" + (f"; {len(errors)} falhas ({errors[0]})" if errors else "")
    if not missing:
        parts = [pd.read_parquet(_tile_path(tiles, b)) for b in BOXES]
        pts = pd.concat(parts, ignore_index=True)
        oldest = min(pts["fetched"].astype(str)) if len(pts) else today.isoformat()
        pts = pts.drop(columns=["fetched"]).drop_duplicates().assign(fetched=oldest)
        if len(pts) >= 1000:
            pts.to_parquet(path, index=False)
            return pts, "ok (" + ", ".join(f"{k}: {int((pts['kind'] == k).sum())}" for k in KINDS) + f"; {note})"
        errors.append(f"só {len(pts)} pontos")
    msg = f"faltam {len(missing)} de {len(BOXES)} quadrículas, continua no próximo build; {note}"
    log.warning("OpenStreetMap: %s", msg)
    if cached is not None:
        return cached, f"CACHE ({msg})"[:300]
    return None, f"ERRO: {msg}"[:300]


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
