"""Séries macro: Euribor 3/6/12M (BCE), HPI e IHPC (Eurostat), desvio crédito/PIB (BIS).

Cada função devolve um DataFrame [period, value] ordenado, ou levanta erro; o
pipeline decide se a falha é fatal (nunca é, para macro: degrada com aviso).
"""
from __future__ import annotations

import io
from typing import Any

import pandas as pd
import requests

UA = {"User-Agent": "imobiliario-pt/0.1 (dados abertos)"}


def _get(url: str, params: dict[str, Any], accept: str | None = None) -> requests.Response:
    headers = dict(UA)
    if accept:
        headers["Accept"] = accept
    r = requests.get(url, params=params, headers=headers, timeout=60)
    r.raise_for_status()
    return r


def fetch_euribor(cfg: dict) -> pd.DataFrame:
    r = _get(cfg["url"], cfg.get("params", {}))
    df = pd.read_csv(io.StringIO(r.text))
    out = df.rename(columns={"TIME_PERIOD": "period", "OBS_VALUE": "value"})[["period", "value"]]
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out.dropna().sort_values("period").reset_index(drop=True)


def parse_jsonstat_time_series(js: dict) -> pd.DataFrame:
    """JSON-stat 2.0 com uma única dimensão de tempo não trivial (Eurostat)."""
    ids = js["id"]
    sizes = js["size"]
    time_dim = "time"
    idx = ids.index(time_dim)
    cat = js["dimension"][time_dim]["category"]["index"]
    labels = sorted(cat, key=lambda k: cat[k]) if isinstance(cat, dict) else list(cat)
    # Todas as outras dimensões têm tamanho 1 nos pedidos filtrados.
    if any(s != 1 for i, s in enumerate(sizes) if i != idx):
        raise ValueError(f"JSON-stat com dimensões não filtradas: {dict(zip(ids, sizes))}")
    values = js["value"]
    get = (lambda i: values.get(str(i))) if isinstance(values, dict) else (lambda i: values[i])
    rows = [(labels[i], get(i)) for i in range(len(labels))]
    df = pd.DataFrame(rows, columns=["period", "value"]).dropna()
    df["period"] = df["period"].str.replace("-Q", "Q", regex=False)
    return df.reset_index(drop=True)


def fetch_eurostat_hpi(cfg: dict) -> pd.DataFrame:
    r = _get(cfg["url"], cfg.get("params", {}))
    return parse_jsonstat_time_series(r.json())


def monthly_to_quarterly(df: pd.DataFrame) -> pd.DataFrame:
    """Série mensal ('2024-01') -> média trimestral ('2024Q1'), só trimestres completos (3 meses)."""
    q = pd.PeriodIndex(df["period"], freq="M").asfreq("Q").astype(str)
    g = df.assign(q=q).groupby("q")["value"].agg(["mean", "count"])
    g = g[g["count"] == 3]
    return pd.DataFrame({"period": g.index, "value": g["mean"].values}).reset_index(drop=True)


def fetch_eurostat_hicp(cfg: dict) -> pd.DataFrame:
    """IHPC de Portugal (2015=100), mensal no Eurostat, devolvido em médias trimestrais."""
    r = _get(cfg["url"], cfg.get("params", {}))
    return monthly_to_quarterly(parse_jsonstat_time_series(r.json()))


def fetch_bis_credit_gap(cfg: dict) -> pd.DataFrame:
    r = _get(cfg["url"], cfg.get("params", {}))
    df = pd.read_csv(io.StringIO(r.text))
    out = df.rename(columns={"TIME_PERIOD": "period", "OBS_VALUE": "value"})[["period", "value"]]
    out["period"] = out["period"].str.replace("-Q", "Q", regex=False)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out.dropna().sort_values("period").reset_index(drop=True)


FETCHERS = {
    "euribor_3m": fetch_euribor,
    "euribor_6m": fetch_euribor,
    "euribor_12m": fetch_euribor,
    "eurostat_hpi": fetch_eurostat_hpi,
    "eurostat_hicp": fetch_eurostat_hicp,
    "bis_credit_gap": fetch_bis_credit_gap,
}
