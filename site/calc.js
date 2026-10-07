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

// Guia: preço máximo de casa que a poupança e o rendimento permitem. A poupança paga a entrada, o IMT, o Imposto do
// Selo e a escritura; o crédito fica limitado (1) pelo LTV do Banco de Portugal (90% habitação própria, 80% outra),
// (2) pelo esforço escolhido (prestação ≤ effort × rendimento líquido) e (3) pela regra do BdP (prestação com a taxa
// +1,5 p.p. ≤ 45% do rendimento). o: { savings, income (líquido/mês), effort, rate (%), years, use, young, ra,
// closing (€), credit (false = sem crédito) }.
function maxPrice(o) {
  const ltv = o.credit === false ? 0 : BDP.ltv[o.use === 'hpp' ? 'hpp' : 'sec'];
  const inc = o.credit === false ? 0 : Math.max(0, o.income || 0);
  const loanInc = inc > 0 ? Math.min((o.effort ?? 0.35) * inc / annuity(1, o.rate, o.years), BDP.dsti * inc / annuity(1, o.rate + BDP.shock, o.years)) : 0;
  const plan = (P) => {
    const loan = Math.min(ltv * P, loanInc), t = buyTaxes(P, loan, o.use, !!o.young, !!o.ra);
    return { price: P, loan, taxes: t.total, cash: P - loan + t.total + (o.closing || 0) };
  };
  if (plan(0).cash > (o.savings || 0)) return { ...plan(0), limit: 'savings' };
  let lo = 0, hi = 2e7;
  for (let i = 0; i < 60; i++) { const mid = (lo + hi) / 2; if (plan(mid).cash <= (o.savings || 0)) lo = mid; else hi = mid; }
  const r = plan(lo);
  return { ...r, pay: annuity(r.loan, o.rate, o.years), limit: r.loan > 0 && r.loan >= loanInc - 1 && loanInc < ltv * lo ? 'income' : 'savings' };
}

// Guia: ordena candidatos por critérios ponderados. Cada critério vira um percentil entre os candidatos (0 = pior,
// 1 = melhor, conforme dir); sem valor conta 0,5 (neutro) e fica em `missing`. score = média ponderada (0–1).
// cands: [{ id, vals: { chave: número | null } }]; crit: [{ key, w, dir: 1 (mais é melhor) | -1 }].
function rankBy(cands, crit) {
  const use = crit.filter((c) => c.w > 0), sorted = {};
  use.forEach((c) => { sorted[c.key] = cands.map((x) => x.vals[c.key]).filter((v) => v != null && Number.isFinite(v)).sort((a, b) => a - b); });
  const lower = (xs, v) => { let lo = 0, hi = xs.length; while (lo < hi) { const m = (lo + hi) >> 1; if (xs[m] < v) lo = m + 1; else hi = m; } return lo; };
  const pct = (c, v) => {
    const xs = sorted[c.key];
    if (v == null || !Number.isFinite(v) || xs.length < 2) return null;
    const below = lower(xs, v), eq = lower(xs, v + Math.abs(v) * 1e-12 + 1e-12) - below;
    const p = (below + (eq - 1) / 2) / (xs.length - 1);
    return c.dir < 0 ? 1 - p : p;
  };
  const W = use.reduce((a, c) => a + c.w, 0) || 1;
  return cands.map((x) => {
    const parts = {}, missing = [];
    let s = 0;
    use.forEach((c) => { const p = pct(c, x.vals[c.key]); parts[c.key] = p; if (p == null) missing.push(c.key); s += c.w * (p == null ? 0.5 : p); });
    return { ...x, score: s / W, parts, missing };
  }).sort((a, b) => b.score - a.score);
}

