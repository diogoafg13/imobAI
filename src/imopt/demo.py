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


def demo_frames(seed: int = 7):
    rng = np.random.default_rng(seed)
    dicos = [f"{i + 1:04d}" for i in range(GRID_W * GRID_H)]
    names = {d: f"Concelho Demo {d}" for d in dicos}
    qs = _quarters("2019Q4", "2026Q2")

    sales_rows, rent_rows = [], []
    for i, d in enumerate(dicos):
        base = rng.uniform(600, 3800)
        drift = rng.uniform(0.005, 0.03)
        v = base
        for p in qs:
            v *= 1 + drift + rng.normal(0, 0.008)
            sales_rows.append(dict(varcd="DEMO", period=p.label, period_kind="quarter", sort_key=p.sort_key,
                                   geocod=f"170{d}", geoname=names[d], value=v, level="municipality", dico=d))
        rent = base * rng.uniform(0.0035, 0.0065)
        for y in range(2022, 2027):
            rent *= 1 + rng.uniform(0.02, 0.12)
            rent_rows.append(dict(varcd="DEMO", period=str(y), period_kind="year", sort_key=y * 100,
                                  geocod=f"170{d}", geoname=names[d], value=rent, level="municipality", dico=d))
    frames = {"sales_price_12m": pd.DataFrame(sales_rows), "rent_new_contracts": pd.DataFrame(rent_rows)}

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
