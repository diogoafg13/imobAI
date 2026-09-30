"""Cliente e parser da API JSON do INE (pindica.jsp).

Formato de resposta esperado (documentação INE):
    [ { "IndicadorCod": "...", "Dados": { "<período>": [ {geocod, geodsg, valor, dim_N, dim_N_t, ...}, ... ] } } ]

O parser é tolerante: a estrutura exata não foi verificada ao vivo, por isso tudo o
que é ambíguo (períodos, dimensões extra) é tratado explicitamente e falha com
mensagens claras em vez de produzir dados errados.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests

MONTHS_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}


class AmbiguousDimensionError(RuntimeError):
    """Vários valores por (local, período) por causa de dimensões extra não filtradas."""


@dataclass(frozen=True)
class Period:
    label: str      # forma normalizada: 2024, 2024Q3, 2024-03
    kind: str       # year | quarter | month
    year: int
    sub: int        # trimestre ou mês (0 se anual)

    @property
    def sort_key(self) -> int:
        return self.year * 100 + self.sub


def parse_period(raw: str) -> Period:
    s = str(raw).strip().lower()
    m = re.search(r"(19|20)\d{2}", s)
    if not m:
        raise ValueError(f"período sem ano: {raw!r}")
    year = int(m.group(0))
    q = re.search(r"(?:^|[^\d])([1-4])\s*(?:[.ºo°]*\s*trimestre)", s) or re.search(r"(?<![a-z])[tq]([1-4])(?!\d)", s)
    if q:
        n = next(int(g) for g in q.groups() if g)
        return Period(f"{year}Q{n}", "quarter", year, n)
    for name, n in MONTHS_PT.items():
        if name in s:
            return Period(f"{year}-{n:02d}", "month", year, n)
    mm = re.search(r"m(\d{1,2})\b", s)
    if mm and 1 <= int(mm.group(1)) <= 12:
        n = int(mm.group(1))
        return Period(f"{year}-{n:02d}", "month", year, n)
    return Period(str(year), "year", year, 0)


def classify_level(geocod: str) -> str:
    g = str(geocod).strip()
    if g.upper() in {"PT", "1", "0"} and not g.isdigit():
        return "national"
    if g.upper() == "PT":
        return "national"
    if g.isdigit():
        return {1: "nuts1", 2: "nuts2", 3: "nuts3", 7: "municipality", 9: "parish"}.get(len(g), "other")
    return "other"


def dico_from_geocod(geocod: str) -> str | None:
    """Código DICO (4 dígitos) de um concelho a partir do geocod INE de 7 dígitos."""
    g = str(geocod).strip()
    return g[-4:] if g.isdigit() and len(g) == 7 else None


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if s in {"", "x", "X", "-", "..", "…", "nan", "None"}:
        return None
    s = s.replace(" ", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_response(payload: Any, varcd: str) -> pd.DataFrame:
    """Converte o JSON do INE num DataFrame longo.

    Colunas: varcd, period, period_kind, sort_key, geocod, geoname, level, dico, value,
    e dim_N / dim_N_t para cada dimensão extra encontrada.
    """
    block = None
    if isinstance(payload, list):
        block = next((b for b in payload if isinstance(b, dict) and "Dados" in b), None)
    elif isinstance(payload, dict) and "Dados" in payload:
        block = payload
    if block is None:
        raise ValueError(f"resposta INE sem 'Dados' para {varcd}: {str(payload)[:200]}")

    rows = []
    for raw_period, records in (block["Dados"] or {}).items():
        try:
            p = parse_period(raw_period)
        except ValueError:
            continue
        for r in records:
            row = {
                "varcd": varcd,
                "period": p.label,
                "period_kind": p.kind,
                "sort_key": p.sort_key,
                "geocod": str(r.get("geocod", "")).strip(),
                "geoname": r.get("geodsg"),
                "value": _to_float(r.get("valor")),
            }
            for k, v in r.items():
                if re.fullmatch(r"dim_\d+(_t)?", k):
                    row[k] = v
            rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["level"] = df["geocod"].map(classify_level)
    df["dico"] = df["geocod"].map(dico_from_geocod)
    return df


def apply_dim_filters(df: pd.DataFrame, filters: dict[str, str] | None, varcd: str) -> pd.DataFrame:
    """Aplica filtros por código de dimensão e garante 1 valor por (local, período)."""
    if df.empty:
        return df
    for col, code in (filters or {}).items():
        if col not in df.columns:
            raise KeyError(f"{varcd}: dimensão {col!r} inexistente (existentes: {[c for c in df.columns if c.startswith('dim_')]})")
        df = df[df[col].astype(str) == str(code)]
    dup = df.duplicated(["geocod", "period"], keep=False)
    if dup.any():
        dim_cols = [c for c in df.columns if re.fullmatch(r"dim_\d+", c)]
        options = {}
        for c in dim_cols:
            t = c + "_t"
            if t in df.columns:
                pairs = df[[c, t]].drop_duplicates().head(12)
                options[c] = {str(a): str(b) for a, b in pairs.itertuples(index=False)}
            else:
                options[c] = sorted(df[c].dropna().astype(str).unique().tolist())[:12]
        raise AmbiguousDimensionError(
            f"{varcd}: {int(dup.sum())} linhas repetidas por (local, período). "
            f"Define 'dims' em config/sources.yml. Opções por dimensão: {options}"
        )
    return df.reset_index(drop=True)


def fetch(base_url: str, varcd: str, lang: str = "PT", dims: dict[str, str] | None = None,
          session: requests.Session | None = None, retries: int = 3, timeout: int = 60) -> Any:
    s = session or requests.Session()
    params = {"op": 2, "varcd": varcd, "lang": lang}
    # Dim1 = período; "T" = todos. Restantes dimensões só se pedidas explicitamente na API.
    params["Dim1"] = "T"
    for k, v in (dims or {}).items():
        if k.startswith("api_"):
            params[k[4:]] = v
    last: Exception | None = None
    for i in range(retries):
        try:
            r = s.get(base_url, params=params, timeout=timeout,
                      headers={"User-Agent": "imobiliario-pt/0.1 (dados abertos INE)"})
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"falha a obter {varcd} do INE: {last}")


def fetch_meta(varcd: str, lang: str = "PT") -> Any:
    url = "https://www.ine.pt/ine/json_indicador/pindicaMeta.jsp"
    r = requests.get(url, params={"varcd": varcd, "lang": lang}, timeout=60)
    r.raise_for_status()
    return r.json()


def dim_labels(df: pd.DataFrame, filters: dict[str, str] | None) -> str:
    """Descrição legível das dimensões escolhidas (código 'nome'), para o log/meta.json."""
    out = []
    for col, code in (filters or {}).items():
        t = col + "_t"
        lab = None
        if t in df.columns:
            m = df.loc[df[col].astype(str) == str(code), t].dropna()
            lab = m.iloc[0] if len(m) else None
        out.append(f"{col}={code}" + (f" '{lab}'" if lab else ""))
    return ", ".join(out)
