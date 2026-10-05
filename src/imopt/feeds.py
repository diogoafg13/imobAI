"""Feeds RSS por concelho (data/rss/<DICO>.xml), gerados em cada build.

Ficheiros estáticos: qualquer leitor de RSS (ou app de notícias) avisa quando sai um trimestre novo de preços, um
ano novo de rendas, uma mudança de faixa de risco ou uma taxa de IMI nova do concelho. Cada item tem um
identificador fixo (concelho + tipo + período): o leitor só mostra como novo o que ainda não viu.
"""
from __future__ import annotations

import datetime as dt
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

BANDS = {"green": "verde (menos esticado)", "amber": "amarela", "red": "vermelha (mais esticado)"}


def _q(p: str) -> str:
    return str(p).replace("Q", "T")


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%".replace(".", ",")


def _eur(x: float) -> str:
    return f"{x:,.0f} €".replace(",", " ")


def items_for(m: dict, site_url: str) -> list[dict]:
    """Itens (mais recentes primeiro) de um concelho, a partir dos números já calculados para o site."""
    link = f"{site_url}#c-{m['dico']}"
    out = []
    price = (m.get("series") or {}).get("price") or []
    for i in range(len(price) - 1, max(len(price) - 9, 0), -1):
        p, v = price[i]
        prev = price[i - 1][1] if i >= 1 else None
        yago = next((x[1] for x in price if x[0] == f"{int(str(p)[:4]) - 1}{str(p)[4:]}"), None)
        bits = [f"{_eur(v)}/m²"] + ([f"{_pct(v / prev - 1)} no trimestre"] if prev else []) + ([f"{_pct(v / yago - 1)} num ano"] if yago else [])
        out.append({"guid": f"{m['dico']}-preco-{p}", "title": f"{m['name']}: preço mediano de venda {_q(p)}",
                    "desc": f"Preço mediano das vendas dos últimos 12 meses (INE), {_q(p)}: " + ", ".join(bits) + ".", "link": link,
                    "key": str(p)})
    rent = (m.get("series") or {}).get("rent") or []
    for i in range(len(rent) - 1, max(len(rent) - 4, 0), -1):
        y, v = rent[i]
        prev = rent[i - 1][1] if i >= 1 else None
        out.append({"guid": f"{m['dico']}-renda-{y}", "title": f"{m['name']}: renda mediana de novos contratos {y}",
                    "desc": f"Renda mediana dos novos contratos de arrendamento (INE), {y}: {v:.2f} €/m²".replace(".", ",")
                    + (f" ({_pct(v / prev - 1)} num ano)." if prev else "."), "link": link, "key": f"{y}Q4"})
    if m.get("band_prev") and m.get("band") and m["band_prev"] != m["band"] and m.get("latest_period"):
        p = m["latest_period"]
        out.append({"guid": f"{m['dico']}-faixa-{p}", "title": f"{m['name']}: faixa de risco passou a {BANDS.get(m['band'], m['band'])}",
                    "desc": f"Com os preços de {_q(p)}, o score passou de {m.get('score_prev', 0):.0f} para {m.get('score_overall', 0):.0f} "
                    f"(faixa {BANDS.get(m['band_prev'], m['band_prev'])} → {BANDS.get(m['band'], m['band'])}). O score é relativo aos outros concelhos e não é uma previsão.",
                    "link": link, "key": str(p)})
    if m.get("imi_year") and (m.get("imi_rate") is not None or m.get("imi_parish_rates")):
        y = m["imi_year"]
        rate = "taxas diferentes por freguesia" if m.get("imi_rate") is None else f"{m['imi_rate'] * 100:.3f}%".replace(".", ",")
        out.append({"guid": f"{m['dico']}-imi-{y}", "title": f"{m['name']}: taxa de IMI de {y}",
                    "desc": f"Taxa de IMI dos prédios urbanos para o IMI de {y} (cobrado em {y + 1}), Finanças: {rate}.",
                    "link": link, "key": f"{y}Q4"})
    return sorted(out, key=lambda x: x["key"], reverse=True)


def render(m: dict, items: list[dict], site_url: str, built: dt.datetime) -> str:
    pub = format_datetime(built)
    body = "".join(
        f"<item><title>{escape(i['title'])}</title><link>{escape(i['link'])}</link>"
        f"<guid isPermaLink=\"false\">{escape(i['guid'])}</guid><description>{escape(i['desc'])}</description></item>"
        for i in items)
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<rss version=\"2.0\"><channel>"
            f"<title>{escape(m['name'])} — Painel de Risco Imobiliário</title><link>{escape(site_url)}#c-{m['dico']}</link>"
            f"<description>Novos dados de preços, rendas, faixa de risco e IMI de {escape(m['name'])}. Indicadores "
            f"informativos, não aconselhamento financeiro.</description><language>pt-PT</language>"
            f"<lastBuildDate>{pub}</lastBuildDate>{body}</channel></rss>\n")


def write(munis: list[dict], out_dir: Path, site_url: str, latest_period: str | None = None) -> int:
    built = dt.datetime.now(dt.timezone.utc)
    d = Path(out_dir) / "rss"
    d.mkdir(parents=True, exist_ok=True)
    n = 0
    for m in munis:
        mm = {**m, "latest_period": latest_period}
        (d / f"{m['dico']}.xml").write_text(render(mm, items_for(mm, site_url), site_url, built), encoding="utf-8")
        n += 1
    return n
