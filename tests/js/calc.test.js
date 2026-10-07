// Testes das contas do site (site/calc.js). Correm com `node --test tests/js` (no build, a seguir ao pytest).
const test = require('node:test');
const assert = require('node:assert/strict');
const c = require('../../site/calc.js');

const near = (a, b, tol = 0.01) => assert.ok(Math.abs(a - b) <= tol, `${a} ≠ ${b}`);

test('prestação: 100 000 € a 3% em 30 anos', () => {
  near(c.annuity(100000, 3, 30), 421.60);
  near(c.annuity(120000, 0, 10), 1000);
});

test('IMT 2026 habitação própria e permanente: valores de referência', () => {
  near(c.imtOf(100000, 'hpp', false), 0);
  near(c.imtOf(150000, 'hpp', false), 1008.98);
  near(c.imtOf(250000, 'hpp', false), 7042.04);
  near(c.imtOf(400000, 'hpp', false), 18236.65);
  near(c.imtOf(700000, 'hpp', false), 42000);                 // taxa única de 6%
  near(c.imtOf(1200000, 'hpp', false), 90000);                // taxa única de 7,5%
});

test('IMT 2026: sem saltos entre escalões com parcela a abater (o salto para a taxa única existe na lei)', () => {
  for (const use of ['hpp', 'sec']) {
    const t = c.IMT26[use];
    for (let i = 0; i < t.length - 1; i++) {
      if (t[i][2] == null || t[i + 1][2] == null) continue;
      near(c.imtOf(t[i][0], use, false), c.imtOf(t[i][0] + 0.01, use, false), 0.01);
    }
  }
});

test('IMT 2026 2.ª habitação e IMT Jovem', () => {
  near(c.imtOf(250000, 'sec', false), 8105.50);
  near(c.imtOf(300000, 'hpp', true), 0);
  near(c.imtOf(400000, 'hpp', true), 0.08 * (400000 - c.YOUNG_FULL));
  near(c.imtOf(700000, 'hpp', true), c.imtOf(700000, 'hpp', false));   // acima de 660 982 € paga como os outros
  near(c.imtOf(300000, 'sec', true), c.imtOf(300000, 'sec', false));   // o IMT Jovem é só para habitação própria
});

test('Imposto do Selo: 0,8% na compra (isenção jovem até 330 539 €) e 0,6% no crédito', () => {
  const t = c.buyTaxes(250000, 225000, 'hpp', false);
  near(t.isb, 2000); near(t.isl, 1350); near(t.total, t.imt + 3350);
  const j = c.buyTaxes(400000, 360000, 'hpp', true);
  near(j.isb, 0.008 * (400000 - c.YOUNG_FULL)); near(j.isl, 2160);
  near(c.buyTaxes(300000, 0, 'hpp', true).total, 0);
});

test('regras do Banco de Portugal (desde 1/08/2026)', () => {
  assert.equal(c.BDP.dsti, 0.45); assert.equal(c.BDP.shock, 1.5);
  assert.deepEqual(c.BDP.ltv, { hpp: 0.9, sec: 0.8 }); assert.deepEqual(c.BDP.years, { young: 40, other: 35 });
});

test('trimestres e mês da compra', () => {
  assert.equal(c.qOfMonth('2026-04'), '2026Q2'); assert.equal(c.qOfMonth('4'), null); assert.equal(c.qOfMonth('2026-13'), null);
  assert.equal(c.qAdd('2025Q4', 1), '2026Q1'); assert.equal(c.qAdd('2026Q1', -4), '2025Q1');
  assert.equal(c.qIdx('2026Q1') - c.qIdx('2025Q1'), 4);
});

const ser = [['2024Q1', 100], ['2024Q2', 102], ['2024Q3', 104], ['2024Q4', 106], ['2025Q1', 108], ['2025Q2', 110],
  ['2025Q3', 112], ['2025Q4', 114], ['2026Q1', 116]];

test('mediana de 12 meses centrada na compra: média das janelas que acabam 1 e 2 trimestres depois', () => {
  near(c.at12(ser, '2025Q2').v, (112 + 114) / 2);
  assert.equal(c.at12(ser, '2025Q2').proj, undefined);
});

test('compra recente: projeção com a variação anual da tendência', () => {
  const trend = [['2025Q1', 200], ['2026Q1', 220]];                     // +10% num ano
  const r = c.at12(ser, '2026Q2', trend);
  assert.equal(r.proj, '2026Q1'); near(r.gy, 0.10, 1e-9);
  near(r.v, 116 * 1.1 ** ((c.qIdx('2026Q2') + 1.5 - c.qIdx('2026Q1')) / 4), 1e-6);
  assert.equal(c.at12(ser, '2023Q1'), null);                            // antes do início da série
});