// ---------- guias de decisão (crédito, senhorio, vender ou manter)
// Plano de pagamentos de um crédito com taxa por mês (rateAt(mês) em %): a prestação é recalculada quando a taxa muda,
// sobre o capital em dívida e o prazo que falta (como num crédito à habitação em Portugal).
function schedule(loan, years, rateAt) {
  const n = Math.round(years * 12);
  let bal = loan, rPrev = null, pay = 0, total = 0, interest = 0, max = 0, first = 0;
  for (let k = 0; k < n && bal > 0.005; k++) {
    const rate = rateAt(k);
    if (rate !== rPrev) { pay = annuity(bal, rate, (n - k) / 12); rPrev = rate; }
    const i = bal * rate / 1200;
    bal = Math.max(0, bal - (pay - i)); total += pay; interest += i;
    if (k === 0) first = pay;
    max = Math.max(max, pay);
  }
  return { first, max, total, interest };
}
// Tipos de taxa face a um choque constante da Euribor (delta, p.p.) a partir da 1.ª revisão (mês 13 na variável, fim do
// prazo fixo na mista). Depois do prazo fixo, a mista passa à taxa variável de hoje + delta. o = { loan, years,
// rates: { f, i, o, p } (%, BCE), fixShort, fixLong (anos de taxa fixa das mistas) }.
const LOAN_PLANS = [
  { key: 'f', label: 'Variável', fixed: () => 1 },
  { key: 'i', label: 'Mista, taxa fixa curta', fixed: (o) => o.fixShort },
  { key: 'o', label: 'Mista, taxa fixa longa', fixed: (o) => o.fixLong },
  { key: 'p', label: 'Fixa todo o prazo', fixed: (o) => o.years },
];
function loanPlans(o, deltas = [-1, 0, 1, 2]) {
  const varNow = o.rates.f;
  const plans = LOAN_PLANS.filter((p) => o.rates[p.key] != null).map((p) => {
    const fixM = Math.min(o.years, p.fixed(o)) * 12;
    const run = (d) => schedule(o.loan, o.years, (k) => (k < fixM ? o.rates[p.key] : Math.max(0, varNow + d)));
    const sc = Object.fromEntries(deltas.map((d) => [d, run(d)]));
    const after = fixM < o.years * 12 ? Object.fromEntries(deltas.map((d) => [d, annuity(1, Math.max(0, varNow + d), (o.years * 12 - fixM) / 12)])) : null;
    return { ...p, rate: o.rates[p.key], fixYears: fixM / 12, sc, run };
  });
  // Euribor média (subida constante, p.p.) que torna o custo total igual ao da variável
  const v = plans.find((p) => p.key === 'f');
  plans.forEach((p) => {
    if (!v || p === v) return;
    const diff = (d) => p.run(d).total - v.run(d).total;
    let lo = -4, hi = 8;
    if (diff(lo) * diff(hi) > 0) { p.breakeven = null; return; }
    for (let i = 0; i < 60; i++) { const mid = (lo + hi) / 2; if (diff(lo) * diff(mid) <= 0) hi = mid; else lo = mid; }
    p.breakeven = (lo + hi) / 2;
  });
  return plans;
}

// Senhorio: rendimento líquido por duração do contrato. o = { rent (€/mês), vacancy (meses/ano), imi (€/ano),
// condo (€/mês), ins (€/ano), maint (fração da renda), growth (fração/ano), years (horizonte), startYear, marginal }.
const LEASES = [{ years: 1, label: 'até 4 anos' }, { years: 5, label: '5 a 9 anos' }, { years: 10, label: '10 anos ou mais' }];
function landlord(o) {
  return LEASES.map((l) => {
    let sum = 0, sumTax = 0;
    const rows = [];
    for (let t = 0; t < o.years; t++) {
      const year = o.startYear + t, rentM = o.rent * (1 + o.growth) ** t, gross = rentM * (12 - o.vacancy);
      const ded = o.imi + o.condo * 12 + o.maint * gross, rate = irsRentRate(rentM, l.years, year);
      const tax = Math.max(0, gross - ded) * rate, net = gross - ded - o.ins - tax;
      rows.push({ year, rentM, gross, rate, tax, net });
      sum += net; sumTax += tax;
    }
    const eng = o.marginal != null ? rows.reduce((a, x) => a + Math.max(0, x.gross - o.imi - o.condo * 12 - o.maint * x.gross) * o.marginal, 0) : null;
    return { ...l, rows, net: sum, tax: sumTax, first: rows[0], englobado: eng };
  });
}

