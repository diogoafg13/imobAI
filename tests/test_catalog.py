from imopt import catalog, cli

XML = """<catalog><indicator id="0012234"><title><![CDATA[ Valor mediano das vendas por m² de alojamentos familiares ]]></title>
<varcd> 0012234 </varcd><geo_lastlevel> Freguesia </geo_lastlevel><source> INE, Estatísticas de Preços da Habitação ao nível local </source>
<dates><last_period_available> S5A20261 </last_period_available></dates><periodicity> Trimestral </periodicity></indicator>
<indicator id="0012088"><title> Dormidas (N.º) nos estabelecimentos de alojamento turístico </title><varcd>0012088</varcd>
<geo_lastlevel>Município</geo_lastlevel><periodicity>Mensal</periodicity></indicator></catalog>"""


def test_parse_and_match_ignores_accents_and_case():
    items = catalog.parse_catalog(XML)
    assert [i["varcd"] for i in items] == ["0012234", "0012088"]
    assert items[0]["geo"] == "Freguesia" and items[0]["periodicity"] == "Trimestral"
    assert [i["varcd"] for i in catalog.matches(items, ["VENDAS", "habitacao"])] == ["0012234"]
    assert catalog.matches(items, ["vendas", "turistico"]) == []


def test_scan_range_queries_each_code(monkeypatch):
    asked = []

    class R:
        ok = True

        def __init__(self, varcd):
            self.text = XML if varcd == "0012234" else "<catalog></catalog>"

    monkeypatch.setattr(catalog.requests, "get", lambda url, params, **k: asked.append(params["varcd"]) or R(params["varcd"]))
    items = catalog.scan_range(12233, 12235, delay=0)
    assert asked == ["0012233", "0012234", "0012235"] and {i["varcd"] for i in items} == {"0012234", "0012088"}


def test_cli_search_file(tmp_path, capsys):
    f = tmp_path / "cat.xml"
    f.write_text(XML, encoding="utf-8")
    assert cli.main(["search", "dormidas", "--file", str(f)]) == 0
    out = capsys.readouterr().out
    assert "1 de 2" in out and "0012088" in out and "Município" in out
