import json

import pandas as pd
import pytest

from imopt import demo, imi, pipeline

FORM = """<form><select name="ano"><option value="">--</option><option value="2024">2024</option>
<option value="2025" selected>2025</option></select>
<select name="distrito"><option value="01AVEIRO">Aveiro</option><option value="11LISBOA">Lisboa</option></select></form>"""

TABLE = """<table><tr><th>Código</th><th>Município</th><th>Taxa Prédios Urbanos</th><th>Taxa Prédios Rústicos</th>
<th>Taxas por freguesia</th><th>Dedução 1 dependente</th><th>Dedução 2 dependentes</th><th>Dedução 3 ou mais dependentes</th></tr>
<tr><td>1106</td><td>LISBOA</td><td>0,300%</td><td>0,8%</td><td></td><td>30,00 €</td><td>70,00 €</td><td>140,00 €</td></tr>
<tr><td>1107</td><td>LOURES</td><td>0,375</td><td>0,8%</td><td>+Info</td><td>-</td><td>-</td><td>-</td></tr>
<tr><td>1304</td><td>GONDOMAR</td><td>-</td><td>-</td><td>+Info</td><td>+Info</td><td></td><td></td></tr>
<tr><td colspan="8">Notas</td></tr></table>"""


def test_parse_form_and_district_table():
    opts = imi.select_options(FORM)
    assert opts["ano"] == ["2024", "2025"] and opts["distrito"] == ["01AVEIRO", "11LISBOA"]
    rows = imi.parse_district(TABLE)
    assert [r["code"] for r in rows] == ["1106", "1107", "1304"] and rows[0]["name"] == "LISBOA"
    assert rows[2]["rate_urban"] is None and rows[2]["parish_rates"]
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
    pd.DataFrame({"dico": ["1106"], "rate_urban": [0.003], "year": [2025], "parser_v": [imi.PARSER_V]}).to_parquet(
        tmp_path / "clean" / "imi_rates.parquet")
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


def test_ingest_uses_district_select_and_falls_back_to_previous_year(tmp_path, monkeypatch):
    calls = []
    big = "<table><tr><th>Código</th><th>Município</th><th>Taxa Prédios Urbanos</th></tr>" + "".join(
        f"<tr><td>{1000 + i}</td><td>M{i}</td><td>0,3</td></tr>" for i in range(300)) + "</table>"

    def fake(url, params):
        calls.append(dict(params))
        if "ano" not in params:
            return FORM
        return big if params["ano"] == 2024 else "<table><tr><th>Município</th><th>Urbanos</th></tr></table>"
    monkeypatch.setattr(imi, "_get", fake)
    df, st = imi.ingest({"form_url": "f", "table_url": "t"}, tmp_path, "20261005", pause=0)
    assert st.startswith("ok (300 concelhos, taxas de 2024") and len(df) == 300
    # 2025 ainda vazio -> 2024; só os distritos do select "distrito", nunca os anos
    assert {c["distrito"] for c in calls if "ano" in c} == {"01AVEIRO", "11LISBOA"}
    assert (tmp_path / "raw" / "imi" / "2025" / "11LISBOA.html").exists()


def test_chain_indices_across_base_change():
    from imopt import macro
    old = pd.DataFrame({"period": ["2025-10", "2025-11", "2025-12"], "value": [125.0, 126.0, 127.0]})
    new = pd.DataFrame({"period": ["2025-11", "2025-12", "2026-01"], "value": [100.0, 100.8, 101.6]})
    out = macro.chain_indices([old, new])
    k = (126 / 100 + 127 / 100.8) / 2
    assert list(out["period"]) == ["2025-10", "2025-11", "2025-12", "2026-01"]
    assert out["value"].iloc[-1] == pytest.approx(101.6 * k) and out["value"].iloc[1] == 126.0


def test_macro_failure_uses_previous_snapshot(tmp_path, monkeypatch):
    from imopt import macro
    (tmp_path / "clean").mkdir()
    pd.DataFrame({"period": ["2025Q4"], "value": [1.0]}).to_parquet(tmp_path / "clean" / "macro_euribor_12m.parquet")
    def boom(cfg):
        raise ConnectionError("sem rede")
    monkeypatch.setitem(macro.FETCHERS, "euribor_12m", boom)
    monkeypatch.setitem(macro.FETCHERS, "euribor_3m", boom)
    frames, st = pipeline.ingest_macro({"macro": {"euribor_12m": {}, "euribor_3m": {}}}, tmp_path)
    assert st["euribor_12m"].startswith("CACHE") and len(frames["euribor_12m"]) == 1
    assert st["euribor_3m"].startswith("ERRO") and "euribor_3m" not in frames


def test_match_dico_mainland_by_code_islands_by_name_within_region():
    names = {"0806": "Lagoa", "4201": "Lagoa (R.A.A.)", "3101": "Calheta (R.A.M.)", "4501": "Calheta (R.A.A.)",
             "3110": "São Vicente", "4302": "Vila da Praia da Vitória", "1106": "Lisboa"}
    df = pd.DataFrame({"code": ["0806", "2101", "2201", "1902", "2211", "1905", "1106", "2001"],
                       "name": ["LAGOA", "LAGOA (AÇORES)", "CALHETA (MADEIRA)", "CALHETA (AÇORES)", "S. VICENTE",
                                "VILA PRAIA DA VITORIA", "LISBOA", "CORVO"]})
    assert imi.match_dico(df, names) == ["0806", "4201", "3101", "4501", "3110", "4302", "1106", None]
