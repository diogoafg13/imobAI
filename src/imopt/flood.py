"""Zonas inundáveis por freguesia: cartas da Diretiva 2007/60/CE (APA, SNIAmb, 2.º ciclo), dados abertos.

A APA publica as áreas inundáveis (camada "Limite") das Áreas de Risco Potencial Significativo de Inundação (ARPSI)
do continente, para vários períodos de retorno (cheias que acontecem, em média, uma vez em 20, 100 ou 1000 anos).
Usa-se o cenário de 100 anos (probabilidade média da diretiva) ou, se não existir, o mais próximo.

- Medida: % da área da freguesia dentro da área inundável cartografada. É uma aproximação: uma freguesia com 3% da
  área inundável pode ter aí o centro histórico; e a área não diz quantas casas estão lá dentro.
- Só as ARPSI estão cartografadas: uma freguesia sem zona cartografada NÃO quer dizer sem risco de cheia (fica sem
  valor, não a zero). Madeira e Açores não estão neste serviço.
- Descarregado no máximo uma vez por mês (as cartas mudam de ciclo em ciclo, de 6 em 6 anos), com a geometria
  simplificada (~5 m); fica em data/clean/flood_zones.geojson.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path

import requests

log = logging.getLogger("imopt")
UA = {"User-Agent": "imobiliario-pt/0.1 (dados abertos)"}
MAX_AGE_DAYS = 30
PAGE = 1000


def _years(v) -> float | None:
    m = re.search(r"\d+", str(v or ""))
    return float(m.group()) if m else None


def pick_return_period(values: list) -> object | None:
    """O valor de `pretorno` mais próximo de 100 anos (tal como vem no serviço)."""
    vals = [(v, _years(v)) for v in values if _years(v)]
    return min(vals, key=lambda t: (abs(t[1] - 100), t[1]))[0] if vals else None


def _query(url: str, params: dict) -> dict:
    r = requests.get(f"{url.rstrip('/')}/query", params={"f": "json", **params}, headers=UA, timeout=300)
    r.raise_for_status()
    js = r.json()
    if "error" in js:
        raise ValueError(str(js["error"])[:150])
    return js


def _where(field: str, value) -> str:
    return f"{field}={value}" if isinstance(value, (int, float)) else f"{field}='{value}'"


def esri_to_geojson(feat: dict) -> dict | None:
    """Polígono ArcGIS (anéis) -> GeoJSON MultiPolygon: anéis no sentido dos ponteiros do relógio são exteriores,
    os outros são buracos do exterior anterior (convenção do ArcGIS)."""
    rings = (feat.get("geometry") or {}).get("rings") or []
    polys: list[list] = []
    for ring in rings:
        if len(ring) < 4:
            continue
        area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:]))
        if area < 0 or not polys:          # sentido horário (área com sinal negativa) = exterior
            polys.append([ring])
        else:
            polys[-1].append(ring)
    if not polys:
        return None
    return {"type": "Feature", "properties": feat.get("attributes") or {},
            "geometry": {"type": "MultiPolygon", "coordinates": polys}}


def ingest(cfg: dict | None, data_dir: Path) -> tuple[dict | None, str]:
    path = data_dir / "clean" / "flood_zones.geojson"
    cached = None
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cached = None
    if not cfg:
        return cached, "sem configuração"
    if cached and cached.get("fetched"):
        age = (dt.date.today() - dt.date.fromisoformat(cached["fetched"])).days
        if age < MAX_AGE_DAYS:
            return cached, f"ok (cache de {cached['fetched']}: {len(cached['features'])} polígonos, {cached.get('scenario')})"
    url, field = cfg["url"], cfg.get("field", "pretorno")
    try:
        d = _query(url, {"where": "1=1", "outFields": field, "returnGeometry": "false", "returnDistinctValues": "true"})
        values = [f["attributes"].get(field) for f in d.get("features", [])]
        rp = pick_return_period(values)
        if rp is None:
            raise ValueError(f"sem períodos de retorno ({field}: {values[:10]})")
        feats, offset = [], 0
        while True:
            page = _query(url, {"where": _where(field, rp), "outFields": f"{field},designa,local", "returnGeometry": "true",
                                "outSR": 4326, "geometryPrecision": 5, "maxAllowableOffset": 0.00005,
                                "resultOffset": offset, "resultRecordCount": PAGE, "orderByFields": "objectid"})
            got = page.get("features", [])
            feats += [g for g in (esri_to_geojson(f) for f in got) if g]
            if len(got) < PAGE and not page.get("exceededTransferLimit"):
                break
            offset += len(got)
            if not got or offset > 200000:
                break
        if len(feats) < 10:
            raise ValueError(f"só {len(feats)} polígonos")
        out = {"type": "FeatureCollection", "fetched": dt.date.today().isoformat(), "scenario": f"{field}={rp}", "rp_years": _years(rp),
               "return_periods": values, "features": feats}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return out, f"ok ({len(feats)} polígonos, {field}={rp}; disponíveis: {values})"
    except Exception as e:  # noqa: BLE001
        log.warning("zonas inundáveis (APA) indisponíveis: %s", e)
        if cached:
            return cached, f"CACHE ({str(e)[:150]})"
        return None, f"ERRO: {str(e)[:200]}"


def by_parish(zones: dict | None, parish_geo: dict | None) -> dict[str, float] | None:
    """{código da freguesia: % da área em zona inundável cartografada}; só freguesias que tocam numa zona.
    As áreas são calculadas em graus: como a razão é entre áreas da mesma freguesia (a mesma latitude), a distorção
    da projeção anula-se."""
    if not zones or not zones.get("features") or not parish_geo:
        return None
    from shapely.geometry import shape
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    geoms = []
    for f in zones["features"]:
        try:
            g = shape(f["geometry"])
            geoms.append(g if g.is_valid else g.buffer(0))
        except Exception:  # noqa: BLE001
            continue
    if not geoms:
        return None
    tree = STRtree(geoms)
    out = {}
    for f in parish_geo.get("features", []):
        code = (f.get("properties") or {}).get("code")
        if not code or not f.get("geometry"):
            continue
        try:
            p = shape(f["geometry"])
            p = p if p.is_valid else p.buffer(0)
            idx = tree.query(p, predicate="intersects")
            if len(idx) == 0 or p.area <= 0:
                continue
            inter = unary_union([geoms[i] for i in idx]).intersection(p).area
            if inter > 0:
                out[str(code)] = round(100 * inter / p.area, 2)
        except Exception:  # noqa: BLE001
            continue
    return out
