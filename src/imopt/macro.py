"""Séries macro: Euribor 3/6/12M (BCE), HPI e IHPC (Eurostat), desvio crédito/PIB (BIS).

Cada função devolve um DataFrame [period, value] ordenado, ou levanta erro; o
pipeline decide se a falha é fatal (nunca é, para macro: degrada com aviso).
"""
from __future__ import annotations

import io
import logging
from typing import Any

import pandas as pd
import requests

UA = {"User-Agent": "imobiliario-pt/0.1 (dados abertos)"}
log = logging.getLogger("imopt")


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


def extend_with_annual_rates(idx: pd.DataFrame, rates: pd.DataFrame | None) -> pd.DataFrame:
    """Índice mensal ('2025-12') prolongado com as taxas de variação homóloga (%) publicadas depois do seu fim:
    I(t) = I(t-12) × (1 + taxa(t)/100). O Eurostat deixou de publicar o IHPC com base 2015 = 100 no fim de 2025
    (mudou de base); a taxa homóloga não depende da base, por isso prolonga a série sem a quebrar. As taxas vêm
    com uma casa decimal: o erro acumulado é de poucas centésimas de ponto por ano."""
    if rates is None or rates.empty or idx.empty:
        return idx
    s = dict(zip(pd.PeriodIndex(idx["period"], freq="M"), idx["value"].astype(float)))
    r = dict(zip(pd.PeriodIndex(rates["period"], freq="M"), rates["value"].astype(float)))
    last = max(s)
    for p in sorted(k for k in r if k > last):
        if p - 12 not in s:
            break
        s[p] = s[p - 12] * (1 + r[p] / 100)
    out = pd.DataFrame({"period": [str(p) for p in sorted(s)], "value": [s[p] for p in sorted(s)]})
    if len(out) > len(idx):
        log.info("IHPC prolongado com a taxa homóloga: %s -> %s", idx["period"].max(), out["period"].iloc[-1])
    return out


def chain_indices(series: list[pd.DataFrame]) -> pd.DataFrame:
    """Junta índices mensais com bases diferentes (ex.: 2015 = 100 até dez/2025 e 2025 = 100 depois): o primeiro
    define o nível; cada seguinte só acrescenta os meses depois do fim, reescalado pela média dos meses em comum."""
    out = {}
    for df in series:
        cur = dict(zip(df["period"].astype(str), df["value"].astype(float)))
        if not out:
            out = cur
            continue
        common = [m for m in cur if m in out and cur[m]]
        if not common:
            continue
        k = sum(out[m] / cur[m] for m in common) / len(common)
        last = max(out)
        out.update({m: v * k for m, v in cur.items() if m > last})
    return pd.DataFrame({"period": sorted(out), "value": [out[m] for m in sorted(out)]})


def _units(cfg: dict, panel: bool = False) -> list[pd.DataFrame]:
    """Pede o índice em cada base configurada (`units`, por ordem); devolve as que responderem."""
    params = cfg.get("params", {})
    units = cfg.get("units") or [params.get("unit")]
    got, errors = [], []
    for u in units:
        try:
            js = _get(cfg["url"], {**params, "unit": u}).json()
            got.append(parse_jsonstat_panel(js) if panel else parse_jsonstat_time_series(js))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{u}: {str(e)[:120]}")
    if errors:
        log.warning("IHPC: bases sem resposta: %s", "; ".join(errors))
    if not got:
        raise RuntimeError("IHPC indisponível em todas as bases: " + "; ".join(errors))
    return got


def _rates(cfg: dict, panel: bool = False) -> pd.DataFrame | None:
    """Taxas de variação homóloga do IHPC (prc_hicp_manr), se configuradas; falha sem parar o resto."""
    rc = cfg.get("rates")
    if not rc:
        return None
    try:
        js = _get(rc["url"], rc.get("params", {})).json()
        return parse_jsonstat_panel(js) if panel else parse_jsonstat_time_series(js)
    except Exception as e:  # noqa: BLE001
        log.warning("taxa homóloga do IHPC indisponível (a série fica até à última base publicada): %s", e)
        return None


