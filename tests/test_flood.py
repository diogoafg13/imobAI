from imopt import flood


def _square(code, x0, y0, size=1.0):
    return {"type": "Feature", "properties": {"code": code},
            "geometry": {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + size, y0], [x0 + size, y0 + size],
                                                             [x0, y0 + size], [x0, y0]]]}}


def test_pick_return_period_prefers_100_years():
    assert flood.pick_return_period([20, 100, 1000]) == 100
    assert flood.pick_return_period(["T20", "T100", "T1000"]) == "T100"
    assert flood.pick_return_period([20, 1000]) == 20        # o mais próximo de 100 (empate desfeito pelo menor)
    assert flood.pick_return_period([None, ""]) is None


def test_esri_rings_to_multipolygon_with_hole():
    outer = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]                  # sentido horário = exterior
    hole = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8], [0.2, 0.2]]  # anti-horário = buraco
    other = [[2, 0], [2, 1], [3, 1], [3, 0], [2, 0]]
    g = flood.esri_to_geojson({"attributes": {"pretorno": 100}, "geometry": {"rings": [outer, hole, other]}})
    assert g["geometry"]["type"] == "MultiPolygon"
    assert [len(p) for p in g["geometry"]["coordinates"]] == [2, 1]
    from shapely.geometry import shape
    assert abs(shape(g["geometry"]).area - (1 - 0.36 + 1)) < 1e-9


def test_by_parish_share_of_area_and_none_without_zone():
    zones = {"features": [_square(None, -9.0, 38.0, 0.5)]}             # um quarto da freguesia A
    gj = {"features": [_square("110601", -9.0, 38.0), _square("110602", -7.0, 38.0)]}
    out = flood.by_parish(zones, gj)
    assert out == {"110601": 25.0}                                      # B sem zona cartografada: sem valor
    assert flood.by_parish(None, gj) is None
