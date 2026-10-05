import json
import xml.etree.ElementTree as ET

from imopt import demo, feeds, pipeline


def test_feed_items_have_stable_ids_and_newest_first():
    m = {"dico": "1107", "name": "Loures", "band": "red", "band_prev": "amber", "score_prev": 60.0, "score_overall": 72.0,
         "imi_rate": 0.00361, "imi_year": 2025,
         "series": {"price": [["2025Q1", 2700.0], ["2025Q2", 2800.0], ["2025Q3", 2900.0], ["2025Q4", 3000.0], ["2026Q1", 3100.0]],
                    "rent": [["2024", 10.0], ["2025", 11.0]]}}
    items = feeds.items_for({**m, "latest_period": "2026Q1"}, "https://x/")
    guids = [i["guid"] for i in items]
    assert guids[0] in ("1107-preco-2026Q1", "1107-faixa-2026Q1") and "1107-renda-2025" in guids and "1107-imi-2025" in guids
    p = next(i for i in items if i["guid"] == "1107-preco-2026Q1")
    assert "+3,3% no trimestre" in p["desc"] and "+14,8% num ano" in p["desc"] and p["link"] == "https://x/#c-1107"
    assert len(guids) == len(set(guids))


def test_build_writes_valid_rss_per_municipality(tmp_path):
    frames, macro_frames = demo.demo_frames()
    pipeline.build_outputs(frames, macro_frames, {}, {}, tmp_path, None, demo=True)
    m = json.loads((tmp_path / "municipalities.json").read_text(encoding="utf-8"))
    files = list((tmp_path / "rss").glob("*.xml"))
    assert len(files) == len(m)
    root = ET.parse(files[0]).getroot()
    assert root.tag == "rss" and root.find("channel/item/guid") is not None
