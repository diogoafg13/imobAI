/* Contas puras do painel (sem DOM): carregado antes do app.js e testado em Node (tests/js). Tudo o que muda por
   lei ou regra anual fica aqui, com o ano a que se refere (TAX_YEAR): ver o aviso no site e no build. */
const TAX_YEAR = 2026;           // ano das tabelas de IMT/Imposto do Selo e das regras do Banco de Portugal abaixo
const taxTablesStale = (now = new Date()) => now.getFullYear() > TAX_YEAR;

// Banco de Portugal (Recomendação macroprudencial, contratos avaliados desde 1/08/2026): prestação calculada com a
// taxa +1,5 p.p. até 45% do rendimento líquido (antes 50%; cada banco pode passar até 10% do crédito de cada semestre);
// financiamento até 90% do valor na habitação própria e permanente e 80% nas outras finalidades; prazo até 40 anos
// até aos 35 anos de idade e 35 anos acima disso. Na escala de cada rendimento do painel, os 45% do líquido são
// ~36% do salário bruto (IRS e Segurança Social ~20%) e ~40% do rendimento após IRS (falta a Segurança Social, ~11%).
const BDP = { dsti: 0.45, shock: 1.5, ltv: { hpp: 0.9, sec: 0.8 }, years: { young: 40, other: 35 } };
const LIMIT = { wage: 0.36, irs: 0.40 };
// IMT e Imposto do Selo na compra, 2026 (continente; OE 2026, Lei 73-A/2025: escalões +2%). [limite, taxa, parcela
// a abater]; parcela null = taxa única sobre o valor. Jovens até 35 anos (1.ª habitação própria e permanente, não
// dependentes): IMT e Imposto do Selo isentos até 330 539 €; até 660 982 € pagam só sobre o excesso.
const IMT26 = {
  hpp: [[106346, 0, 0], [145470, 0.02, 2126.92], [198347, 0.05, 6491.02], [330539, 0.07, 10457.96], [660982, 0.08, 13763.35], [1150853, 0.06, null], [Infinity, 0.075, null]],
  sec: [[106346, 0.01, 0], [145470, 0.02, 1063.46], [198347, 0.05, 5427.56], [330539, 0.07, 9394.50], [633931, 0.08, 12699.89], [1150853, 0.06, null], [Infinity, 0.075, null]],
};
const YOUNG_FULL = 330539, YOUNG_PART = 660982, IS_BUY = 0.008, IS_LOAN = 0.006;
// Açores e Madeira: limites dos escalões 25% acima dos do continente (arredondados ao euro), mesmas taxas; as
// parcelas a abater saem da continuidade entre escalões (para a habitação própria coincidem com as publicadas no
// ofício circulado 40129/2026 da AT da Madeira, ver tests/js). Os limites do IMT Jovem sobem na mesma proporção.
const RA = 1.25;
function regional(table) {
  const out = [];
  for (const [lim, r, ded] of table) {
    const L = Number.isFinite(lim) ? Math.round(lim * RA) : Infinity;
    if (ded == null) { out.push([L, r, null]); continue; }
    const prev = out[out.length - 1];
    // continuidade: no limite anterior, r·x − d = r_ant·x − d_ant
    const d = prev ? Math.round((r * prev[0] - (prev[1] * prev[0] - prev[2])) * 100) / 100 : 0;
    out.push([L, r, d]);
  }
  return out;
}
IMT26.hpp_ra = regional(IMT26.hpp);
IMT26.sec_ra = regional(IMT26.sec);
const youngLim = (ra) => (ra ? [Math.round(YOUNG_FULL * RA), Math.round(YOUNG_PART * RA)] : [YOUNG_FULL, YOUNG_PART]);
function imtOf(v, use, young, ra = false) {
  const [yf, yp] = youngLim(ra);
  if (use === 'hpp' && young && v <= yp) return v <= yf ? 0 : 0.08 * (v - yf);
  const [, r, ded] = IMT26[(use === 'sec' ? 'sec' : 'hpp') + (ra ? '_ra' : '')].find(([lim]) => v <= lim);
  return ded == null ? r * v : Math.max(0, r * v - ded);
}
function isBuyOf(v, use, young, ra = false) {
  const [yf, yp] = youngLim(ra);
  if (use === 'hpp' && young && v <= yp) return v <= yf ? 0 : IS_BUY * (v - yf);
  return IS_BUY * v;
}
// impostos de uma compra: IMT + Imposto do Selo da aquisição (0,8%) + do crédito (0,6%, prazo de 5 anos ou mais);
// ra = imóvel nos Açores ou na Madeira
function buyTaxes(v, loan, use, young, ra = false) {
  const imt = imtOf(v, use, young, ra), isb = isBuyOf(v, use, young, ra), isl = loan > 0 ? IS_LOAN * loan : 0;
  return { imt, isb, isl, total: imt + isb + isl };
}
const islands = (dico) => /^[34]/.test(String(dico || ''));

