"""Taxas de IMI por concelho (Autoridade Tributária, consulta pública "Taxas IMI/CA por Município e Ano").

A AT publica, por ano e distrito, a taxa de IMI dos prédios urbanos fixada por cada município (0,3% a 0,45%),
as taxas diferenciadas por freguesia, quando existem, e a dedução fixa do IMI familiar por n.º de dependentes.

- Um pedido ao formulário (anos e distritos disponíveis) e, só quando aparece um ano que ainda não temos, um
  pedido por distrito (~20), com uma pausa entre pedidos. O HTML bruto fica em data/raw/imi/ (branch `data`),
  para se poder confirmar a leitura; o resultado em data/clean/imi_rates.parquet.
- Tudo opcional: se a AT não responder ou a página mudar, o painel continua sem a taxa de IMI.

O IMI incide sobre o valor patrimonial tributário (VPT, na caderneta predial), não sobre o preço de mercado:
IMI = VPT × taxa (menos a dedução do IMI familiar, se houver dependentes).
"""
from __future__ import annotations

import html
import logging
import re
import time
from pathlib import Path

import pandas as pd
import requests

from . import geo

log = logging.getLogger("imopt")
UA = {"User-Agent": "imobiliario-pt/0.1 (dados abertos)"}


def _strip(cell: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cell))).strip()


def table_rows(page: str) -> list[list[str]]:
    """Linhas de todas as tabelas da página (texto das células), sem depender de bibliotecas de HTML."""
    rows = []
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", page, flags=re.S | re.I):
        cells = [_strip(c) for c in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, flags=re.S | re.I)]
        if any(cells):
            rows.append(cells)
    return rows


def select_options(page: str) -> dict[str, list[str]]:
    """{nome do select: [valores das opções]} de um formulário."""
    out = {}
    for name, body in re.findall(r"<select\b[^>]*name=[\"']?([\w-]+)[^>]*>(.*?)</select>", page, flags=re.S | re.I):
        out[name] = [v for v in re.findall(r"<option\b[^>]*value=[\"']?([^\"'>]*)", body, flags=re.I) if v.strip()]
    return out


def parse_rate(text: str) -> float | None:
    """'0,300%' / '0,3' / '0.0035' -> fração (0.003). Taxas de prédios urbanos ficam entre 0,3% e 0,45%."""
    m = re.search(r"\d+(?:[.,]\d+)?", text or "")
    if not m:
        return None
    v = float(m.group(0).replace(",", "."))
    if 0.1 <= v <= 1:          # em percentagem
        v /= 100
    return round(v, 6) if 0.001 <= v <= 0.01 else None


def parse_money(text: str) -> float | None:
    m = re.search(r"\d[\d .]*(?:,\d+)?", text or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(" ", "").replace(".", "").replace(",", "."))
    except ValueError:
        return None


def parse_district(page: str) -> list[dict]:
    """Linhas (município, taxa urbana, deduções) de uma página de distrito. Procura o cabeçalho pelas palavras
    'munic' e 'urban'; as colunas do IMI familiar pelas palavras 'depend' ou 'dedu'."""
    rows = table_rows(page)
    out = []
    head_i = next((i for i, r in enumerate(rows)
                   if any("munic" in c.lower() for c in r) and any("urban" in c.lower() for c in r)), None)
    if head_i is None:
        return out
    head = [c.lower() for c in rows[head_i]]
    ci_mun = next(i for i, c in enumerate(head) if "munic" in c)
    ci_urb = next(i for i, c in enumerate(head) if "urban" in c)
    ci_ded = [i for i, c in enumerate(head) if "depend" in c or "dedu" in c]
    ci_par = next((i for i, c in enumerate(head) if "freguesia" in c), None)
    for r in rows[head_i + 1:]:
        if len(r) <= max(ci_mun, ci_urb):
            continue
        rate = parse_rate(r[ci_urb])
        if rate is None:
            continue
        cell = r[ci_mun]
        code = re.search(r"\b(\d{4})\b", " ".join(r[:ci_mun + 1]))
        name = re.sub(r"^[\d\s\-–.]+", "", cell).strip()
        item = {"code": code.group(1) if code else None, "name": name, "rate_urban": rate,
                "parish_rates": bool(ci_par is not None and len(r) > ci_par and re.search(r"\d", r[ci_par]))}
        for k, i in enumerate(ci_ded[:3], 1):
            item[f"ded_{k}"] = parse_money(r[i]) if len(r) > i else None
        out.append(item)
    return out