test('valorização com índice de 12 meses: base centrada; compra recente sem variação medida', () => {
  const g = c.serGrowth(ser, '2024Q2', true);
  near(g.v0, (104 + 106) / 2); near(g.g, 116 / 105 - 1, 1e-9); assert.ok(g.roll12);
  assert.ok(c.serGrowth(ser, '2025Q4', true).recent);
  const plain = c.serGrowth(ser, '2025Q1');
  near(plain.g, 116 / 108 - 1, 1e-9);
});

test('parte dos agregados com rendimento acima de um valor (escalões do INE)', () => {
  const m = { tax_hh_1: 0.1, tax_hh_2: 0.2, tax_hh_3: 0.2, tax_hh_4: 0.2, tax_hh_5: 0.2, tax_hh_6: 0.1 };
  near(c.shareAbove(m, 0).v, 1, 1e-9);
  near(c.shareAbove(m, 16250).v, 0.1 + 0.2 + 0.1, 1e-9);                // meio do 4.º escalão
  assert.deepEqual(c.shareAbove(m, 40000), { v: 0.1, exact: false });  // escalão de topo é aberto
  assert.equal(c.shareAbove({}, 10000), null);
});

test('tabelas fiscais marcadas como desatualizadas depois do ano a que se referem', () => {
  assert.equal(c.taxTablesStale(new Date(`${c.TAX_YEAR}-12-31T12:00:00`)), false);
  assert.equal(c.taxTablesStale(new Date(`${c.TAX_YEAR + 1}-01-02T12:00:00`)), true);
});

test('IMT 2026 Açores e Madeira: escalões e parcelas publicados (ofício circulado 40129/2026, AT Madeira)', () => {
  const pub = [[132933, 0, 0], [181838, 0.02, 2658.66], [247934, 0.05, 8113.80], [413174, 0.07, 13072.48],
    [826228, 0.08, 17204.22], [1438566, 0.06, null], [Infinity, 0.075, null]];
  assert.equal(c.IMT26.hpp_ra.length, pub.length);
  c.IMT26.hpp_ra.forEach(([lim, r, d], i) => {
    assert.equal(lim, pub[i][0]); assert.equal(r, pub[i][1]);
    if (pub[i][2] == null) assert.equal(d, null); else near(d, pub[i][2], 0.005);
  });
  near(c.imtOf(132000, 'hpp', false, true), 0);
  near(c.imtOf(400000, 'hpp', true, true), 0);                              // IMT Jovem até 413 174 € nas regiões
  near(c.imtOf(250000, 'hpp', false, true), 0.07 * 250000 - 13072.48);
  assert.ok(c.imtOf(250000, 'hpp', false, true) < c.imtOf(250000, 'hpp', false));
});

test('IRS sobre rendas 2026: 10% até 2 300 €/mês até 2029; 25% com reduções por duração', () => {
  assert.equal(c.irsRentRate(1000, 1, 2026), 0.10);
  assert.equal(c.irsRentRate(1000, 1, 2030), 0.25);
  assert.equal(c.irsRentRate(2500, 1, 2026), 0.25);
  assert.equal(c.irsRentRate(2500, 5, 2026), 0.15);
  assert.equal(c.irsRentRate(2500, 12, 2026), 0.10);
  assert.equal(c.RENT_COEF.value, 1.0256);
});

test('TIR: fluxos simples', () => {
  near(c.irr([-100, 110]), 0.10, 1e-6);
  near(c.irr([-1000, 100, 100, 1100]), 0.10, 1e-6);
  assert.equal(c.irr([100, 100]), null);
});

test('investimento: contas do 1.º ano, venda e TIR', () => {
  const o = { price: 250000, down: 0.2, rate: 3.07, years: 30, rent: 1000, rentGrowth: 0.0256, priceGrowth: 0.02, vacancy: 1,
    condo: 30, ins: 150, maint: 0.05, imiRate: 0.003, contractYears: 5, hold: 10, sellCost: 0.05, marginal: 0.35, closing: 1000, startYear: 2026 };
  const r = c.invest(o);
  near(r.cash0, 50000 + c.imtOf(250000, 'sec', false) + 2000 + 1200 + 1000);
  const y1 = r.rows[0];
  near(y1.gross, 11000); near(y1.imi, 750); near(y1.irs, (11000 - 750 - 360 - 550) * 0.10);
  near(y1.debt, r.pay * 12, 0.05);
  near(y1.cf, 11000 - 750 - 360 - 550 - 150 - y1.irs - y1.debt, 0.05);
  near(r.sale, 250000 * 1.02 ** 10, 0.01);
  near(r.cgt, Math.max(0, r.gain) * 0.5 * 0.35, 0.01);
  // a TIR anula o valor atual dos fluxos
  near(r.flows.reduce((a, f, t) => a + f / (1 + r.irr) ** t, 0), 0, 0.5);
  // sem crédito: a dívida é zero e a rentabilidade sobre o capital é a líquida da casa
  const cashOnly = c.invest({ ...o, down: 1 });
  assert.equal(cashOnly.rows[0].debt, 0); assert.ok(cashOnly.irr > 0);
  // mais renda -> mais TIR; mais juros -> menos TIR
  assert.ok(c.invest({ ...o, rent: 1200 }).irr > r.irr);
  assert.ok(c.invest({ ...o, rate: 5 }).irr < r.irr);
});