function annuity(loan, ratePct, years) {
  const r = ratePct / 100 / 12, n = years * 12;
  return Math.abs(r) < 1e-12 ? loan / n : (loan * r) / (1 - (1 + r) ** -n);
}

const qOfMonth = (ym) => {
  const mt = /^(\d{4})-(\d{2})$/.exec(String(ym || ''));
  if (!mt) return null;
  const y = +mt[1], m = +mt[2];
  return y >= 2000 && m >= 1 && m <= 12 ? `${y}Q${Math.floor((m - 1) / 3) + 1}` : null;
};

function serVal(ser, q) { const r = (ser || []).find((x) => x[0] === q); return r ? r[1] : null; }
// As medianas de venda do INE (concelho, freguesia, tipologia) são das vendas dos últimos 12 meses: o valor do
// trimestre Q reflete o mercado de ~1,5 trimestres antes. Para o mercado do trimestre q usa-se a média das
// janelas que acabam em q+1 e q+2 (centradas em q); se ainda não saíram, projeta-se o último valor com a
// variação anual da série `trend`: a mediana nacional. Testado com o histórico (README): erra menos do que a
// tendência do próprio concelho (ruidosa nos pequenos) e do que não projetar (que ficava ~4% abaixo).
const qAdd = (q, k) => { const i = +q.slice(0, 4) * 4 + +q.slice(-1) - 1 + k; return `${Math.floor(i / 4)}Q${(i % 4) + 1}`; };
const qIdx = (q) => +q.slice(0, 4) * 4 + +q.slice(-1) - 1;
function at12(ser, q, trend) {
  if (!ser || !ser.length || q < ser[0][0]) return null;
  const a = serVal(ser, qAdd(q, 1)), b = serVal(ser, qAdd(q, 2));
  if (a && b) return { v: (a + b) / 2 };
  const last = ser[ser.length - 1];
  if (q < qAdd(last[0], -1)) { const x = serVal(ser, q); return x ? { v: x } : null; }   // falha no meio da série
  const tr = trend && trend.length ? trend : ser, tl = tr[tr.length - 1], tp = serVal(tr, qAdd(tl[0], -4));
  const gq = tp ? (tl[1] / tp) ** 0.25 : 1;
  return { v: last[1] * gq ** (qIdx(q) + 1.5 - qIdx(last[0])), proj: last[0], gy: tp ? tl[1] / tp - 1 : null };
}
function serGrowth(ser, q0, roll12 = false) {
  if (!ser || !ser.length) return null;
  const first = ser[0][0], last = ser[ser.length - 1];
  if (q0 < first) return null;
  if (roll12) {
    const b = at12(ser, q0);
    if (!b || b.proj) return { g: 0, from: q0, to: last[0], recent: true };
    return { g: last[1] / b.v - 1, from: q0, to: last[0], v0: b.v, roll12: true };
  }
  if (q0 >= last[0]) return { g: 0, from: q0, to: last[0], recent: true };
  const v0 = serVal(ser, q0);
  return v0 ? { g: last[1] / v0 - 1, from: q0, to: last[0], v0 } : null;
}

// Quem consegue pagar esta renda? Perfis com rendimentos locais e parte dos agregados fiscais do concelho com
// rendimento bruto suficiente (escalões do INE, interpolação linear dentro de cada escalão).
const TAX_EDGES = [0, 5000, 10000, 13500, 19000, 32500];
function shareAbove(m, annual) {
  const sh = [1, 2, 3, 4, 5, 6].map((i) => m[`tax_hh_${i}`]);
  if (sh.some((x) => x == null)) return null;
  let tot = 0;
  for (let i = 0; i < 5; i++) {
    const a = TAX_EDGES[i], b = TAX_EDGES[i + 1];
    tot += annual <= a ? sh[i] : annual >= b ? 0 : sh[i] * (b - annual) / (b - a);
  }
  // escalão de topo (32 500 € ou mais) é aberto: abaixo do limiar conta inteiro; acima, só sabemos o máximo
  return annual <= 32500 ? { v: tot + sh[5], exact: true } : { v: sh[5], exact: false };
}

