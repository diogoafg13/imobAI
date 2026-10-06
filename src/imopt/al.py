"""Alojamento local por freguesia: Registo Nacional de Alojamento Local (RNAL), Turismo de Portugal, dados abertos.

O RNAL em dados abertos tem um registo por estabelecimento (continente), com coordenadas, freguesia, concelho e
n.º de utentes. Cada registo é ligado à freguesia pelas coordenadas (fronteiras do painel), o que evita os nomes
antigos e as uniões de freguesias de 2013; sem coordenadas, pelo nome da freguesia dentro do concelho.

- Descarregado no máximo uma vez por semana (o ficheiro tem >100 mil linhas); fica em data/clean/al_points.parquet
  só com as colunas usadas, e as primeiras linhas brutas em data/raw/al/ para se confirmar a leitura.
- Opcional: se o portal não responder ou o formato mudar, o painel continua sem estes números.
- Registado não é o mesmo que ativo: o RNAL inclui estabelecimentos que já não funcionam, se não tiverem sido
  cancelados. Por isso a medida é "registos", não "casas em AL".
"""
from __future__ import annotations

import datetime as dt
import io
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import geo

log = logging.getLogger("imopt")
UA = {"User-Agent": "imobiliario-pt/0.1 (dados abertos)"}
MAX_AGE_DAYS = 7
PARSER_V = 2          # sobe quando a leitura muda: o ficheiro guardado com uma versão anterior é relido


def _col(cols: list[str], *pats: str, avoid: tuple[str, ...] = ()) -> str | None:
    low = {c: geo.norm_name(c) for c in cols}
    for p in pats:
        for c, n in low.items():
            if re.search(p, n) and not any(a in n for a in avoid):
                return c
    return None


def read_points(text: str) -> pd.DataFrame:
    """CSV do RNAL -> colunas normalizadas: lat, lon, freguesia, concelho, utentes (as que existirem)."""
    first = text.splitlines()[0] if text else ""
    sep = ";" if first.count(";") > first.count(",") else ","
    df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, low_memory=False)
    cols = list(df.columns)
    # o RNAL traz o código DICOFRE da freguesia (DTMNFR), coordenadas em "LatLong" ("37,06 ; -7,82") e X/Y em metros
    # (Web Mercator, não usados); a ordem dos padrões evita apanhar "LatLong" como latitude
    pick = {"code": _col(cols, r"^dtmnfr$", r"dicofre"), "latlong": _col(cols, r"^latlong$"),
            "lat": _col(cols, r"^latitude$", r"^lat$"), "lon": _col(cols, r"^longitude$", r"^lon$", r"^long$"),
            "freguesia": _col(cols, r"^freguesia"), "concelho": _col(cols, r"^concelho", r"^municipio"),
            "utentes": _col(cols, r"utentes", r"capacidade")}
    if not pick["code"] and not pick["freguesia"] and not pick["latlong"] and not (pick["lat"] and pick["lon"]):
        raise ValueError(f"CSV sem código, coordenadas nem freguesia reconhecíveis (colunas: {cols[:30]})")
    out = pd.DataFrame({k: df[c] for k, c in pick.items() if c})
    if "code" in out:
        out["code"] = out["code"].astype(str).str.strip().str.extract(r"(\d+)")[0].str.zfill(6)
    if "latlong" in out:
        ll = out.pop("latlong").astype(str).str.split(";", expand=True)
        if ll.shape[1] >= 2:
            out["lat"] = ll[0].str.strip()
            out["lon"] = ll[1].str.strip()
    for k in ("lat", "lon", "utentes"):
        if k in out:
            out[k] = pd.to_numeric(out[k].str.replace(",", ".", regex=False), errors="coerce")
    if "lat" in out and "lon" in out:
        # coordenadas trocadas (lat ~ -8, lon ~ 40) acontecem em exportações ArcGIS
        swap = out["lat"].between(-32, -6) & out["lon"].between(30, 43)
        out.loc[swap, ["lat", "lon"]] = out.loc[swap, ["lon", "lat"]].to_numpy()
    return out


