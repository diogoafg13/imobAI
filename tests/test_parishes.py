import json

import pandas as pd
import pytest

from imopt import demo, geo, parishes, pipeline


def _row(code, period, value, level="parish", name=None):
    y, q = period.split("Q")
    return dict(geocod="11A" + code, geoname=name or f"F{code}", period=period, sort_key=int(y) * 100 + int(q),
                value=value, level=level, dico=None)


def test_table_relative_to_municipality_and_growth():
    sales = pd.DataFrame([_row("110601", "2025Q1", 4000.0), _row("110601", "2026Q1", 5000.0),
                          _row("110602", "2026Q1", 3000.0, level="other", name="União X"),
                          dict(geocod="1A01106", geoname="Lisboa", period="2026Q1", sort_key=202601, value=4000.0,
                               level="municipality", dico="1106")])
    t = parishes.table(sales, None, {"1106": 4000.0}).set_index("code")
    assert t.attrs["period"] == "2026Q1" and set(t.index) == {"110601", "110602"}
    assert t.at["110601", "rel_muni"] == pytest.approx(0.25) and t.at["110601", "g1y"] == pytest.approx(0.25)
    assert t.at["110602", "name"] == "União X" and t.at["110602", "dico"] == "1106"


def test_neighbours_need_two_with_data():
    gj, n = geo.attach_code(demo.demo_parish_geojson(), ["fre_code"])
    assert n == 4 * 48
    t = pd.DataFrame({"code": ["000101", "000102", "000103", "000104"], "price": [100.0, 200.0, 300.0, 400.0],
                      "dico": "0001", "name": "x", "rel_muni": 0.0, "g1y": 0.0})
    r = parishes.add_neighbours(t, gj).set_index("code")
    # 000101 toca 000102, 000103 e 000104 (diagonal): mediana 300 -> 100/300 - 1
    assert r.at["000101", "rel_nb"] == pytest.approx(100 / 300 - 1) and r.at["000101", "n_nb"] == 3
    one = parishes.add_neighbours(t.iloc[:2], gj)
    assert one["rel_nb"].isna().all()                  # só 1 vizinha com dados: sem comparação


def test_attach_code_handles_lists_and_padding():
    gj = {"features": [{"properties": {"fre_code": ["80807"]}}, {"properties": {"x": 1}}]}
    out, n = geo.attach_code(gj, ["fre_code"])
    assert n == 1 and out["features"][0]["properties"]["code"] == "080807"


def test_parish_geojson_falls_back_to_cache(monkeypatch, tmp_path):
    cache = tmp_path / "clean" / "geo_parishes.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")

    def boom(url):
        raise OSError("sem rede")
    monkeypatch.setattr(geo, "download_geojson", boom)
    status = {}
    gj = pipeline.load_parish_geojson({"geo": {"parishes_geojson": ["http://x"], "parish_props": []}}, tmp_path, status)
    assert gj == {"type": "FeatureCollection", "features": []} and status["geo_parishes"].startswith("CACHE")
    cache.unlink()
    assert pipeline.load_parish_geojson({"geo": {"parishes_geojson": ["http://x"]}}, tmp_path, status) is None
    assert status["geo_parishes"].startswith("ERRO")


def test_build_outputs_writes_parishes(tmp_path):
    frames, macro_frames = demo.demo_frames()
    pgj, _ = geo.attach_code(demo.demo_parish_geojson(), ["fre_code"])
    meta = pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path, demo.demo_geojson(), demo=True, parish_geojson=pgj)
    fr = json.loads((tmp_path / "freguesias.json").read_text(encoding="utf-8"))
    assert fr["with_map"] and len(fr["rows"]) == 144 and meta["parishes"].startswith("144 freguesias")
    gj = json.loads((tmp_path / "freguesias.geojson").read_text(encoding="utf-8"))
    # todas as fronteiras vão para o mapa (sem dados = cinzento); 144 com preço
    assert len(gj["features"]) == 192 and sum(f["properties"].get("price") is not None for f in gj["features"]) == 144
    assert {"price", "rel_nb", "rel_muni", "irs", "vac"} <= set(gj["features"][0]["properties"])
    munis = json.loads((tmp_path / "municipalities.json").read_text(encoding="utf-8"))
    assert len(munis) == 48                              # freguesias não entram no ranking de concelhos
    pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path / "b", None, demo=True)
    fr2 = json.loads((tmp_path / "b" / "freguesias.json").read_text(encoding="utf-8"))
    assert not fr2["with_map"] and len(fr2["rows"]) == 144 and not (tmp_path / "b" / "freguesias.geojson").exists()


def test_table_adds_irs_and_census_parishes_without_price():
    sales = pd.DataFrame([dict(geocod="1A0110601", level="parish", period="2026Q1", sort_key=202601, value=2000.0, geoname="A")])
    irs = pd.DataFrame([dict(geocod=g, level="parish", period=str(y), sort_key=y * 100, value=v, geoname=n)
                        for g, n in (("1A0110601", "A"), ("1A0110602", "B")) for y, v in ((2023, 10000.0), (2024, 11000.0))])
    cen = lambda v: pd.DataFrame([dict(geocod="110602", level="other", period="2021", sort_key=202100, value=v, geoname="B")])  # noqa: E731
    t = parishes.table(sales, None, {"1106": 2500.0}, irs,
                       {"total": cen(1000.0), "secondary": cen(100.0), "vacant_market": cen(50.0), "vacant_other": cen(30.0)})
    t = t.set_index("code")
    assert t.at["110601", "price"] == 2000.0 and t.at["110601", "irs_median"] == 11000.0
    assert pd.isna(t.at["110602", "price"]) and t.at["110602", "irs_growth_1y"] == pytest.approx(0.1)
    assert t.at["110602", "vacant_share"] == pytest.approx(0.08) and t.at["110602", "name"] == "B"
    assert t.at["110602", "dico"] == "1106"
