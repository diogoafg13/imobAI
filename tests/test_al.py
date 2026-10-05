import pandas as pd
import pytest

from imopt import al


def _square(code, x0, y0):
    return {"type": "Feature", "properties": {"code": code},
            "geometry": {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + 1, y0], [x0 + 1, y0 + 1], [x0, y0 + 1], [x0, y0]]]}}


def test_read_points_semicolon_decimal_comma_and_swapped_coords():
    csv = "Nº de registo;Latitude;Longitude;Freguesia;Concelho;Nº Utentes\n1;38,5;-9,5;Alfama;Lisboa;4\n2;-8,5;40,5;Sé;Porto;2\n"
    p = al.read_points(csv)
    assert list(p.columns) == ["lat", "lon", "freguesia", "concelho", "utentes"]
    assert p.loc[0, "lat"] == 38.5 and p.loc[1, "lat"] == 40.5 and p.loc[1, "lon"] == -8.5 and p["utentes"].sum() == 6
    with pytest.raises(ValueError):
        al.read_points("a,b\n1,2\n")


def test_by_parish_uses_coordinates_then_names():
    gj = {"type": "FeatureCollection", "features": [_square("110601", -10, 38), _square("110602", -9, 38)]}
    pts = pd.DataFrame({"lat": [38.5, 38.5, 38.2, None], "lon": [-9.5, -8.5, -8.1, None],
                        "freguesia": ["x", "y", "z", "Freg B"], "concelho": ["Lisboa"] * 4, "utentes": [2, 4, 6, 8]})
    out = al.by_parish(pts, gj, {"110602": ("Freg B", "Lisboa")})
    assert out.loc["110601", "al_n"] == 1 and out.loc["110602", "al_n"] == 3 and out.loc["110602", "al_users"] == 18
    assert out.attrs["matched"] == 1.0
    f = al.per_parish_fields(out, pd.Series({"110601": 100.0, "110602": 0.0}))
    assert f.loc["110601", "al_per_100"] == 1.0 and pd.isna(f.loc["110602", "al_per_100"])
