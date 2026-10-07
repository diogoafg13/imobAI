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


def test_summarize_probe_lists_dims_levels_and_periods():
    import pandas as pd
    from imopt import discover
    df = pd.DataFrame({"geocod": ["PT", "1106", "110601", "110602"], "period": ["2021"] * 4,
                       "dim_3": ["T", "1", "1", "2"], "dim_3_t": ["Total", "Antes de 1919", "Antes de 1919", "1919 - 1945"],
                       "value": [1, 2, 3, 4]})
    s = discover.summarize(df)
    assert s["dims"]["dim_3"] == {"T": "Total", "1": "Antes de 1919", "2": "1919 - 1945"}
    assert s["geocod_len"] == {"6": 2, "2": 1, "4": 1} and s["periods"] == ["2021", "2021", 1] and s["rows"] == 4


def test_ogc_probe_lists_collections_samples_and_cors(tmp_path, monkeypatch):
    import json as _json
    from imopt import discover

    class R:
        def __init__(self, js, headers=None, status=200):
            self._js, self.headers, self.status_code = js, headers or {}, status
            self.ok = status == 200
            self.text = _json.dumps(js)

        def json(self):
            return self._js

        def raise_for_status(self):
            if not self.ok:
                raise RuntimeError(self.status_code)

    def get(url, params=None, headers=None, timeout=None):
        if url.endswith("/"):
            return R({"title": "DGT"}, {"Access-Control-Allow-Origin": "*"})
        if url.endswith("/collections"):
            return R({"collections": [{"id": "crus_fafe"}, {"id": "crus_loures"}, {"id": "ren_braga"}, {"id": "orto"}]},
                     {"Access-Control-Allow-Origin": "*"})
        if url.endswith("/items"):
            return R({"features": [{"properties": {"classe": "Solo urbano", "categoria": "Espaços habitacionais"},
                                    "geometry": {"type": "MultiPolygon", "coordinates": []}}]})
        return R({"id": url.rsplit("/", 1)[-1]})

    monkeypatch.setattr(discover.requests, "get", get)
    st = discover.ogc_probe({"dgt": {"base": "http://x", "sample": ["crus_fafe"], "grep": ["^crus_", "ren"]}}, tmp_path)
    assert "4 coleções" in st and "crus_: 2" in st and "ren: 1" in st and "exemplos com dados" in st
    d = _json.loads((tmp_path / "clean" / "ogc_probe.json").read_text())
    api = d["apis"]["dgt"]
    assert api["cors"] == "*" and set(api["samples"]) == {"crus_fafe", "ren_braga"}
    assert api["samples"]["crus_fafe"]["properties"] == ["categoria", "classe"]
    assert (tmp_path / "raw" / "services" / "dgt_collections.json").exists()


def test_ogc_probe_survives_a_failing_collection_list(tmp_path, monkeypatch):
    import json as _json
    from imopt import discover

    class R:
        def __init__(self, js, status=200):
            self._js, self.status_code, self.headers = js, status, {}
            self.ok = status == 200
            self.text = _json.dumps(js)

        def json(self):
            return self._js

        def raise_for_status(self):
            if not self.ok:
                raise RuntimeError(f"{self.status_code} Server Error")

    def get(url, params=None, headers=None, timeout=None):
        if url.endswith("/collections"):
            return R({}, 502)
        if url.endswith("/items"):
            return R({"features": [{"properties": {"classe": "Solo urbano"}, "geometry": {"type": "Polygon"}}]})
        return R({})

    monkeypatch.setattr(discover.requests, "get", get)
    st = discover.ogc_probe({"dgt": {"base": "http://x", "sample": ["crus_fafe"], "grep": ["^crus_"]}}, tmp_path)
    assert "lista indisponível" in st and "crus_fafe" in st
    d = _json.loads((tmp_path / "clean" / "ogc_probe.json").read_text())
    assert d["ok"] and "502" in d["apis"]["dgt"]["collections_error"]
    assert d["apis"]["dgt"]["samples"]["crus_fafe"]["properties"] == ["classe"]


def test_ogc_probe_cache_is_invalidated_by_a_config_change(tmp_path, monkeypatch):
    import json as _json
    from imopt import discover
    calls = []

    class R:
        status_code, ok, headers, text = 200, True, {}, "{}"

        def json(self):
            return {"collections": [{"id": "crus"}], "features": []}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(discover.requests, "get", lambda url, params=None, headers=None, timeout=None: (calls.append(url), R())[1])
    discover.ogc_probe({"dgt": {"base": "http://x", "sample": ["crus"]}}, tmp_path)
    n = len(calls)
    discover.ogc_probe({"dgt": {"base": "http://x", "sample": ["crus"]}}, tmp_path)
    assert len(calls) == n                                         # mesma configuração: cache
    discover.ogc_probe({"dgt": {"base": "http://x", "sample": ["crus", "cadastro"]}}, tmp_path)
    assert len(calls) > n                                          # configuração nova: repete
