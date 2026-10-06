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