// ---------- arrendar e investir (regras de 2026; ver TAX_YEAR)
// Coeficiente de atualização das rendas para 2027 (INE, Aviso n.º 24199/2026/2, DR de 1/10/2026): o máximo que o
// senhorio pode aplicar a uma renda em curso no ano seguinte, se o contrato não disser outra coisa.
const RENT_COEF = { year: 2027, value: 1.0256 };
// IRS sobre rendas de habitação (taxa autónoma): 25%; com contrato de 5 a 10 anos −10 p.p., de 10 ou mais −15 p.p.;
// rendas até 2 300 €/mês: 10% até 31/12/2029 (Decreto-Lei 97/2026). Incide sobre a renda menos IMI, condomínio e
// conservação; os juros do crédito não se deduzem.
const IRS_RENT = { base: 0.25, cut5: 0.10, cut10: 0.15, moderate: 0.10, moderateMax: 2300, moderateUntil: 2029 };
function irsRentRate(rentMonthly, contractYears = 1, year = TAX_YEAR) {
  if (rentMonthly <= IRS_RENT.moderateMax && year <= IRS_RENT.moderateUntil) return IRS_RENT.moderate;
  return IRS_RENT.base - (contractYears >= 10 ? IRS_RENT.cut10 : contractYears >= 5 ? IRS_RENT.cut5 : 0);
}
// taxa interna de rentabilidade de fluxos anuais (o primeiro, negativo, é o investimento); bisseção
function irr(flows) {
  const npv = (r) => flows.reduce((a, f, t) => a + f / (1 + r) ** t, 0);
  let lo = -0.99, hi = 1;
  if (npv(lo) * npv(hi) > 0) return null;
  for (let i = 0; i < 200; i++) { const mid = (lo + hi) / 2; if (npv(lo) * npv(mid) <= 0) hi = mid; else lo = mid; }
  return (lo + hi) / 2;
}
// Investimento para arrendar: fluxos anuais, venda no fim do prazo e TIR.
// o = { price, down (fração), rate (%), years (crédito), rent (€/mês no 1.º ano), rentGrowth, priceGrowth (frações/ano),
//       vacancy (meses/ano), condo (€/mês), ins (€/ano), maint (fração da renda), imiRate, vpt (opcional),
//       contractYears, hold (anos), sellCost (fração do preço de venda), marginal (taxa marginal de IRS, mais-valias),
//       closing (€: escritura, registos), ra (Açores/Madeira), startYear }
function invest(o) {
  const loan = o.price * (1 - o.down), tax = buyTaxes(o.price, loan, 'sec', false, !!o.ra);
  const cash0 = o.price - loan + tax.total + (o.closing || 0);
  const r = o.rate / 100 / 12, n = o.years * 12, pay = loan > 0 ? annuity(loan, o.rate, o.years) : 0;
  let bal = loan;
  const rows = [];
  for (let t = 1; t <= o.hold; t++) {
    const rentM = o.rent * (1 + o.rentGrowth) ** (t - 1), year = (o.startYear || TAX_YEAR) + t - 1;
    const gross = rentM * (12 - o.vacancy);
    const imi = (o.vpt || o.price) * o.imiRate, condo = o.condo * 12, maint = o.maint * gross, ins = o.ins;
    const deductible = imi + condo + maint;            // o seguro e os juros não se deduzem nas rendas
    const irs = Math.max(0, gross - deductible) * irsRentRate(rentM, o.contractYears, year);
    let interest = 0, debt = 0;
    for (let k = 0; k < 12 && bal > 0.005 && (t - 1) * 12 + k < n; k++) {
      const i = bal * r; interest += i; debt += pay; bal = Math.max(0, bal - (pay - i));
    }
    const cf = gross - imi - condo - maint - ins - irs - debt;
    rows.push({ t, year, rentM, gross, imi, condo, maint, ins, irs, irsRate: irsRentRate(rentM, o.contractYears, year), debt, interest, cf, balance: bal });
  }
  const sale = o.price * (1 + o.priceGrowth) ** o.hold, sellCost = sale * o.sellCost;
  // mais-valia de residente: 50% do ganho somado ao rendimento (taxa marginal); sem os coeficientes de
  // desvalorização da moeda (que baixam o imposto em detenções longas) — conta por excesso
  const gain = sale - sellCost - (o.price + tax.imt + tax.isb + (o.closing || 0));
  const cgt = Math.max(0, gain) * 0.5 * o.marginal;
  const netSale = sale - sellCost - bal - cgt;
  const flows = [-cash0, ...rows.map((x, i) => x.cf + (i === rows.length - 1 ? netSale : 0))];
  const y1 = rows[0];
  const noi1 = y1.gross - y1.imi - y1.condo - y1.maint - y1.ins - y1.irs;
  return { loan, tax, cash0, pay, rows, sale, sellCost, gain, cgt, netSale, flows, irr: irr(flows),
    grossYield: (o.rent * 12) / o.price, netYield: noi1 / (o.price + tax.total + (o.closing || 0)),
    cashOnCash: y1.cf / cash0, totalProfit: flows.reduce((a, b) => a + b, 0) };
}

if (typeof module !== 'undefined') {
  module.exports = { TAX_YEAR, taxTablesStale, BDP, LIMIT, IMT26, YOUNG_FULL, YOUNG_PART, IS_BUY, IS_LOAN, imtOf, isBuyOf, buyTaxes,
    islands, annuity, qOfMonth, serVal, qAdd, qIdx, at12, serGrowth, TAX_EDGES, shareAbove,
    RENT_COEF, IRS_RENT, irsRentRate, irr, invest };
}
