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