test('maxPrice: poupança paga entrada e impostos; crédito limitado pelo LTV e pelo rendimento', () => {
  const base = { savings: 50000, income: 3000, effort: 0.35, rate: 3.5, years: 30, use: 'hpp', young: false, ra: false, closing: 1000 };
  const r = c.maxPrice(base);
  assert.ok(Math.abs(r.cash - 50000) < 1, 'gasta a poupança toda');
  assert.ok(r.loan <= 0.9 * r.price + 1e-6);
  assert.ok(c.annuity(r.loan, 3.5, 30) <= 0.35 * 3000 + 1e-6);
  assert.ok(c.annuity(r.loan, 3.5 + c.BDP.shock, 30) <= c.BDP.dsti * 3000 + 1e-6);
  // com rendimento baixo, o limite passa a ser o rendimento e o preço desce
  const low = c.maxPrice({ ...base, income: 1000 });
  assert.equal(low.limit, 'income');
  assert.ok(low.price < r.price);
  // sem crédito: só a poupança
  const cash = c.maxPrice({ ...base, credit: false });
  assert.equal(cash.loan, 0);
  assert.ok(cash.price < 50000 && cash.price > 40000);
  // mais poupança nunca baixa o preço
  assert.ok(c.maxPrice({ ...base, savings: 80000 }).price > r.price);
});

test('rankBy: percentis ponderados, direção e valores em falta neutros', () => {
  const cands = [
    { id: 'a', vals: { y: 0.06, risk: 30 } },
    { id: 'b', vals: { y: 0.04, risk: 10 } },
    { id: 'c', vals: { y: 0.05, risk: null } },
  ];
  const r1 = c.rankBy(cands, [{ key: 'y', w: 1, dir: 1 }]);
  assert.deepEqual(r1.map((x) => x.id), ['a', 'c', 'b']);
  const r2 = c.rankBy(cands, [{ key: 'y', w: 1, dir: 1 }, { key: 'risk', w: 3, dir: -1 }]);
  assert.equal(r2[0].id, 'b');
  assert.deepEqual(r2.find((x) => x.id === 'c').missing, ['risk']);
  assert.ok(r2.every((x) => x.score >= 0 && x.score <= 1));
  const r3 = c.rankBy(cands, [{ key: 'y', w: 0, dir: 1 }]);
  assert.ok(r3.every((x) => x.score === 0.5 || Number.isFinite(x.score)));
});

test('schedule: taxa constante = anuidade; subida da taxa sobe a prestação', () => {
  const s = c.schedule(200000, 30, () => 3);
  assert.ok(Math.abs(s.first - c.annuity(200000, 3, 30)) < 1e-6);
  assert.ok(Math.abs(s.total - s.first * 360) < 1);
  const up = c.schedule(200000, 30, (k) => (k < 12 ? 3 : 5));
  assert.ok(up.max > s.first && up.total > s.total);
});

test('loanPlans: fixa não reage à Euribor; variável sim; ponto de equilíbrio coerente', () => {
  const o = { loan: 200000, years: 30, rates: { f: 3.28, i: 2.88, o: 4.93, p: 3.68 }, fixShort: 5, fixLong: 10 };
  const P = Object.fromEntries(c.loanPlans(o).map((p) => [p.key, p]));
  assert.equal(P.p.sc[2].total, P.p.sc[0].total);                 // fixa todo o prazo
  assert.ok(P.f.sc[2].total > P.f.sc[0].total && P.f.sc[2].max > P.f.sc[0].max);
  assert.ok(P.i.sc[0].first < P.f.sc[0].first);                   // mista curta mais barata hoje
  // a fixa (3,68%) só compensa face à variável (3,28%) se a Euribor subir em média: equilíbrio positivo
  assert.ok(P.p.breakeven > 0 && P.p.breakeven < 2);
  const at = P.p.run(P.p.breakeven).total, vt = P.f.run(P.p.breakeven).total;
  assert.ok(Math.abs(at - vt) < 5);
});

