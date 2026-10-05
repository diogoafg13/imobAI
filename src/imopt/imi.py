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
PARSER_V = 2          # sobe quando a leitura muda: a tabela guardada com uma versão anterior é refeita


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
    # "Código Municipio" e "Município": o nome é a coluna com "munic" sem "código"
    ci_mun = next((i for i, c in enumerate(head) if "munic" in c and "dig" not in c), next(i for i, c in enumerate(head) if "munic" in c))
    ci_urb = next(i for i, c in enumerate(head) if "urban" in c)
    ci_ded = [i for i, c in enumerate(head) if "depend" in c or "dedu" in c]
    ci_par = next((i for i, c in enumerate(head) if "freguesia" in c), None)
    for r in rows[head_i + 1:]:
        if len(r) <= max(ci_mun, ci_urb):
            continue
        rate = parse_rate(r[ci_urb])
        # com taxas diferentes por freguesia, a AT não dá taxa única ("-") e põe uma ligação ("+Info")
        parish = bool(ci_par is not None and len(r) > ci_par and r[ci_par].strip())
        code = re.search(r"\b(\d{4})\b", " ".join(r[:ci_mun + 1]))
        name = re.sub(r"^[\d\s\-–.]+", "", r[ci_mun]).strip()
        if not name or (rate is None and not parish):
            continue
        item = {"code": code.group(1) if code else None, "name": name, "rate_urban": rate, "parish_rates": parish}
        for k, i in enumerate(ci_ded[:3], 1):      # na página atual a dedução é uma ligação ("+Info"): fica vazia
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
    if cached is not None and ("parser_v" not in cached or int(cached["parser_v"].max()) < PARSER_V):
        cached = None
    if not cfg:
        return cached, "sem configuração"
    raw = data_dir / "raw" / "imi"
    try:
        form = _get(cfg["form_url"], cfg.get("form_params", {}))
        raw.mkdir(parents=True, exist_ok=True)
        (raw / f"form_{today}.html").write_text(form, encoding="utf-8")
        opts = select_options(form)
        # selects "ano" (2026, 2025, …) e "distrito" ("11LISBOA", "19ANGRA DO HEROISMO", …); sem esses nomes, procura
        # pelo formato dos valores (o dos distritos tem letras depois dos 2 dígitos — os anos também começam por dígitos)
        year_vals = opts.get("ano") or next((v for v in opts.values() if v and all(re.fullmatch(r"\d{4}", x.strip()) for x in v)), [])
        dists = opts.get("distrito") or next((v for v in opts.values() if v and all(re.fullmatch(r"\d\d\D.*", x.strip()) for x in v)), [])
        years = sorted({int(v) for v in year_vals if re.fullmatch(r"20\d\d", v.strip())}, reverse=True)
        if not years or not dists:
            raise ValueError(f"formulário sem anos/distritos reconhecíveis (selects: {list(opts)})")
        if cached is not None and len(cached) >= 250 and int(cached["year"].max()) >= years[0]:
            return cached, f"ok (cache: taxas de {int(cached['year'].max())} já recolhidas)"
        # o ano mais recente pode ainda estar incompleto (as câmaras fixam as taxas até ao fim do ano): se tiver
        # poucos concelhos, usa o anterior
        rows, year = [], None
        for year in years[:2]:
            if cached is not None and len(cached) >= 250 and int(cached["year"].max()) >= year:
                return cached, f"ok (cache: taxas de {int(cached['year'].max())}; {years[0]} ainda incompleto)"
            rows = []
            for i, d in enumerate(dists):
                if i:
                    time.sleep(pause)
                page = _get(cfg["table_url"], {**cfg.get("table_params", {}), "ano": year, "distrito": d})
                (raw / str(year)).mkdir(parents=True, exist_ok=True)
                (raw / str(year) / f"{re.sub(r'[^0-9A-Za-z]', '_', d)}.html").write_text(page, encoding="utf-8")
                rows += [{**r, "district": d} for r in parse_district(page)]
            if len(rows) >= 250:
                break
        if len(rows) < 250:
            raise ValueError(f"só {len(rows)} linhas reconhecidas para {year} (ver data/raw/imi)")
        df = pd.DataFrame(rows)
        df["year"] = year
        df["dico"] = match_dico(df, names or {})
        n_ok = int(df["dico"].notna().sum())
        if n_ok < 250:
            raise ValueError(f"só {n_ok} concelhos reconhecidos em {len(df)} linhas (ver data/raw/imi)")
        df = df.dropna(subset=["dico"]).drop_duplicates("dico").assign(parser_v=PARSER_V)
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cached_path, index=False)
        return df, f"ok ({len(df)} concelhos, taxas de {year})"
    except Exception as e:  # noqa: BLE001
        log.warning("taxas de IMI (AT) indisponíveis: %s", e)
        if cached is not None:
            return cached, f"CACHE ({str(e)[:150]})"
        return None, f"ERRO: {str(e)[:200]}"


def _norm(name: str) -> str:
    n = re.sub(r"\(.*?\)", "", str(name))
    n = re.sub(r"\bS\.\s*", "SAO ", n.upper())
    n = re.sub(r"\b(DA|DE|DO|DAS|DOS)\b", " ", n)          # "Vila Praia da Vitória" = "Vila da Praia da Vitória"
    return geo.norm_name(n)


def match_dico(df: pd.DataFrame, names: dict[str, str]) -> list[str | None]:
    """Código da AT -> código DICO do INE. No continente são iguais (confirmado pelo nome); nas ilhas a AT usa os
    distritos 19-22 (Açores 19-21, Madeira 22) e o INE 31-32 (Madeira) e 41-49 (Açores): liga-se pelo nome,
    dentro da região (há Calheta e Lagoa nas duas regiões autónomas e Lagoa também no Algarve)."""
    by_region: dict[str, dict[str, str]] = {"C": {}, "M": {}, "A": {}}
    for d, n in names.items():
        reg = "M" if d[:2] in ("31", "32") else "A" if d[:1] == "4" else "C"
        by_region[reg][_norm(n)] = d
    out = []
    for code, name in zip(df["code"], df["name"]):
        c = str(code) if code else ""
        reg = "M" if c[:2] == "22" else "A" if c[:2] in ("19", "20", "21") else "C"
        if reg == "C" and c and (not names or (c in names and _norm(names[c]) == _norm(name))):
            out.append(c)
        else:
            out.append(by_region[reg].get(_norm(name)))
    return out


def per_municipality(df: pd.DataFrame | None) -> dict[str, dict]:
    """{dico: campos para o site}."""
    if df is None or df.empty:
        return {}
    out = {}
    for r in df.to_dict("records"):
        rate = r.get("rate_urban")
        item = {"imi_rate": None if rate is None or rate != rate else round(float(rate), 6), "imi_year": int(r["year"]),
                "imi_parish_rates": bool(r.get("parish_rates"))}
        for k in (1, 2, 3):
            v = r.get(f"ded_{k}")
            if v is not None and v == v:
                item[f"imi_ded_{k}"] = float(v)
        out[str(r["dico"])] = item
    return out
