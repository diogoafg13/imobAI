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
    # categorias e indicadores de contexto (sintéticos, derivados dos de cima)
    sales, rent = frames["sales_price_12m"], frames["rent_new_contracts"]
    muni_val = frames["bank_valuation"][frames["bank_valuation"]["level"] == "municipality"]
    has_new = sales["dico"].astype(int) % 2 == 0
    frames["sales_price_new"] = sales[has_new].assign(value=lambda d: d["value"] * 1.25)
    frames["sales_price_existing"] = sales.assign(value=lambda d: d["value"] * 0.95)
    frames["valuation_apartments"] = muni_val.assign(value=lambda d: d["value"] * 1.05)
    frames["valuation_houses"] = muni_val[muni_val["dico"].astype(int) % 3 != 0].assign(value=lambda d: d["value"] * 0.9)
    frames["rent_q1"] = rent.assign(value=lambda d: d["value"] * 0.75)
    frames["rent_q3"] = rent.assign(value=lambda d: d["value"] * 1.3)
    frames["sales_price_domestic"] = sales.assign(value=lambda d: d["value"] * 0.97)
    frames["sales_price_foreign"] = sales[sales["dico"].astype(int) % 4 == 0].assign(value=lambda d: d["value"] * 1.4)
    # freguesias: 4 por concelho (só 3 com dados, como no INE), código DICOFRE = dico + 01..04
    par = []
    for r in sales.itertuples():
        for k, f in ((1, 1.3), (2, 0.85), (3, 1.0)):
            par.append(_row(r.dico, f"Freguesia {r.dico}-{k}", f"{r.geocod[:3]}{r.dico}{k:02d}", r.period, "quarter",
                            r.sort_key, r.value * f * (1 + 0.02 * np.sin(int(r.dico) * k)), "parish"))
    frames["sales_price_12m"] = pd.concat([sales, pd.DataFrame(par)], ignore_index=True)
    frames["sales_price_households"] = sales.assign(value=lambda d: d["value"] * 0.98)
    frames["sales_price_companies"] = sales[sales["dico"].astype(int) % 3 == 0].assign(value=lambda d: d["value"] * 1.2)
    frames["sales_price_apartments"] = sales.assign(value=lambda d: d["value"] * 1.08)
    for k, f in (("t01", 1.25), ("t2", 1.05), ("t3", 0.95), ("t4", 0.85)):
        frames[f"sales_price_{k}"] = sales.assign(value=lambda d, f=f: d["value"] * f)
    frames["valuation_count"] = muni_val.assign(value=lambda d: (40 + 30 * np.sin(d["sort_key"] / 7.0)).round())
    frames["valuation_count_apartments"] = frames["valuation_count"].assign(value=lambda d: (d["value"] * 0.6).round())
    frames["valuation_count_houses"] = frames["valuation_count"].assign(value=lambda d: (d["value"] * 0.4).round())
    yearly = frames["population_density"]
    frames["rent_contracts"] = yearly.assign(value=lambda d: (d["value"] * rng.uniform(0.5, 2, len(d))).round())
    frames["tourism_nights"] = yearly.assign(value=lambda d: d["value"] * rng.uniform(200, 4000, len(d)))
    frames["housing_credit_pc"] = yearly.assign(value=lambda d: rng.uniform(3000, 15000, len(d)))
    # parque, Censos 2021, camas turísticas e IRS (concelho); licenças e conclusões só nacionais (como no INE)
    ydf = pd.DataFrame([_row(r.dico, names[r.dico], r.geocod, str(y), "year", y * 100, 1.0)
                        for r in yearly.drop_duplicates("dico").itertuples() for y in range(2016, 2026)])
    stock = {d: rng.uniform(3000, 60000) for d in dicos}
    frames["dwellings_stock"] = ydf[ydf["period"].astype(int) <= 2022].assign(
        value=lambda d: [stock[x] * (1 + 0.004 * (int(p) - 2016)) for x, p in zip(d["dico"], d["period"])])
    frames["tourism_beds"] = ydf[ydf["period"].astype(int) >= 2023].assign(value=lambda d: [round(stock[x] * rng.uniform(0.01, 0.2)) for x in d["dico"]])
    frames["tourism_beds_al"] = frames["tourism_beds"].assign(value=lambda d: (d["value"] * 0.3).round())
    gm = pd.period_range("2022-01", "2026-07", freq="M")
    base_g = {d: rng.uniform(500, 50000) for d in dicos}
    ref = yearly.drop_duplicates("dico").set_index("dico")
    frames["tourism_guests"] = pd.DataFrame([_row(d, names[d], ref.at[d, "geocod"], str(m), "month", m.year * 100 + m.month,
                                                  round(base_g[d] * (1 + 0.04 * (m.year - 2022)) * (1.5 if m.month in (7, 8) else 1)))
                                             for d in dicos for m in gm])
    frames["tourism_guests_al"] = frames["tourism_guests"].assign(value=lambda d: (d["value"] * 0.3).round())
    frames["tourism_occupancy"] = ydf[ydf["period"].astype(int) >= 2022].assign(value=lambda d: rng.uniform(30, 70, len(d)).round(1))
    shares = {d: (rng.uniform(0.05, 0.25), rng.uniform(0.04, 0.12), rng.uniform(0.02, 0.06)) for d in dicos}
    for key, j in (("census_total", None), ("census_secondary", 0), ("census_vacant_market", 2), ("census_vacant_other", 1)):
        # Censos: o INE usa geocod de 4 dígitos (o DICO) e o parser não lhe atribui concelho
        frames[key] = pd.DataFrame([dict(_row(None, names[d], d, "2021", "year", 202100,
                                             stock[d] * (1 if j is None else shares[d][j])), level="other") for d in dicos])
    months_n = pd.period_range("2007-01", "2026-07", freq="M")
    frames["dwellings_licensed"] = pd.DataFrame([_row("PT", "Portugal", "PT", str(m), "month", m.year * 100 + m.month,
                                                      round(3000 * (0.4 + 0.6 * abs(np.sin(i / 60)))), "national")
                                                 for i, m in enumerate(months_n)])
    qn = _quarters("2004Q1", "2026Q2")
    frames["dwellings_completed"] = pd.DataFrame([_row("PT", "Portugal", "PT", q.label, "quarter", q.sort_key,
                                                       round(7000 * (0.4 + 0.6 * abs(np.cos(i / 20)))), "national")
                                                  for i, q in enumerate(qn)])
    stock_nat = frames["dwellings_stock"].groupby(["period", "sort_key"])["value"].sum().reset_index()
    frames["dwellings_stock"] = pd.concat([frames["dwellings_stock"], pd.DataFrame(
        [_row("PT", "Portugal", "PT", r.period, "year", r.sort_key, r.value, "national") for r in stock_nat.itertuples()])],
        ignore_index=True)
    inc_m = frames["income"].groupby("dico")["value"].first()
    frames["irs_median"] = ydf[ydf["period"].astype(int) >= 2016].assign(
        value=lambda d: [inc_m[x] * 10.5 * 1.03 ** (int(p) - 2016) for x, p in zip(d["dico"], d["period"])])
    nat_rows = []
    for key in ("irs_median",):
        g = frames[key].groupby(["period", "sort_key"])["value"].median().reset_index()
        nat_rows = [_row("PT", "Portugal", "PT", r.period, "year", r.sort_key, r.value, "national") for r in g.itertuples()]
        frames[key] = pd.concat([frames[key], pd.DataFrame(nat_rows)], ignore_index=True)
    g = frames["income"].groupby(["period", "sort_key"])["value"].median().reset_index()
    frames["income"] = pd.concat([frames["income"], pd.DataFrame(
        [_row("PT", "Portugal", "PT", r.period, "year", r.sort_key, r.value, "national") for r in g.itertuples()])], ignore_index=True)

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
        "mortgage_rate_pt": pd.DataFrame({"period": months, "value": e + 1.1}),
        "eurostat_hicp": pd.DataFrame({"period": [p.label for p in hq],
                                       "value": [100 * 1.005 ** (i - 24) for i in range(len(hq))]}),
        "bis_credit_gap": pd.DataFrame({"period": [p.label for p in hq], "value": rng.normal(-5, 6, len(hq))}),
    }
    # UE (sintético): HPI e IHPC trimestrais de 12 países, PT a subir mais depressa
    eu_h, eu_c = [], []
    for j, g in enumerate(("PT", "ES", "FR", "DE", "IT", "NL", "IE", "AT", "BE", "PL", "LT", "EE")):
        speed = 0.03 if g == "PT" else rng.uniform(0.0, 0.02)
        for i, q in enumerate(hq):
            eu_h.append((g, q.label, 100 * np.exp(speed * (i - 24) / 4 + rng.normal(0, 0.005))))
            eu_c.append((g, q.label, 100 * 1.005 ** (i - 24)))
    macro_frames["eurostat_hpi_eu"] = pd.DataFrame(eu_h, columns=["geo", "period", "value"])
    macro_frames["eurostat_hicp_eu"] = pd.DataFrame(eu_c, columns=["geo", "period", "value"])
    return frames, macro_frames