test('landlord: rendas até 2300 € a 10% até 2029; depois depende da duração do contrato', () => {
  const L = c.landlord({ rent: 1000, vacancy: 0, imi: 300, condo: 30, ins: 150, maint: 0.05, growth: 0, years: 6, startYear: 2026, marginal: null });
  const short = L.find((x) => x.years === 1), long = L.find((x) => x.years === 10);
  assert.equal(short.rows[0].rate, 0.10);
  assert.equal(short.rows[4].rate, 0.25);       // 2030
  assert.equal(long.rows[4].rate, 0.10);
  assert.ok(long.net > short.net);
  const big = c.landlord({ rent: 3000, vacancy: 0, imi: 0, condo: 0, ins: 0, maint: 0, growth: 0, years: 1, startYear: 2026, marginal: 0.2 });
  assert.equal(big[0].rows[0].rate, 0.25);
  assert.ok(big[0].englobado < big[0].tax);     // taxa marginal mais baixa: englobar paga menos
});

test('holdOptions: sem crescimento nem rendas, vender já ganha a manter vazia; isenção de mais-valias', () => {
  const base = { value: 300000, sellCost: 0.05, balance: 100000, rate: 3, yearsLeft: 20, buyCost: 150000, hpp: false, reinvest: false,
    marginal: 0.35, rent: 1000, vacancy: 1, imi: 400, condo: 40, ins: 200, maint: 0.05, contractYears: 1, priceGrowth: 0, rentGrowth: 0,
    altRate: 0.02, horizon: 10, startYear: 2026 };
  const r = c.holdOptions(base);
  assert.ok(r.cgt0 > 0 && Math.abs(r.cgt0 - (300000 * 0.95 - 150000) * 0.5 * 0.35) < 1e-6);
  assert.ok(r.sell.wealth > r.keep.wealth);
  assert.ok(r.rent.wealth > r.keep.wealth);
  assert.equal(c.holdOptions({ ...base, hpp: true, reinvest: true }).cgt0, 0);
  assert.ok(c.holdOptions({ ...base, priceGrowth: 0.05 }).rent.wealth > r.rent.wealth);
});

test('youngPlan: garantia dispensa a entrada até 450 mil; isenção de IMT/IS até 330 539 €', () => {
  const base = { price: 250000, savings: 5000, income: 2800, rate: 3.1, closing: 1000, ra: false, guarantee: true, young: true };
  const r = c.youngPlan(base);
  assert.equal(r.aid.guarantee, true);
  assert.equal(r.aid.taxes.imt, 0); assert.equal(r.aid.taxes.isb, 0);
  assert.ok(r.aid.taxes.isl > 0);                         // o Imposto do Selo do crédito paga-se na mesma
  assert.equal(r.aid.years, 40);
  assert.ok(r.aid.cash < r.none.cash && r.none.short > 0);
  assert.ok(r.none.down >= 25000 - 1e-6);                  // sem garantia: entrada de 10%
  const big = c.youngPlan({ ...base, price: 500000 });
  assert.equal(big.aid.guarantee, false);                  // acima de 450 000 €: sem garantia
  const noG = c.youngPlan({ ...base, guarantee: false });
  assert.ok(noG.aid.down >= 25000 - 1e-6 && noG.aid.taxes.imt === 0);
});

test('landResidual: pagar o máximo dá exatamente a margem pretendida; margem e preço necessário coerentes', () => {
  const o = { abc: 600, eff: 0.85, sale: 3500, cost: 1500, soft: 0.12, sales: 0.05, margin: 0.15, rate: 5, years: 2.5, closing: 1000, rustic: false };
  const r = c.landResidual(o);
  assert.ok(r.max > 0 && r.landShare > 0 && r.landShare < 0.5);
  const atMax = c.landResidual({ ...o, asking: r.max });
  assert.ok(Math.abs(atMax.marginAtAsking - 0.15) < 1e-9);
  assert.ok(Math.abs(atMax.saleNeeded - 3500) < 1e-6);            // no máximo, o preço necessário é o de mercado
  const dear = c.landResidual({ ...o, asking: r.max * 1.5 });
  assert.ok(dear.marginAtAsking < 0.15 && dear.saleNeeded > 3500);
  assert.ok(c.landResidual({ ...o, rustic: true }).max > r.max);  // IMT mais baixo
  assert.equal(c.landResidual({ ...o, sale: 1000 }).max, 0);       // não paga a construção: o terreno não vale nada para construir
});

test('parseLL: formatos do Google Maps, vírgula decimal, ordem trocada e fora de Portugal', () => {
  assert.deepEqual(c.parseLL('38.83092, -9.16851'), [38.83092, -9.16851]);
  assert.deepEqual(c.parseLL('38,7223 -9,1393'), [38.7223, -9.1393]);
  assert.deepEqual(c.parseLL('-9.1393, 38.7223'), [38.7223, -9.1393]);
  assert.deepEqual(c.parseLL('32.65, -16.91'), [32.65, -16.91]);           // Funchal
  assert.equal(c.parseLL('48.85, 2.35'), null);                             // Paris
  assert.equal(c.parseLL('x'), null);
});
