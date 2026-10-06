"""Descoberta de fontes: guarda no branch `data` o que é preciso para encontrar códigos novos sem os inventar.

Corre em cada build (passo fixo, sem parâmetros vindos de fora), no máximo uma vez por semana:
- INE: catálogo de indicadores (xml_indic.jsp). Tenta o catálogo completo (opc=2); se não vier, o dos indicadores
  principais (opc=3) e uma varredura progressiva de intervalos de códigos (config `discover.ine_ranges`), com um
  limite de pedidos por build. Resultado: data/clean/ine_catalog.json (código, título, nível geográfico,
  periodicidade, último período) — para encontrar, por exemplo, o código novo de uma série parada.
- Serviços de mapas (config `discover.services`, ex.: zonas inundáveis da APA): a descrição em JSON (camadas e
  campos), em data/raw/services/.

Nada disto entra nos números do painel: é só para se confirmar códigos e camadas antes de os usar.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import time
from pathlib import Path

import requests

from . import catalog

log = logging.getLogger("imopt")
UA = {"User-Agent": "imobiliario-pt/0.1 (dados abertos)"}
MAX_AGE_DAYS = 7


def _fresh(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if (dt.date.today() - dt.date.fromisoformat(d.get("updated", "1900-01-01"))).days < MAX_AGE_DAYS and d.get("complete"):
            return d
        return d | {"stale": True}
    except Exception:  # noqa: BLE001
        return None


def ine_catalog(cfg: dict, data_dir: Path) -> str:
    path = data_dir / "clean" / "ine_catalog.json"
    prev = _fresh(path)
    if prev and not prev.get("stale"):
        return f"ok (cache: {len(prev.get('items', []))} indicadores)"
    items: dict[str, dict] = {i["varcd"]: i for i in (prev or {}).get("items", [])}
    scanned: set[int] = set((prev or {}).get("scanned", []))
    notes = []
    try:          # catálogo completo, se o INE o servir
        r = requests.get(catalog.XML_URL, params={"opc": 2, "lang": "PT"}, headers=UA, timeout=600)
        full = catalog.parse_catalog(r.text) if r.ok else []
        notes.append(f"opc=2: {len(full)}")
        items.update({i["varcd"]: i for i in full})
    except Exception as e:  # noqa: BLE001
        notes.append(f"opc=2 falhou: {str(e)[:80]}")
    complete = len(items) > 2000
    if not complete:
        try:
            main = catalog.fetch_main_catalog()
            items.update({i["varcd"]: i for i in main})
            notes.append(f"opc=3: {len(main)}")
        except Exception as e:  # noqa: BLE001
            notes.append(f"opc=3 falhou: {str(e)[:80]}")
        budget = int(cfg.get("max_requests", 400))
        todo = []
        for rng in cfg.get("ine_ranges", []):
            a, b = (int(x) for x in str(rng).split("-"))
            todo += [n for n in range(a, b + 1) if n not in scanned]
        for n in todo[:budget]:
            try:
                rr = requests.get(catalog.XML_URL, params={"opc": 1, "varcd": f"{n:07d}", "lang": "PT"}, headers=UA, timeout=60)
                if rr.ok:
                    items.update({i["varcd"]: i for i in catalog.parse_catalog(rr.text)})
                scanned.add(n)
            except requests.RequestException:
                pass
            time.sleep(float(cfg.get("delay", 0.2)))
        complete = not [n for n in todo if n not in scanned]
        notes.append(f"varridos {len(scanned)} códigos{'' if complete else ' (continua no próximo build)'}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"updated": dt.date.today().isoformat(), "complete": complete, "scanned": sorted(scanned),
                                "items": sorted(items.values(), key=lambda i: i["varcd"])}, ensure_ascii=False, indent=0),
                    encoding="utf-8")
    return f"ok ({len(items)} indicadores; {'; '.join(notes)})"


def services(cfg: dict, data_dir: Path) -> str:
    out_dir = data_dir / "raw" / "services"
    done = []
    for name, url in (cfg.get("services") or {}).items():
        try:
            r = requests.get(url, params={"f": "json"}, headers=UA, timeout=120)
            r.raise_for_status()
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{re.sub(r'[^0-9A-Za-z_]', '_', name)}.json").write_text(r.text, encoding="utf-8")
            # e a descrição de cada camada (campos), para escolher a certa
            js = r.json()
            for layer in (js.get("layers") or [])[:40]:
                lr = requests.get(f"{url.rstrip('/')}/{layer['id']}", params={"f": "json"}, headers=UA, timeout=60)
                if lr.ok:
                    (out_dir / f"{re.sub(r'[^0-9A-Za-z_]', '_', name)}_{layer['id']}.json").write_text(lr.text, encoding="utf-8")
            done.append(f"{name}: {len(js.get('layers') or [])} camadas")
        except Exception as e:  # noqa: BLE001
            done.append(f"{name}: falhou ({str(e)[:80]})")
    return "; ".join(done) or "sem serviços"


def run(cfg: dict | None, data_dir: Path) -> dict:
    if not cfg:
        return {}
    out = {}
    try:
        out["ine_catalog"] = ine_catalog(cfg, data_dir)
    except Exception as e:  # noqa: BLE001
        out["ine_catalog"] = f"ERRO: {str(e)[:150]}"
    try:
        out["services"] = services(cfg, data_dir)
    except Exception as e:  # noqa: BLE001
        out["services"] = f"ERRO: {str(e)[:150]}"
    for k, v in out.items():
        log.info("descoberta %s: %s", k, v)
    return out
