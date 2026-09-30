import json
import math

import numpy as np
import pandas as pd
import pytest

from imopt import demo, geo, outlook


def _sales_groups(seed=0):
    """3 grupos bem separados: nível e ritmo antes/depois de 2022T2."""
    rng = np.random.default_rng(seed)
    groups = {"A": (3000, 0.10, 0.10), "B": (700, 0.00, 0.15), "C": (1200, 0.20, 0.03)}
    rows, truth = [], {}
    i = 0
    for gname, (lvl, ga, gb) in groups.items():
        for _ in range(20):
            i += 1
            d = f"{i:04d}"
            truth[d] = gname
            v = lvl * rng.uniform(0.9, 1.1)
            y, q = 2019, 4
            while (y, q) <= (2026, 1):
                rows.append(dict(dico=d, sort_key=y * 100 + q, period=f"{y}Q{q}", value=v, level="municipality", geoname=d))
                g = ga if (y, q) < (2022, 2) else gb
                v *= (1 + g) ** 0.25 * (1 + rng.normal(0, 0.003))
                q += 1
                if q == 5:
                    y, q = y + 1, 1
    return pd.DataFrame(rows), truth


def test_regimes_finds_known_breakpoints():
    rng = np.random.default_rng(0)
    slopes = [-0.02] * 16 + [0.01] * 16 + [0.035] * 16
    y = np.cumsum(slopes) + rng.normal(0, 0.002, 48)
    per = [f"{2008 + i // 4}Q{i % 4 + 1}" for i in range(48)]
    r = outlook.regimes(pd.DataFrame({"period": per, "value": 100 * np.exp(y)}))
    assert r["n_segments"] == 3
    starts = [per.index(s["start"]) for s in r["segments"]]
    assert abs(starts[1] - 16) <= 1 and abs(starts[2] - 32) <= 1
    assert r["segments"][2]["growth_ann"] == pytest.approx(math.exp(4 * 0.035) - 1, abs=0.01)


def test_typologies_recover_known_groups():
    sales, truth = _sales_groups()
    summary, per = outlook.typologies(sales)
    assert summary["k"] == 3
    for g in "ABC":
        labels = {per[d]["typology"] for d, t in truth.items() if t == g}
        assert len(labels) == 1, g                  # cada grupo verdadeiro cai num só cluster
    names = {per[d]["typology_name"] for d in per}
    assert any("arranque tardio" in n for n in names) and any("abrandar" in n for n in names)


def test_fair_value_recovers_elasticity_and_flags_outlier():
    rng = np.random.default_rng(4)
    n = 150
    inc = rng.uniform(800, 1800, n)
    dens = np.exp(rng.uniform(2, 8, n))
    age = rng.uniform(80, 400, n)
    coast = rng.random(n) < 0.3
    price = np.exp(0.8 * np.log(inc) + 0.1 * np.log(dens) - 0.3 * np.log(age) + 0.3 * coast + rng.normal(0, 0.05, n))
    price[0] *= 2
    dicos = [f"{i + 1:04d}" for i in range(n)]
    feats = pd.DataFrame({"dico": dicos, "name": dicos, "price": price, "income": inc, "density": dens,
                          "ageing_index": age, "migration_balance": rng.normal(0, 50, n)})
    spatial = pd.DataFrame({"dico": dicos, "area_km2": 300.0, "coastal": coast})
    summary, per = outlook.fair_value(feats, spatial, None, {})
    eff = {e["feature"]: e for e in summary["effects"]}
    assert eff["log_income"]["effect_10pct"] == pytest.approx(1.1 ** 0.8 - 1, abs=0.01)
    assert eff["coastal"]["effect_unit"] == pytest.approx(math.exp(0.3) - 1, abs=0.05)
    assert summary["r2_cv"] > 0.8
    assert summary["top_above"][0]["dico"] == "0001" and per["0001"]["fv_gap"] > 0.7


def test_rate_scenarios_annuity_math_and_no_fake_effect():
    months = [f"{y}-{m:02d}" for y in range(2020, 2027) for m in range(1, 13)]
    r = outlook.rate_scenarios(pd.DataFrame({"period": months, "value": 2.0}), None)

    def cap(rate):
        i, n = rate / 12, 360
        return (1 - (1 + i) ** -n) / i
    up = next(s for s in r["shocks"] if s["shock"] == 1.0)
    assert up["capacity_change"] == pytest.approx(cap(0.04) / cap(0.03) - 1)
    assert up["payment_change"] > 0 and not r["credible"] and "price_effect_12m" not in up


def test_spatial_index_neighbours_area_and_coast():
    sp, nb = geo.spatial_index(demo.demo_geojson())
    assert set(nb["0001"]) == {"0002", "0009", "0010"}
    assert set(sp.loc[sp["coastal"], "dico"]) == {f"{1 + 8 * r:04d}" for r in range(6)}   # só a coluna oeste
    assert sp["area_km2"].between(1500, 2200).all()


def test_build_outputs_writes_outlook_without_nan(tmp_path):
    from imopt import pipeline
    frames, macro_frames = demo.demo_frames()
    pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path, demo.demo_geojson(), demo=True)

    def no_nan(x):
        raise ValueError(f"valor não-JSON: {x}")
    ol = json.loads((tmp_path / "outlook.json").read_text(encoding="utf-8"), parse_constant=no_nan)
    assert not ol["errors"]
    assert {"sales", "rent", "regimes", "typologies", "fair_value", "rates"} <= set(ol)
    munis = json.loads((tmp_path / "municipalities.json").read_text(encoding="utf-8"), parse_constant=no_nan)
    assert all(m.get("fc_growth_12m") is not None for m in munis)
    geoj = json.loads((tmp_path / "concelhos.geojson").read_text(encoding="utf-8"))
    assert "fc" in geoj["features"][0]["properties"] and "fv" in geoj["features"][0]["properties"]


def test_outlook_degrades_without_valuation_or_geometry(tmp_path):
    from imopt import pipeline
    frames, macro_frames = demo.demo_frames()
    frames.pop("bank_valuation")
    pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path, None, demo=True)
    ol = json.loads((tmp_path / "outlook.json").read_text(encoding="utf-8"))
    assert "sales" in ol and not ol["errors"]
    assert "v_lead" not in ol["sales"]["features"]
    feats = {e["feature"] for e in ol["fair_value"]["effects"]}   # sem geometrias: sem área, litoral nem distância
    assert "log_income" in feats and not {"coastal", "mig_rate", "log_dist"} & feats
