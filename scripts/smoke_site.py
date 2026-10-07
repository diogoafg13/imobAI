"""Teste do site no browser (Chromium, Playwright): abre todos os separadores e guias com os dados do build e falha se
aparecer um erro de JavaScript, "NaN"/"undefined" no texto, ou um guia sem resultado.

Corre no workflow depois de construir os dados e antes de publicar: se falhar, a versão nova não é publicada (o site
anterior continua no ar) — os dados já ficaram guardados no branch `data`.

    python scripts/smoke_site.py site            # usa o Chromium do Playwright
    SMOKE_CHROMIUM=/caminho/chromium python scripts/smoke_site.py site

Bibliotecas vindas de CDN (gráficos, mapa) que não carreguem e a falta de WebGL no runner dão aviso, não erro: não são
defeitos do site.
"""
from __future__ import annotations

import functools
import http.server
import os
import re
import sys
import threading

from playwright.sync_api import sync_playwright

BAD_TEXT = re.compile(r"\bNaN\b|\bundefined\b|\bInfinity\b|\[object Object\]")
TABS = ["mercado", "guia", "seguir", "comprar", "arrendar", "investir", "imovel", "perspetivas", "metodo"]


class Smoke:
    def __init__(self, page):
        self.pg, self.errors, self.warnings, self.cdn_failed = page, [], [], False
        page.on("pageerror", lambda e: self.errors.append(f"erro de JavaScript: {str(e)[:200]} | {(getattr(e, 'stack', '') or '').splitlines()[1:3]}"))
        page.on("console", self._console)
        page.on("requestfailed", self._reqfail)

    def _reqfail(self, req):
        if not req.url.startswith("http://127.0.0.1"):
            self.cdn_failed = True
            self.warnings.append(f"pedido externo falhou: {req.url[:120]}")

    def _console(self, msg):
        if msg.type != "error":
            return
        t = msg.text
        if t.startswith("Failed to load resource"):
            return
        external = re.search(r"echarts is not defined|maplibregl is not defined", t) and self.cdn_failed
        webgl = "WebGL" in t or "webgl" in t
        (self.warnings if external or webgl else self.errors).append(f"consola: {t[:300]}")

    def check_text(self, where: str):
        txt = self.pg.evaluate("document.querySelector('main') ? document.querySelector('main').innerText : document.body.innerText")
        for m in BAD_TEXT.finditer(txt):
            ctx = txt[max(0, m.start() - 80):m.end() + 40].replace("\n", " ")
            self.errors.append(f"{where}: texto '{m.group()}' em …{ctx}…")
            break

    def need(self, sel: str, where: str):
        if not self.pg.query_selector(sel):
            self.errors.append(f"{where}: não apareceu {sel}")


def run(site: str) -> int:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=site)
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    with sync_playwright() as p:
        kw = {"args": ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]}
        if os.environ.get("SMOKE_CHROMIUM"):
            kw["executable_path"] = os.environ["SMOKE_CHROMIUM"]
        browser = p.chromium.launch(**kw)
        ctx = browser.new_context(viewport={"width": 1200, "height": 900})
        ctx.add_init_script("navigator.clipboard && (navigator.clipboard.writeText = (t) => { window.__copied = t; return Promise.resolve(); });")
        pg = ctx.new_page()
        s = Smoke(pg)
        try:
            steps(pg, s, ctx, base)
        except Exception as e:  # noqa: BLE001
            s.errors.append(f"o teste parou: {str(e).splitlines()[0][:300]}")
        browser.close()
    srv.shutdown()
    for w in dict.fromkeys(s.warnings):
        print(f"::warning::teste do site: {w}")
    for e in dict.fromkeys(s.errors):
        print(f"::error::teste do site: {e}")
    print(f"teste do site: {len(s.errors)} erros, {len(set(s.warnings))} avisos")
    return 1 if s.errors else 0