def ingest(cfg: dict | None, data_dir: Path, today: str) -> tuple[pd.DataFrame | None, str]:
    path = data_dir / "clean" / "al_points.parquet"
    cached = pd.read_parquet(path) if path.exists() else None
    if not cfg:
        return cached, "sem configuração"
    if cached is not None and ("parser_v" not in cached or int(cached["parser_v"].max()) < PARSER_V):
        cached = None
    if cached is not None and "fetched" in cached and len(cached):
        age = (dt.date.today() - dt.date.fromisoformat(str(cached["fetched"].iloc[0]))).days
        if age < MAX_AGE_DAYS:
            return cached, f"ok (cache de {cached['fetched'].iloc[0]}: {len(cached)} registos)"
    errors = []
    for url in cfg.get("urls", []):
        try:
            r = requests.get(url, headers=UA, timeout=300)
            r.raise_for_status()
            # o servidor não declara a codificação e o requests assumia latin-1 ("OlhÃ£o"): o ficheiro é UTF-8
            text = r.content.decode("utf-8-sig", errors="replace")
            raw = data_dir / "raw" / "al"
            raw.mkdir(parents=True, exist_ok=True)
            (raw / f"sample_{today}.csv").write_text("\n".join(text.splitlines()[:50]), encoding="utf-8")
            pts = read_points(text)
            if len(pts) < 10000:
                raise ValueError(f"só {len(pts)} registos")
            pts["fetched"] = dt.date.today().isoformat()
            pts["parser_v"] = PARSER_V
            path.parent.mkdir(parents=True, exist_ok=True)
            pts.to_parquet(path, index=False)
            return pts, f"ok ({len(pts)} registos, {url})"
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url}: {str(e)[:150]}")
    log.warning("alojamento local (RNAL) indisponível: %s", "; ".join(errors))
    if cached is not None:
        return cached, "CACHE (" + "; ".join(errors)[:200] + ")"
    return None, "ERRO: " + ("; ".join(errors) or "sem URL configurado")[:250]


def by_parish(points: pd.DataFrame | None, parish_geo: dict | None,
              names: dict[str, tuple[str, str]] | None = None) -> pd.DataFrame | None:
    """Registos e utentes por freguesia (código DICOFRE). `names`: {code: (nome da freguesia, nome do concelho)}
    para os registos sem coordenadas."""
    if points is None or points.empty:
        return None
    code = points["code"].where(points["code"].astype(str).str.fullmatch(r"\d{6}"), None) if "code" in points else \
        pd.Series(None, index=points.index, dtype=object)
    if parish_geo:   # códigos que não existem nas fronteiras atuais (ex.: freguesias antigas) vão pelas coordenadas
        known = {str((f.get("properties") or {}).get("code")) for f in parish_geo.get("features", [])}
        code = code.where(code.isin(known), None)
    if parish_geo and "lat" in points and "lon" in points and code.isna().any():
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
        if polys:
            tree = STRtree(polys)
            ok = points["lat"].notna() & points["lon"].notna() & code.isna()
            pts = [Point(x, y) for x, y in zip(points.loc[ok, "lon"], points.loc[ok, "lat"])]
            hit_pt, hit_poly = tree.query(pts, predicate="within")
            idx = points.index[ok]
            found = pd.Series([codes[j] for j in hit_poly], index=idx[hit_pt])
            found = found[~found.index.duplicated()]
            code.loc[found.index] = found
    if names and "freguesia" in points:
        key = {(geo.norm_name(f), geo.norm_name(c)): k for k, (f, c) in names.items()}
        miss = code.isna()
        if "concelho" in points:
            code.loc[miss] = [key.get((geo.norm_name(f), geo.norm_name(c))) for f, c in
                              zip(points.loc[miss, "freguesia"].fillna(""), points.loc[miss, "concelho"].fillna(""))]
    d = points.assign(code=code).dropna(subset=["code"])
    if d.empty:
        return None
    g = d.groupby("code")
    out = pd.DataFrame({"al_n": g.size()})
    if "utentes" in d:
        out["al_users"] = g["utentes"].sum(min_count=1)
    out.attrs["matched"] = float(len(d) / len(points))
    return out


def per_parish_fields(al: pd.DataFrame | None, census_total: pd.Series | None) -> pd.DataFrame | None:
    """al_n, al_users e al_per_100 (registos por 100 alojamentos do Censos 2021)."""
    if al is None or al.empty:
        return None
    out = al.copy()
    if census_total is not None:
        tot = census_total.reindex(out.index)
        out["al_per_100"] = (out["al_n"] / tot * 100).where(tot > 0)
    return out.replace([np.inf, -np.inf], np.nan)
