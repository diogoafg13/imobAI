from imopt import osm


def _square(code, x0, y0):
    return {"type": "Feature", "properties": {"code": code},
            "geometry": {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + 1, y0], [x0 + 1, y0 + 1], [x0, y0 + 1], [x0, y0]]]}}


def test_parse_nodes_and_way_centers_then_count_by_parish():
    js = {"elements": [{"type": "node", "lat": 38.5, "lon": -9.5}, {"type": "way", "center": {"lat": 38.6, "lon": -8.5}},
                       {"type": "relation"}]}
    p = osm.parse(js, "school")
    assert len(p) == 2 and set(p["kind"]) == {"school"}
    p2 = osm.parse({"elements": [{"lat": 38.2, "lon": -8.2}]}, "station")
    gj = {"features": [_square("110601", -10, 38), _square("110602", -9, 38)]}
    import pandas as pd
    out = osm.by_parish(pd.concat([p, p2]), gj)
    assert out.loc["110601", "n_school"] == 1 and out.loc["110602", "n_school"] == 1 and out.loc["110602", "n_station"] == 1
    assert out.loc["110601", "n_health"] == 0 and out.attrs["matched"] == 1.0
    assert 'area["ISO3166-1"="PT"]' in osm.query(osm.KINDS["school"])