// Vender agora, arrendar ou manter (sem arrendar) e vender daqui a N anos: riqueza no fim, com todo o dinheiro que
// entra e sai a render altRate. Mais-valias de residente: 50% do ganho à taxa marginal, sem os coeficientes de
// desvalorização da moeda (por excesso); isentas na venda de hoje se era habitação própria e se reinveste noutra.
// o = { value, sellCost, balance, rate, yearsLeft, buyCost (preço de compra + despesas), hpp, reinvest, marginal,
//       rent, vacancy, imi, condo, ins, maint, contractYears, priceGrowth, rentGrowth, altRate, horizon, startYear }
function holdOptions(o) {
  const cgt = (sale) => Math.max(0, sale * (1 - o.sellCost) - o.buyCost) * 0.5 * o.marginal;
  const cgt0 = o.hpp && o.reinvest ? 0 : cgt(o.value);
  const now = o.value * (1 - o.sellCost) - o.balance - cgt0;
  const pay = o.balance > 0 ? annuity(o.balance, o.rate, o.yearsLeft) : 0, r = o.rate / 1200, nLeft = o.yearsLeft * 12;
  const path = (rented) => {
    let bal = o.balance, acc = 0;
    const rows = [];
    for (let t = 1; t <= o.horizon; t++) {
      let debt = 0;
      for (let k = 0; k < 12 && bal > 0.005 && (t - 1) * 12 + k < nLeft; k++) { const i = bal * r; debt += pay; bal = Math.max(0, bal - (pay - i)); }
      const rentM = o.rent * (1 + o.rentGrowth) ** (t - 1), year = o.startYear + t - 1;
      const gross = rented ? rentM * (12 - o.vacancy) : 0, maint = rented ? o.maint * gross : 0;
      const irs = rented ? Math.max(0, gross - o.imi - o.condo * 12 - maint) * irsRentRate(rentM, o.contractYears, year) : 0;
      const cf = gross - o.imi - o.condo * 12 - o.ins - maint - irs - debt;
      acc = acc * (1 + o.altRate) + cf;
      rows.push({ t, year, gross, irs, debt, cf });
    }
    const sale = o.value * (1 + o.priceGrowth) ** o.horizon;
    const end = sale * (1 - o.sellCost) - bal - cgt(sale);
    return { rows, sale, cgt: cgt(sale), balance: bal, cash: acc, wealth: acc + end };
  };
  const rent = path(true), keep = path(false);
  return { pay, cgt0, now, sell: { wealth: now * (1 + o.altRate) ** o.horizon }, rent, keep };
}

// Garantia pública para jovens (Decreto-Lei 44/2024, Portaria 236-A/2024): o Estado garante até 15% do valor da
// transação, para o banco poder financiar até 100%; 18 a 35 anos, 1.ª habitação própria e permanente até 450 000 €,
// rendimento até ao 8.º escalão do IRS, sem outra casa em nome próprio; contratos até 31/12/2026 (salvo prorrogação).
const YOUNG_GUARANTEE = { share: 0.15, maxPrice: 450000, until: '2026-12-31', ageMax: 35 };
// Primeira casa: com os apoios (IMT/IS jovem, garantia, prazo de 40 anos) e sem eles (entrada de 10%, 30 anos).
// o = { price, savings, income, rate, closing, ra, guarantee (cumpre as condições), young (até 35 anos) }
function youngPlan(o) {
  const mk = (withAid) => {
    const g = withAid && o.guarantee && o.price <= YOUNG_GUARANTEE.maxPrice;
    const years = withAid && o.young ? BDP.years.young : 30;
    const minDown = g ? 0 : 1 - BDP.ltv.hpp;
    const t0 = buyTaxes(o.price, o.price * (1 - minDown), 'hpp', withAid && o.young, !!o.ra);
    // a poupança paga primeiro impostos e escritura; o resto vai para a entrada (pelo menos a mínima)
    const spare = Math.max(0, (o.savings || 0) - t0.total - (o.closing || 0));
    const down = Math.min(o.price, Math.max(minDown * o.price, spare));
    const loan = o.price - down, t = buyTaxes(o.price, loan, 'hpp', withAid && o.young, !!o.ra);
    const cash = down + t.total + (o.closing || 0), pay = annuity(loan, o.rate, years);
    return { guarantee: g, years, minDown, down, loan, taxes: t, cash, pay, short: Math.max(0, cash - (o.savings || 0)),
      payStress: annuity(loan, o.rate + BDP.shock, years),
      dstiOk: o.income ? annuity(loan, o.rate + BDP.shock, years) <= BDP.dsti * o.income : null };
  };
  return { aid: mk(true), none: mk(false) };
}

