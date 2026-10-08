"""O que o imobiliário rendeu de facto, por concelho: retorno total real dos últimos 5 anos.

Shiller e Dimson insistem em olhar para o retorno total (rendimento + valorização), descontada a inflação, e não só para
o preço. Aqui, com as séries do painel:
- valorização real: preço mediano descontado do IHPC (série `price_real`), de um trimestre ao mesmo trimestre 5 anos
  antes, em taxa anual;
- rendimento: renda mediana dos contratos novos × 12 sobre o preço médio desse ano, média dos anos com os dois
  valores, menos 25% de custos (IMI, condomínio, seguro, manutenção, meses vazios; pressuposto) — antes de IRS;
- inflação do período: a que separa o preço nominal do real.
É uma aproximação: medianas do concelho (a mistura de casas vendidas muda), rendas de contratos novos (as rendas em
curso costumam ser mais baixas) e sem custos de compra e venda.
"""
from __future__ import annotations

COST_SHARE = 0.25
YEARS = 5


def _q(p: str) -> int:
    return int(p[:4]) * 4 + int(p[-1]) - 1


def total_return(price: list, price_real: list, rent: list, years: int = YEARS, cost_share: float = COST_SHARE) -> dict | None:
    """price, price_real: [[AAAAQn, valor]]; rent: [[AAAA, €/m²]]. None se faltarem dados."""
    pr = {p: v for p, v in (price_real or []) if v is not None}
    pn = {p: v for p, v in (price or []) if v is not None}
    if not pr or not pn:
        return None
    end = max(pr, key=_q)
    start_i = _q(end) - 4 * years
    start = next((p for p in pr if _q(p) == start_i), None)
    if start is None or start not in pn or end not in pn or pr[start] <= 0:
        return None
    g_real = (pr[end] / pr[start]) ** (1 / years) - 1
    defl_end, defl_start = pn[end] / pr[end], pn[start] / pr[start]
    infl = (defl_end / defl_start) ** (1 / years) - 1
    y0, y1 = int(start[:4]), int(end[:4])
    yields = []
    for y, r in rent or []:
        y = int(str(y)[:4])
        if r is None or not (y0 <= y <= y1):
            continue
        qs = [v for p, v in pn.items() if p.startswith(str(y))]
        if qs:
            yields.append(r * 12 / (sum(qs) / len(qs)))
    if len(yields) < 3:
        return None
    gross = sum(yields) / len(yields)
    net = gross * (1 - cost_share)
    return {"tr5_real": round(g_real + net, 4), "tr5_price_real": round(g_real, 4), "tr5_yield_net": round(net, 4),
            "tr5_infl": round(infl, 4), "tr5_from": start, "tr5_to": end, "tr5_years_rent": len(yields)}
