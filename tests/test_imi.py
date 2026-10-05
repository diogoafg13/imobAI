import json

import pandas as pd

from imopt import demo, imi, pipeline

FORM = """<form><select name="ano"><option value="">--</option><option value="2024">2024</option>
<option value="2025" selected>2025</option></select>
<select name="distrito"><option value="01AVEIRO">Aveiro</option><option value="11LISBOA">Lisboa</option></select></form>"""

TABLE = """<table><tr><th>Código</th><th>Município</th><th>Taxa Prédios Urbanos</th><th>Taxa Prédios Rústicos</th>
<th>Taxas por freguesia</th><th>Dedução 1 dependente</th><th>Dedução 2 dependentes</th><th>Dedução 3 ou mais dependentes</th></tr>
<tr><td>1106</td><td>LISBOA</td><td>0,300%</td><td>0,8%</td><td></td><td>30,00 €</td><td>70,00 €</td><td>140,00 €</td></tr>
<tr><td>1107</td><td>LOURES</td><td>0,375</td><td>0,8%</td><td>Sim: 0,35</td><td>-</td><td>-</td><td>-</td></tr>
<tr><td colspan="8">Notas</td></tr></table>"""


def test_parse_form_and_district_table():
    opts = imi.select_options(FORM)
    assert opts["ano"] == ["2024", "2025"] and opts["distrito"] == ["01AVEIRO", "11LISBOA"]
    rows = imi.parse_district(TABLE)
    assert [r["code"] for r in rows] == ["1106", "1107"]
    assert rows[0]["rate_urban"] == 0.003 and rows[1]["rate_urban"] == 0.00375
    assert rows[0]["ded_1"] == 30.0 and rows[0]["ded_3"] == 140.0 and rows[1]["ded_1"] is None
    assert rows[1]["parish_rates"] and not rows[0]["parish_rates"]
    assert imi.parse_rate("0,45 %") == 0.0045 and imi.parse_rate("45") is None and imi.parse_rate("") is None


def test_ingest_without_network_keeps_cache(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("sem rede")
    monkeypatch.setattr(imi, "_get", boom)
    df, st = imi.ingest({"form_url": "x", "table_url": "y"}, tmp_path, "20260101")
    assert df is None and st.startswith("ERRO")
    (tmp_path / "clean").mkdir()
    pd.DataFrame({"dico": ["1106"], "rate_urban": [0.003], "year": [2025]}).to_parquet(tmp_path / "clean" / "imi_rates.parquet")
    df, st = imi.ingest({"form_url": "x", "table_url": "y"}, tmp_path, "20260101")
    assert len(df) == 1 and st.startswith("CACHE")


def test_imi_rates_reach_municipalities(tmp_path):
    frames, macro_frames = demo.demo_frames()
    pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path, None, demo=True,
                           imi_rates=demo.demo_imi(frames), imi_status="sintético")
    m = json.loads((tmp_path / "municipalities.json").read_text(encoding="utf-8"))
    assert all(0.003 <= x["imi_rate"] <= 0.0045 and x["imi_year"] == 2025 for x in m)
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["sources"]["at"]["imi_rates"] == "sintético"
