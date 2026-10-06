import json

from imopt import discover


class _R:
    def __init__(self, text="", ok=True, js=None):
        self.text, self.ok, self._js = text, ok, js

    def json(self):
        return self._js

    def raise_for_status(self):
        pass


XML = "<catalog><indicator><varcd>0012999</varcd><title>Edifícios por época de construção</title></indicator></catalog>"


def test_catalog_scan_is_progressive_and_saved(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, params=None, **kw):
        calls.append(params)
        if params.get("opc") == 1 and params["varcd"] == "0012999":
            return _R(XML)
        return _R("<catalog></catalog>")
    monkeypatch.setattr(discover.requests, "get", fake_get)
    monkeypatch.setattr(discover.catalog, "fetch_main_catalog", lambda: [])
    cfg = {"ine_ranges": ["0012995-0013004"], "max_requests": 6, "delay": 0}
    st = discover.ine_catalog(cfg, tmp_path)
    d = json.loads((tmp_path / "clean" / "ine_catalog.json").read_text(encoding="utf-8"))
    assert not d["complete"] and len(d["scanned"]) == 6 and "continua" in st
    assert [i["varcd"] for i in d["items"]] == ["0012999"]
    discover.ine_catalog(cfg, tmp_path)             # segundo build: só os 4 que faltam
    d = json.loads((tmp_path / "clean" / "ine_catalog.json").read_text(encoding="utf-8"))
    assert d["complete"] and len(d["scanned"]) == 10
