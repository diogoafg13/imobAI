"""Dados SINTÉTICOS para testar o pipeline e o site offline. Nunca usar como dados reais."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .ine import Period, parse_period

GRID_W, GRID_H = 8, 6


def _quarters(start: str, end: str) -> list[Period]:
    out, y, q = [], int(start[:4]), int(start[-1])
    ey, eq = int(end[:4]), int(end[-1])
    while (y, q) <= (ey, eq):
        out.append(parse_period(f"{y}Q{q}"))
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


DEMO_REGIONS = ["11", "11", "19", "19", "1A", "15"]   # NUTS II por linha da grelha (ver outlook.NUTS2)


def _row(d, name, geocod, period, kind, sort_key, value, level="municipality"):
    return dict(varcd="DEMO", period=period, period_kind=kind, sort_key=sort_key, geocod=geocod, geoname=name,
                value=value, level=level, dico=d)


def demo_frames(seed: int = 7):
    rng = np.random.default_rng(seed)
    dicos = [f"{i + 1:04d}" for i in range(GRID_W * GRID_H)]
    names = {d: f"Concelho Demo {d}" for d in dicos}
    qs = _quarters("2019Q4", "2026Q2")
    months = pd.period_range("2011-01", "2026-08", freq="M")
    # ciclo nacional (log, por mês): crise até 2013, retoma, boom, abrandamento com juros, nova subida
    rate = np.select([months.year < 2013, months.year < 2016, months.year < 2022, months.year < 2024],
                     [-0.05, 0.03, 0.08, 0.04], 0.12) / 12
    cycle = np.cumsum(rate)

    rows = {k: [] for k in ("sales", "rent", "val", "income", "density", "ageing", "migration")}
    for i, d in enumerate(dicos):
        geocod = f"{DEMO_REGIONS[i // GRID_W]}X{d}"
        base = rng.uniform(600, 3800)
        drift = rng.uniform(0.005, 0.03)
        v = base
        for p in qs:
            v *= 1 + drift + rng.normal(0, 0.008)
            rows["sales"].append(_row(d, names[d], geocod, p.label, "quarter", p.sort_key, v))
        rent = base * rng.uniform(0.0035, 0.0065)
        for y in range(2020, 2027):
            rent *= 1 + rng.uniform(0.02, 0.12)
            rows["rent"].append(_row(d, names[d], geocod, str(y), "year", y * 100, rent))
        beta = rng.uniform(0.6, 1.4)
        val = base * 0.55 * np.exp(beta * cycle + rng.normal(0, 0.03, len(months)))
        for m, x in zip(months, val):
            rows["val"].append(_row(d, names[d], geocod, str(m), "month", m.year * 100 + m.month, x))
        inc = 700 + base * rng.uniform(0.18, 0.25)
        dens = float(np.exp(rng.uniform(2.5, 7.5)))
        for y in range(2021, 2025):
            rows["income"].append(_row(d, names[d], geocod, str(y), "year", y * 100, inc * 1.04 ** (y - 2021)))
        for y in range(2021, 2026):
            rows["density"].append(_row(d, names[d], geocod, str(y), "year", y * 100, dens))
            rows["ageing"].append(_row(d, names[d], geocod, str(y), "year", y * 100, rng.uniform(90, 350)))
            rows["migration"].append(_row(d, names[d], geocod, str(y), "year", y * 100, rng.normal(50, 150)))
    nat = np.exp(cycle) * 1100
    rows["val"] += [_row("PT", "Portugal", "PT", str(m), "month", m.year * 100 + m.month, x, "national")
                    for m, x in zip(months, nat)]
    frames = {"sales_price_12m": pd.DataFrame(rows["sales"]), "rent_new_contracts": pd.DataFrame(rows["rent"]),
              "bank_valuation": pd.DataFrame(rows["val"]), "income": pd.DataFrame(rows["income"]),
              "population_density": pd.DataFrame(rows["density"]), "ageing_index": pd.DataFrame(rows["ageing"]),
              "migration_balance": pd.DataFrame(rows["migration"])}

    hq = _quarters("2009Q1", "2026Q2")
    h, hv = 90.0, []
    for i, p in enumerate(hq):
        h *= 1 + (0.0 if i < 20 else 0.02) + rng.normal(0, 0.006)
        hv.append((p.label, h))
    months = pd.period_range("2015-01", "2026-08", freq="M").astype(str)
    n = len(months)
    shape = np.concatenate([np.linspace(0, -0.5, 84), np.linspace(-0.5, 4.0, 18), np.linspace(4.0, 2.4, n - 102)])
    e = np.clip(shape + rng.normal(0, 0.05, n), -0.7, None)
    macro_frames = {
        "eurostat_hpi": pd.DataFrame(hv, columns=["period", "value"]),
        "euribor_3m": pd.DataFrame({"period": months, "value": np.clip(e - 0.35, -0.7, None)}),
        "euribor_6m": pd.DataFrame({"period": months, "value": np.clip(e - 0.15, -0.7, None)}),
        "euribor_12m": pd.DataFrame({"period": months, "value": e}),
        "eurostat_hicp": pd.DataFrame({"period": [p.label for p in hq],
                                       "value": [100 * 1.005 ** (i - 24) for i in range(len(hq))]}),
        "bis_credit_gap": pd.DataFrame({"period": [p.label for p in hq], "value": rng.normal(-5, 6, len(hq))}),
    }
    return frames, macro_frames


def demo_geojson() -> dict:
    feats = []
    for i in range(GRID_W * GRID_H):
        r, c = divmod(i, GRID_W)
        x0, y0 = -9.0 + c * 0.5, 41.5 - r * 0.4
        ring = [[x0, y0], [x0 + 0.5, y0], [x0 + 0.5, y0 - 0.4], [x0, y0 - 0.4], [x0, y0]]
        feats.append({"type": "Feature", "properties": {"dico": f"{i + 1:04d}"},
                      "geometry": {"type": "Polygon", "coordinates": [ring]}})
    return {"type": "FeatureCollection", "features": feats}
