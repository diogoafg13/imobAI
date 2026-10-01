"""Pesquisa de indicadores no INE por palavras: `python -m imopt search <termos>`.

Usa a API de catálogo documentada pelo INE (xml_indic.jsp):
- opc=3: catálogo dos ~260 "indicadores principais" (nem todos os indicadores estão aqui);
- opc=1&varcd=X: ficha de um indicador — permite varrer um intervalo de códigos (`--range`), útil porque
  indicadores da mesma operação estatística costumam ter códigos próximos.
Também aceita um ficheiro XML do catálogo já descarregado (`--file`).
"""
from __future__ import annotations

import re
import time
import unicodedata
from pathlib import Path

import requests

XML_URL = "https://www.ine.pt/ine/xml_indic.jsp"
UA = {"User-Agent": "imobiliario-pt/0.1 (dados abertos INE)"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _tag(block: str, name: str) -> str | None:
    m = re.search(rf"<{name}>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</{name}>", block, flags=re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def parse_catalog(xml: str) -> list[dict]:
    out = []
    for b in re.findall(r"<indicator\b.*?</indicator>", xml, flags=re.S):
        varcd = _tag(b, "varcd")
        if not varcd:
            continue
        out.append({"varcd": varcd.strip(), "title": _tag(b, "title") or "", "geo": _tag(b, "geo_lastlevel") or "",
                    "periodicity": _tag(b, "periodicity") or "", "last": _tag(b, "last_period_available") or "",
                    "source": _tag(b, "source") or ""})
    return out


def matches(items: list[dict], terms: list[str]) -> list[dict]:
    words = [_norm(t) for t in terms]
    return [i for i in items if all(w in _norm(f"{i['title']} {i['source']}") for w in words)]


def fetch_main_catalog(lang: str = "PT") -> list[dict]:
    r = requests.get(XML_URL, params={"opc": 3, "lang": lang}, headers=UA, timeout=300)
    r.raise_for_status()
    return parse_catalog(r.text)


def scan_range(start: int, end: int, lang: str = "PT", delay: float = 0.3, progress=None) -> list[dict]:
    out = []
    for n in range(start, end + 1):
        varcd = f"{n:07d}"
        try:
            r = requests.get(XML_URL, params={"opc": 1, "varcd": varcd, "lang": lang}, headers=UA, timeout=60)
            if r.ok:
                out += parse_catalog(r.text)
        except requests.RequestException:
            pass
        if progress:
            progress(n - start + 1, end - start + 1)
        time.sleep(delay)
    return out


def load_file(path: str | Path) -> list[dict]:
    return parse_catalog(Path(path).read_text(encoding="utf-8", errors="replace"))