def fetch_eurostat_hicp(cfg: dict) -> pd.DataFrame:
    """IHPC de Portugal (2015=100), mensal no Eurostat, prolongado com a taxa homóloga depois do fim da base 2015,
    devolvido em médias trimestrais."""
    monthly = chain_indices(_units(cfg))
    return monthly_to_quarterly(extend_with_annual_rates(monthly, _rates(cfg)))


def fetch_bis_credit_gap(cfg: dict) -> pd.DataFrame:
    r = _get(cfg["url"], cfg.get("params", {}))
    df = pd.read_csv(io.StringIO(r.text))
    out = df.rename(columns={"TIME_PERIOD": "period", "OBS_VALUE": "value"})[["period", "value"]]
    out["period"] = out["period"].str.replace("-Q", "Q", regex=False)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out.dropna().sort_values("period").reset_index(drop=True)


def parse_jsonstat_panel(js: dict, panel_dim: str = "geo") -> pd.DataFrame:
    """JSON-stat 2.0 com duas dimensões não triviais (ex.: país e tempo) -> colunas geo, period, value."""
    ids, sizes = js["id"], js["size"]
    if any(s != 1 for d, s in zip(ids, sizes) if d not in (panel_dim, "time")):
        raise ValueError(f"JSON-stat com dimensões não filtradas: {dict(zip(ids, sizes))}")

    def labels(dim):
        cat = js["dimension"][dim]["category"]["index"]
        return sorted(cat, key=lambda k: cat[k]) if isinstance(cat, dict) else list(cat)

    strides = [1] * len(ids)
    for i in range(len(ids) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    gi, ti = ids.index(panel_dim), ids.index("time")
    values = js["value"]
    get = (lambda i: values.get(str(i))) if isinstance(values, dict) else (lambda i: values[i] if i < len(values) else None)
    rows = []
    for a, g in enumerate(labels(panel_dim)):
        for b, t in enumerate(labels("time")):
            v = get(a * strides[gi] + b * strides[ti])
            if v is not None:
                rows.append((g, t.replace("-Q", "Q"), float(v)))
    return pd.DataFrame(rows, columns=[panel_dim, "period", "value"])


def fetch_eurostat_panel(cfg: dict) -> pd.DataFrame:
    """Vários países num só pedido (parâmetro geo repetido). Séries mensais passam a médias trimestrais."""
    parts = _units(cfg, panel=True) if cfg.get("units") else [parse_jsonstat_panel(_get(cfg["url"], cfg.get("params", {})).json())]
    if len(parts) > 1:
        df = pd.concat([chain_indices([p[p["geo"] == geo][["period", "value"]] for p in parts]).assign(geo=geo)
                        for geo in sorted(set().union(*[set(p["geo"]) for p in parts]))], ignore_index=True)
    else:
        df = parts[0]
    if df["period"].str.contains("-").any():          # mensal ('2024-01')
        rates = _rates(cfg, panel=True)
        rg = dict(tuple(rates.groupby("geo"))) if rates is not None else {}
        df = pd.concat([monthly_to_quarterly(extend_with_annual_rates(g[["period", "value"]],
                                                                       rg[geo][["period", "value"]] if geo in rg else None)).assign(geo=geo)
                        for geo, g in df.groupby("geo")], ignore_index=True)
    return df.sort_values(["geo", "period"]).reset_index(drop=True)


FETCHERS = {
    "euribor_3m": fetch_euribor,
    "euribor_6m": fetch_euribor,
    "euribor_12m": fetch_euribor,
    "mortgage_rate_pt": fetch_euribor,     # mesmo formato CSV da API de dados do BCE
    "mortgage_volume_pt": fetch_euribor,
    "mortgage_volume_pure_pt": fetch_euribor,
    "eurostat_hpi": fetch_eurostat_hpi,
    "eurostat_hicp": fetch_eurostat_hicp,
    "bis_credit_gap": fetch_bis_credit_gap,
    "eurostat_hpi_eu": fetch_eurostat_panel,
    "eurostat_hicp_eu": fetch_eurostat_panel,
}