def steps(pg, s: Smoke, ctx, base: str) -> None:
    pg.goto(base + "#mercado")
    pg.wait_for_timeout(4000)
    munis = pg.evaluate("fetch('data/municipalities.json').then(r => r.json()).then(m => m.map(x => [x.dico, x.name]))")
    names = dict(munis)
    lisboa = "1106" if "1106" in names else munis[0][0]
    porto = "1312" if "1312" in names else munis[1][0]

    # 1) todos os separadores
    for t in TABS:
        pg.click(f"#topnav a[data-tab={t}]")
        pg.wait_for_timeout(600)
        s.check_text(f"separador {t}")

    # 2) mercado: um concelho, todas as métricas do mapa, freguesias
    pg.goto(base + f"#c-{lisboa}")
    pg.wait_for_timeout(1500)
    s.need("#detail:not(.off)", "detalhe do concelho")
    for v in pg.eval_on_selector_all("#metric option", "e => e.map(o => o.value)"):
        pg.select_option("#metric", v)
        pg.wait_for_timeout(80)
    if pg.query_selector("button[data-lvl=f]"):
        pg.click("button[data-lvl=f]")
        pg.wait_for_timeout(1500)
        for v in pg.eval_on_selector_all("#metric-f option", "e => e.map(o => o.value)"):
            pg.select_option("#metric-f", v)
            pg.wait_for_timeout(80)
    s.check_text("mercado")

    # 3) comprar, arrendar, investir, o meu imóvel
    pg.click("#topnav a[data-tab=arrendar]")
    pg.fill("#rent-form [name=inc]", "2000")
    pg.click("#rent-form button[type=submit]")
    pg.wait_for_timeout(500)
    s.check_text("arrendar")
    pg.click("#topnav a[data-tab=investir]")
    pg.fill("#inv-form [name=conc]", names[porto])
    pg.click("#inv-form button[type=submit]")
    pg.wait_for_timeout(500)
    s.need("#inv-out .stats", "investir")
    s.check_text("investir")
    pg.click("#topnav a[data-tab=imovel]")
    pg.fill("#im-form [name=conc]", names[porto])
    pg.dispatch_event("#im-form [name=conc]", "change")
    pg.wait_for_timeout(500)
    opts = pg.eval_on_selector_all("#im-form [name=year] option", "e => e.map(o => o.value).filter(Boolean)")
    if opts:
        pg.select_option("#im-form [name=year]", sorted(opts)[len(opts) // 2])
    mopts = pg.eval_on_selector_all("#im-form [name=month] option", "e => e.map(o => o.value).filter(Boolean)")
    if mopts:
        pg.select_option("#im-form [name=month]", mopts[0])
    pg.fill("#im-form [name=price]", "200000")
    pg.fill("#im-form [name=area]", "90")
    pg.click("#im-form button[type=submit]")
    pg.wait_for_timeout(1500)
    s.check_text("o meu imóvel")

    # 4) guias
    pg.click("#topnav a[data-tab=guia]")
    pg.click("[data-gp=where]")
    for goal, fill in (("buy", {"savings": "40000", "income": "2500"}), ("rent", {"income": "1800"}),
                       ("invest", {"savings": "60000", "income": "3000"})):
        pg.click("#g-reset")
        pg.check(f"#guide-form input[name=goal][value={goal}]")
        pg.click("#g-next")
        pg.click("#g-next")
        for k, v in fill.items():
            pg.fill(f"#guide-form [name={k}]", v)
        pg.click("#g-next")
        pg.click("#g-next")
        pg.wait_for_timeout(500)
        pg.click("#g-go")
        pg.wait_for_timeout(1500)
        s.need("#guide-out .g-res > li", f"guia onde procurar ({goal})")
        s.check_text(f"guia onde procurar ({goal})")
    guides = [("young", "gy", {"price": "250000", "savings": "15000", "income": "2400"}),
              ("loan", "gl", {"loan": "200000", "income": "3000", "extra": "200"}),
              ("landlord", "gs", {"conc": names[porto], "area": "80"}),
              ("tenant", "gt", {"conc": names[lisboa], "area": "70", "rent": "1300", "income": "3000"}),
              ("sell", "gv", {"conc": names[porto], "area": "90", "buy": "160000", "bal": "50000"}),
              ("land", "gn", {"conc": names[porto], "area": "800", "iu": "0.6", "asking": "150000", "ll": "41.1579, -8.6291"})]
    for kind, fid, fill in guides:
        pg.click(f"[data-gp={kind}]")
        for k, v in fill.items():
            pg.fill(f"#{fid}-form [name={k}]", v)
            if k == "conc":
                pg.dispatch_event(f"#{fid}-form [name=conc]", "change")
                pg.wait_for_timeout(500)
        pg.click(f"#{fid}-form button[type=submit]")
        pg.wait_for_timeout(500)
        s.need(f"#{fid}-out .stats, #{fid}-out table", f"guia {kind}")
        s.check_text(f"guia {kind}")
    # ligação partilhada: gerar e abrir numa página nova
    pg.click("[data-gp=loan]")
    pg.click("#gl-out [data-share]")
    link = pg.evaluate("window.__copied")
    if not link or "#guia?" not in link:
        s.errors.append("guia: a ligação para partilhar não foi gerada")
    else:
        q = ctx.new_page()
        s2 = Smoke(q)
        q.goto(link)
        q.wait_for_timeout(3000)
        if not q.query_selector("#gl-out table"):
            s.errors.append("guia: a ligação partilhada não reproduz o resultado")
        s.errors += s2.errors
        s.warnings += s2.warnings


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "site"))
