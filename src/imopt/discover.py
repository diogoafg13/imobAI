"""Descoberta de fontes: guarda no branch `data` o que é preciso para encontrar códigos novos sem os inventar.

Corre em cada build (passo fixo, sem parâmetros vindos de fora), no máximo uma vez por semana:
- INE: catálogo de indicadores (xml_indic.jsp). Tenta o catálogo completo (opc=2); se não vier, o dos indicadores
  principais (opc=3) e uma varredura progressiva de intervalos de códigos (config `discover.ine_ranges`), com um
  limite de pedidos por build. Resultado: data/clean/ine_catalog.json (código, título, nível geográfico,
  periodicidade, último período) — para encontrar, por exemplo, o código novo de uma série parada.
- INE, sonda (config `discover.ine_probe`): para cada código novo, o JSON completo uma vez (sem filtros) em
  data/raw/ine/<código>/ e um resumo em data/clean/ine_probe.json (dimensões com códigos e nomes, níveis
  geográficos, primeiro e último período) — para escrever os `dims` certos no config sem adivinhar.
- APIs OGC (config `discover.ogc`, ex.: DGT, Carta do Regime de Uso do Solo dos PDM e RAN/REN): a lista de coleções,
  e para algumas a descrição, os campos e 5 elementos de exemplo, mais o cabeçalho CORS (se o site pode consultar a
  API diretamente do browser), em data/raw/services/ e data/clean/ogc_probe.json.
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

from . import catalog, ine

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


def summarize(df) -> dict:
    """Resumo de uma resposta do INE: dimensões (código -> nome), níveis geográficos e períodos."""
    dims = {}
    for c in sorted(c for c in df.columns if re.fullmatch(r"dim_\d+", c)):
        t = f"{c}_t"
        pairs = df[[c, t]].drop_duplicates() if t in df.columns else df[[c]].drop_duplicates().assign(_t="")
        dims[c] = {str(a): str(b) for a, b in pairs.head(60).itertuples(index=False)}
    lens = df["geocod"].astype(str).str.len().value_counts().to_dict() if "geocod" in df else {}
    per = sorted(df["period"].astype(str).unique()) if "period" in df else []
    return {"rows": int(len(df)), "dims": dims, "geocod_len": {str(k): int(v) for k, v in lens.items()},
            "periods": [per[0], per[-1], len(per)] if per else [],
            "sample": df.head(3).astype(str).to_dict("records")}


def ine_probe(cfg: dict, ine_cfg: dict, data_dir: Path, today: str) -> str:
    path = data_dir / "clean" / "ine_probe.json"
    done = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    notes, fails = [], 0
    deadline = time.monotonic() + float(cfg.get("probe_budget_s", 600))   # o build não fica preso à espera do INE
    for varcd in cfg.get("ine_probe") or []:
        varcd = str(varcd)
        if varcd in done and "error" not in done[varcd]:
            continue
        if time.monotonic() > deadline or fails >= 2:
            notes.append(f"{varcd}: fica para o próximo build")
            continue
        try:
            payload = ine.fetch(ine_cfg["base_url"], varcd, ine_cfg.get("lang", "PT"), None, retries=1, timeout=(10, 240))
            df = ine.parse_response(payload, varcd)
            if df.empty:
                raise ValueError("resposta vazia")
            out = data_dir / "raw" / "ine" / varcd / f"{today}.parquet"
            out.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(out, index=False)
            done[varcd] = {"probed": today, **summarize(df)}
            notes.append(f"{varcd}: {len(df)} linhas")
            fails = 0
        except Exception as e:  # noqa: BLE001
            done[varcd] = {"error": str(e)[:200]}
            notes.append(f"{varcd}: falhou")
            fails += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    return "; ".join(notes) or f"nada novo ({len(done)} já sondados)"


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


def ogc_probe(cfg: dict, data_dir: Path) -> str:
    """Descobre uma API OGC (Features): coleções, campos e exemplos das que interessam. Uma vez por semana."""
    path = data_dir / "clean" / "ogc_probe.json"
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            if (dt.date.today() - dt.date.fromisoformat(prev.get("updated", "1900-01-01"))).days < MAX_AGE_DAYS and prev.get("ok"):
                return f"ok (cache: {prev.get('summary')})"
        except Exception:  # noqa: BLE001
            pass
    out_dir = data_dir / "raw" / "services"
    out_dir.mkdir(parents=True, exist_ok=True)
    res: dict = {"updated": dt.date.today().isoformat(), "apis": {}}
    notes = []
    for name, spec in (cfg or {}).items():
        base = spec["base"].rstrip("/")
        info: dict = {}
        try:
            r = requests.get(f"{base}/collections", params={"f": "json"}, headers={**UA, "Origin": "https://example.github.io"}, timeout=120)
            r.raise_for_status()
            info["cors"] = r.headers.get("Access-Control-Allow-Origin")
            (out_dir / f"{name}_collections.json").write_text(r.text, encoding="utf-8")
            cols = [c.get("id") for c in r.json().get("collections", []) if c.get("id")]
            info["n_collections"] = len(cols)
            for pat in spec.get("grep", []):
                hits = [c for c in cols if re.search(pat, c, re.I)]
                info[f"match_{pat}"] = {"n": len(hits), "first": hits[:15]}
            samples = list(spec.get("sample", []))
            for pat in spec.get("grep", []):           # e a primeira coleção de cada padrão
                samples += [c for c in cols if re.search(pat, c, re.I)][:1]
            info["samples"] = {}
            for cid in dict.fromkeys(samples):
                one: dict = {}
                for suffix, key, params in (("", "meta", {"f": "json"}), ("/queryables", "queryables", {"f": "json"}),
                                            ("/items", "items", {"f": "json", "limit": 5})):
                    try:
                        rr = requests.get(f"{base}/collections/{cid}{suffix}", params=params, headers=UA, timeout=120)
                        one[f"{key}_status"] = rr.status_code
                        if rr.ok:
                            fn = f"{name}_{re.sub(r'[^0-9A-Za-z_]', '_', cid)}_{key}.json"
                            (out_dir / fn).write_text(rr.text[:2_000_000], encoding="utf-8")
                            if key == "items":
                                feats = rr.json().get("features", [])
                                one["properties"] = sorted({k for f in feats for k in (f.get("properties") or {})})
                                one["example"] = (feats[0].get("properties") if feats else None)
                                one["geometry"] = feats[0]["geometry"]["type"] if feats and feats[0].get("geometry") else None
                    except Exception as e:  # noqa: BLE001
                        one[f"{key}_error"] = str(e)[:120]
                info["samples"][cid] = one
            notes.append(f"{name}: {len(cols)} coleções" + "".join(f", {k[6:]}: {v['n']}" for k, v in info.items() if k.startswith("match_")))
        except Exception as e:  # noqa: BLE001
            info["error"] = str(e)[:200]
            notes.append(f"{name}: falhou ({str(e)[:80]})")
        res["apis"][name] = info
    res["ok"] = all("error" not in v for v in res["apis"].values())
    res["summary"] = "; ".join(notes)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res["summary"] or "sem APIs"


def run(cfg: dict | None, data_dir: Path, ine_cfg: dict | None = None, today: str | None = None) -> dict:
    if not cfg:
        return {}
    out = {}
    if ine_cfg and cfg.get("ine_probe"):
        try:
            out["ine_probe"] = ine_probe(cfg, ine_cfg, data_dir, today or dt.date.today().strftime("%Y%m%d"))
        except Exception as e:  # noqa: BLE001
            out["ine_probe"] = f"ERRO: {str(e)[:150]}"
    try:
        out["ine_catalog"] = ine_catalog(cfg, data_dir)
    except Exception as e:  # noqa: BLE001
        out["ine_catalog"] = f"ERRO: {str(e)[:150]}"
    if cfg.get("ogc"):
        try:
            out["ogc"] = ogc_probe(cfg["ogc"], data_dir)
        except Exception as e:  # noqa: BLE001
            out["ogc"] = f"ERRO: {str(e)[:150]}"
    try:
        out["services"] = services(cfg, data_dir)
    except Exception as e:  # noqa: BLE001
        out["services"] = f"ERRO: {str(e)[:150]}"
    for k, v in out.items():
        log.info("descoberta %s: %s", k, v)
    return out
