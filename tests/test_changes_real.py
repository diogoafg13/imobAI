import json

import numpy as np
import pandas as pd
import pytest

from imopt import changes, demo, pipeline, scoring


def _sales(dico, values, start=(2024, 1)):
    y, q = start
    rows = []
    for v in values:
        rows.append(dict(dico=dico, geoname=f"C{dico}", period=f"{y}Q{q}", sort_key=y * 100 + q, value=v, level="municipality"))
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return rows


def test_real_growth_deflates_with_last_published_hicp():
    hicp = pd.DataFrame({"period": ["2025Q1", "2025Q4"], "value": [100.0, 103.0]})
    feats = pd.DataFrame({"dico": ["0001"], "latest_key": [202601], "price_growth_1y": [0.10],
                          "price_growth_3y": [np.nan], "price_growth_5y": [0.2]})
    f = scoring.real_growth(feats, hicp)
    # 2026Q1 ainda sem IHPC: usa 2025Q4 (103); um ano antes, 2025Q1 (100)
    assert f.at[0, "price_growth_1y_real"] == pytest.approx(1.10 / 1.03 - 1)
    assert f.at[0, "hicp_period"] == "2025Q4" and pd.isna(f.at[0, "price_growth_3y_real"])
    assert "price_growth_1y_real" not in scoring.real_growth(feats, None)


def test_quarter_changes_band_moves_and_movers():
    rows = []
    for i in range(12):
        base = [1000 + 50 * i] * 8
        if i == 0:
            base[-1] = base[-2] * 1.5          # salto forte no último trimestre
        rows += _sales(f"{i + 1:04d}", base)
    sales = pd.DataFrame(rows)
    feats = scoring.municipal_features(sales, None).assign(volatile=False)   # séries constantes: volatilidade degenerada
    summary, per = changes.quarter_changes(sales, None, feats)
    assert summary["period"] == "2025Q4" and summary["prev_period"] == "2025Q3"
    assert summary["price_up"][0]["dico"] == "0001" and summary["price_up"][0]["value"] == pytest.approx(0.5)
    assert per["0001"]["price_qoq"] == pytest.approx(0.5)
    assert any(c["dico"] == "0001" for c in summary["band_changes"]) or per["0001"]["band_prev"] == feats.set_index("dico").at["0001", "band"]
    vol = feats.assign(val_count=[5.0] + [50.0] * 11)        # o concelho do salto tem pouco mercado
    s2, _ = changes.quarter_changes(sales, None, vol)
    assert all(x["dico"] != "0001" for x in s2["price_up"]) and s2["min_volume"] == changes.MIN_VOLUME


def test_quarter_changes_needs_previous_quarter():
    sales = pd.DataFrame(_sales("0001", [1000.0]))
    assert changes.quarter_changes(sales, None, scoring.municipal_features(sales, None)) == (None, {})


def test_build_outputs_real_prices_changes_and_volume_in_type_forecasts(tmp_path):
    frames, macro_frames = demo.demo_frames()
    pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path, None, demo=True)
    ol = json.loads((tmp_path / "outlook.json").read_text(encoding="utf-8"))
    assert ol["changes"]["period"] == "2026Q2" and ol["changes"]["prev_period"] == "2026Q1"
    assert "vol_chg" in ol["fc_apt"]["features"] and "vol_chg" not in ol["sales"]["features"]
    m = json.loads((tmp_path / "municipalities.json").read_text(encoding="utf-8"))[0]
    assert m["price_growth_1y_real"] is not None and m["hicp_period"] and m["price_qoq"] is not None
    ser = json.loads((tmp_path / "series.json").read_text(encoding="utf-8"))[m["dico"]]["series"]
    assert len(ser["price_real"]) == len(ser["price"]) and "series" not in m and "rent_first" in m