// Terreno para construir: valor residual (o método dos promotores). Valor das casas a vender (GDV) − construção −
// projetos/licenças/taxas − comercialização − margem do promotor − financiamento − impostos e escritura do terreno
// = o máximo a pagar pelo terreno. IMT de terreno para construção 6,5% (rústico 5%) + Imposto do Selo 0,8%.
// Financiamento: juros sobre o terreno durante todo o prazo e sobre metade da construção (gasta ao longo da obra).
// o = { abc (m² de construção), eff (área vendável / abc), sale (€/m² vendável), cost (€/m² de construção, com IVA),
//       soft (fração da construção), sales (fração do GDV), margin (fração do GDV), rate (%/ano), years, closing (€),
//       rustic, asking (€, opcional) }
const LAND_TAX = { urban: 0.065, rustic: 0.05, is: 0.008 };
function landResidual(o) {
  const tx = (o.rustic ? LAND_TAX.rustic : LAND_TAX.urban) + LAND_TAX.is, rT = (o.rate / 100) * o.years;
  const gdv = o.abc * o.eff * o.sale, build = o.abc * o.cost, soft = build * o.soft, sales = gdv * o.sales;
  const fixed = build + soft + sales + (o.closing || 0) * (1 + rT) + 0.5 * rT * (build + soft);
  const max = Math.max(0, (gdv - fixed - gdv * o.margin) / ((1 + tx) * (1 + rT)));
  const out = { gdv, build, soft, sales, tx, max, maxPerM2: o.abc ? max / o.abc : null, landShare: gdv ? max / gdv : null };
  if (o.asking != null) {
    const land = o.asking * (1 + tx) * (1 + rT);
    const profit = gdv - fixed - land;
    // preço de venda (€/m²) que dá a margem pretendida pagando o preço pedido
    const needGdv = (build + soft + (o.closing || 0) * (1 + rT) + 0.5 * rT * (build + soft) + land) / (1 - o.sales - o.margin);
    Object.assign(out, { profit, marginAtAsking: gdv ? profit / gdv : null, saleNeeded: o.abc * o.eff ? needGdv / (o.abc * o.eff) : null,
      totalCost: gdv - profit, landTaxes: o.asking * tx });
  }
  return out;
}

if (typeof module !== 'undefined') {
  module.exports = { TAX_YEAR, taxTablesStale, BDP, LIMIT, IMT26, YOUNG_FULL, YOUNG_PART, IS_BUY, IS_LOAN, imtOf, isBuyOf, buyTaxes,
    islands, annuity, qOfMonth, serVal, qAdd, qIdx, at12, serGrowth, TAX_EDGES, shareAbove,
    RENT_COEF, IRS_RENT, irsRentRate, irr, invest, maxPrice, rankBy,
    schedule, LOAN_PLANS, loanPlans, LEASES, landlord, holdOptions, YOUNG_GUARANTEE, youngPlan, LAND_TAX, landResidual };
}