def _get(url: str, params: dict) -> str:
    r = requests.get(url, params=params, headers=UA, timeout=60)
    r.raise_for_status()
    r.encoding = r.encoding or "iso-8859-1"
    return r.text


def ingest(cfg: dict | None, data_dir: Path, today: str, names: dict[str, str] | None = None,
           pause: float = 1.0) -> tuple[pd.DataFrame | None, str]:
    """Taxas de IMI do ano mais recente publicado pela AT. Devolve (tabela por concelho, estado para o site)."""
    cached_path = data_dir / "clean" / "imi_rates.parquet"
    cached = pd.read_parquet(cached_path) if cached_path.exists() else None
    if not cfg:
        return cached, "sem configuração"
    raw = data_dir / "raw" / "imi"
    try:
        form = _get(cfg["form_url"], cfg.get("form_params", {}))
        raw.mkdir(parents=True, exist_ok=True)
        (raw / f"form_{today}.html").write_text(form, encoding="utf-8")
        opts = select_options(form)
        years = sorted({int(v) for vals in opts.values() for v in vals if re.fullmatch(r"20\d\d", v.strip())})
        dists = next((vals for vals in opts.values() if vals and all(re.match(r"\d\d", v) for v in vals)), [])
        if not years or not dists:
            raise ValueError(f"formulário sem anos/distritos reconhecíveis (selects: {list(opts)})")
        year = years[-1]
        if cached is not None and len(cached) >= 250 and int(cached["year"].max()) >= year:
            return cached, f"ok (cache: taxas de {year} já recolhidas)"
        rows = []
        for i, d in enumerate(dists):
            if i:
                time.sleep(pause)
            page = _get(cfg["table_url"], {**cfg.get("table_params", {}), "ano": year, "distrito": d})
            (raw / str(year)).mkdir(parents=True, exist_ok=True)
            (raw / str(year) / f"{re.sub(r'[^0-9A-Za-z]', '_', d)}.html").write_text(page, encoding="utf-8")
            rows += [{**r, "district": d} for r in parse_district(page)]
        if not rows:
            raise ValueError("páginas dos distritos sem tabela reconhecível (ver data/raw/imi)")
        df = pd.DataFrame(rows)
        df["year"] = year
        by_name = {geo.norm_name(n): d for d, n in (names or {}).items()}
        df["dico"] = [c if c else by_name.get(geo.norm_name(n)) for c, n in zip(df["code"], df["name"])]
        n_ok = int(df["dico"].notna().sum())
        if n_ok < 250:
            raise ValueError(f"só {n_ok} concelhos reconhecidos em {len(df)} linhas (ver data/raw/imi)")
        df = df.dropna(subset=["dico"]).drop_duplicates("dico")
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cached_path, index=False)
        return df, f"ok ({len(df)} concelhos, taxas de {year})"
    except Exception as e:  # noqa: BLE001
        log.warning("taxas de IMI (AT) indisponíveis: %s", e)
        if cached is not None:
            return cached, f"CACHE ({str(e)[:150]})"
        return None, f"ERRO: {str(e)[:200]}"


def per_municipality(df: pd.DataFrame | None) -> dict[str, dict]:
    """{dico: campos para o site}."""
    if df is None or df.empty:
        return {}
    out = {}
    for r in df.to_dict("records"):
        item = {"imi_rate": round(float(r["rate_urban"]), 6), "imi_year": int(r["year"]), "imi_parish_rates": bool(r.get("parish_rates"))}
        for k in (1, 2, 3):
            v = r.get(f"ded_{k}")
            if v is not None and v == v:
                item[f"imi_ded_{k}"] = float(v)
        out[str(r["dico"])] = item
    return out
