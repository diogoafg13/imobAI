from imopt import osm


def _square(code, x0, y0):
    return {"type": "Feature", "properties": {"code": code},
            "geometry": {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + 1, y0], [x0 + 1, y0 + 1], [x0, y0 + 1], [x0, y0]]]}}


def test_parse_classifies_by_tags_then_count_by_parish():
    js = {"elements": [{"type": "node", "lat": 38.5, "lon": -9.5, "tags": {"amenity": "school"}},
                       {"type": "way", "center": {"lat": 38.6, "lon": -8.5}, "tags": {"amenity": "school"}},
                       {"type": "node", "lat": 38.2, "lon": -8.2, "tags": {"railway": "halt"}},
                       {"type": "node", "lat": 38.3, "lon": -8.3, "tags": {"amenity": "pharmacy"}},
                       {"type": "relation", "tags": {"amenity": "clinic"}}]}
    p = osm.parse(js)
    assert sorted(p["kind"]) == ["school", "school", "station"]
    gj = {"features": [_square("110601", -10, 38), _square("110602", -9, 38)]}
    out = osm.by_parish(p, gj)
    assert out.loc["110601", "n_school"] == 1 and out.loc["110602", "n_school"] == 1 and out.loc["110602", "n_station"] == 1
    assert out.loc["110601", "n_health"] == 0 and out.attrs["matched"] == 1.0
    assert osm.kind_of({"amenity": "doctors"}) == "health"


def test_boxes_cover_portugal():
    def inside(lat, lon):
        return any(s <= lat <= n and w <= lon <= e for s, w, n, e in osm.BOXES)
    # Melgaço (norte), Sagres, Elvas, Funchal, Porto Santo, Ponta Delgada, Horta, Corvo
    for lat, lon in [(42.15, -8.26), (37.0, -8.94), (38.88, -7.16), (32.65, -16.91), (33.07, -16.34),
                     (37.74, -25.67), (38.53, -28.63), (39.70, -31.11)]:
        assert inside(lat, lon), (lat, lon)
    assert "[bbox:38,-9,39,-8]" in osm.query((38, -9, 39, -8))


def test_ingest_keeps_tiles_and_completes_across_builds(tmp_path, monkeypatch):
    import pandas as pd
    calls = []

    seq = iter(range(10**6))

    class R:
        def raise_for_status(self):
            pass

        def json(self):              # 40 escolas diferentes por quadrícula
            return {"elements": [{"lat": 38 + next(seq) * 1e-5, "lon": -9.5, "tags": {"amenity": "school"}} for _ in range(40)]}

    def post(url, data, headers, timeout):
        calls.append(data["data"])
        if len(calls) > 5:              # o servidor "cai" a meio do primeiro build
            raise osm.requests.ConnectionError("504")
        return R()

    monkeypatch.setattr(osm.requests, "post", post)
    monkeypatch.setattr(osm.time, "sleep", lambda s: None)
    cfg = {"urls": ["http://x"], "budget_s": 600}
    pts, st = osm.ingest(cfg, tmp_path)
    assert pts is None and "faltam" in st and "continua" in st
    calls.clear()
    monkeypatch.setattr(osm.requests, "post", lambda url, data, headers, timeout: (calls.append(1), R())[1])
    pts, st = osm.ingest(cfg, tmp_path)
    assert st.startswith("ok") and len(calls) == len(osm.BOXES) - 5      # só pede as que faltavam
    assert isinstance(pts, pd.DataFrame) and set(pts["kind"]) == {"school"}


def test_empty_sea_tiles_count_as_done(tmp_path, monkeypatch):
    class R:
        def __init__(self, n):
            self.n = n

        def raise_for_status(self):
            pass

        def json(self):
            return {"elements": [{"lat": 38 + len(calls) * 0.01 + i * 1e-4, "lon": -8.5, "tags": {"railway": "station"}}
                                 for i in range(self.n)]}

    calls = []

    def post(url, data, headers, timeout):
        calls.append(1)
        return R(0 if len(calls) % 2 else 80)       # metade das quadrículas só de mar

    monkeypatch.setattr(osm.requests, "post", post)
    monkeypatch.setattr(osm.time, "sleep", lambda s: None)
    pts, st = osm.ingest({"urls": ["http://x"]}, tmp_path)
    assert st.startswith("ok"), st
    calls.clear()
    pts2, st2 = osm.ingest({"urls": ["http://x"]}, tmp_path)
    assert calls == [] and len(pts2) == len(pts)                 # tudo em cache, nada pedido outra vez