def demo_parish_geojson() -> dict:
    """Cada quadrado de concelho dividido em 4 freguesias (código DICOFRE = dico + 01..04)."""
    feats = []
    for i in range(GRID_W * GRID_H):
        r, c = divmod(i, GRID_W)
        x0, y0 = -9.0 + c * 0.5, 41.5 - r * 0.4
        for k, (dx, dy) in enumerate(((0, 0), (0.25, 0), (0, -0.2), (0.25, -0.2)), start=1):
            a, b = x0 + dx, y0 + dy
            ring = [[a, b], [a + 0.25, b], [a + 0.25, b - 0.2], [a, b - 0.2], [a, b]]
            feats.append({"type": "Feature", "properties": {"fre_code": f"{i + 1:04d}{k:02d}"},
                          "geometry": {"type": "Polygon", "coordinates": [ring]}})
    return {"type": "FeatureCollection", "features": feats}


def demo_geojson() -> dict:
    feats = []
    for i in range(GRID_W * GRID_H):
        r, c = divmod(i, GRID_W)
        x0, y0 = -9.0 + c * 0.5, 41.5 - r * 0.4
        ring = [[x0, y0], [x0 + 0.5, y0], [x0 + 0.5, y0 - 0.4], [x0, y0 - 0.4], [x0, y0]]
        feats.append({"type": "Feature", "properties": {"dico": f"{i + 1:04d}"},
                      "geometry": {"type": "Polygon", "coordinates": [ring]}})
    return {"type": "FeatureCollection", "features": feats}
