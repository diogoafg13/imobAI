(() => {
'use strict';
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fmt = {
  pct: (v, d = 1) => (v == null ? '—' : (v * 100).toFixed(d).replace('.', ',') + '%'),
  eur: (v) => (v == null ? '—' : Math.round(v).toLocaleString('pt-PT') + ' €'),
  eur2: (v) => (v == null ? '—' : v.toFixed(2).replace('.', ',') + ' €'),
  n: (v, d = 0) => (v == null ? '—' : v.toFixed(d).replace('.', ',')),
};
const BAND_LABEL = { green: 'Baixo', amber: 'Moderado', red: 'Elevado' };
const pill = (band, txt) => `<span class="pill ${band || 'none'}">${esc(txt ?? BAND_LABEL[band] ?? 'n/d')}</span>`;

let MUNIS = [], BY = {}, NAT = null, META = null, GEO = null, MAP = null;
let sortKey = 'score_overall', sortDir = -1, selected = null;
const compare = [];
const charts = {};

async function j(path) {
  const r = await fetch(path, { cache: 'no-cache' });
  if (!r.ok) throw new Error(path + ' ' + r.status);
  return r.json();
}

// ---------- paleta / escalas
const PAL = ['#2e9e6b', '#8bc16a', '#e0c34b', '#e08a3b', '#d1493f'];
const SEQ = ['#d7ecf3', '#9fd0e0', '#5bb3d0', '#2b86a8', '#155a78'];
const METRICS = {
  score: { prop: 'score', pal: PAL, fixed: [0, 100], f: (v) => fmt.n(v), label: 'Score' },
  price: { prop: 'price', pal: SEQ, f: fmt.eur, label: '€/m²' },
  yield: { prop: 'yield', pal: SEQ, f: (v) => fmt.pct(v, 2), label: 'Rendibilidade bruta' },
  g1y: { prop: 'g1y', pal: SEQ, f: (v) => fmt.pct(v), label: 'Var. 12m' },
};
function quantile(sorted, q) { const i = (sorted.length - 1) * q, lo = Math.floor(i), hi = Math.ceil(i); return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo); }
function domain(m) {
  if (m.fixed) return m.fixed;
  const v = MUNIS.map((x) => ({ price: x.price, yield: x.gross_yield, g1y: x.price_growth_1y })[m.prop]).filter((x) => x != null).sort((a, b) => a - b);
  if (v.length < 2) return [0, 1];
  const lo = quantile(v, 0.05), hi = quantile(v, 0.95);
  return lo === hi ? [lo, lo + 1] : [lo, hi];
}
function stops(m) {
  const [lo, hi] = domain(m);
  return m.pal.flatMap((c, i) => [lo + ((hi - lo) * i) / (m.pal.length - 1), c]);
}

// ---------- nacional
function renderNational() {
  const n = NAT, ov = n.overall;
  $('#nat-score').innerHTML = ov == null
    ? '<div class="muted">Sem dados macro suficientes</div>'
    : `<div class="num">${Math.round(ov)}</div><div>${pill(n.band)}</div><div class="muted">score macro (0–100)</div>`;
  const li = Object.values(n.components).map((c) => {
    const isPct = /anual|Crescimento/.test(c.label);
    const val = c.value == null ? '—' : isPct ? fmt.pct(c.value) : fmt.n(c.value, 2);
    const band = c.score == null ? null : c.score < 40 ? 'green' : c.score < 70 ? 'amber' : 'red';
    return `<li><span>${esc(c.label)}</span><span>${val} ${pill(band, c.score == null ? 'n/d' : Math.round(c.score))}</span></li>`;
  });
  $('#nat-components').innerHTML = li.join('') || '<li class="muted">Sem componentes disponíveis</li>';
  lineChart('chart-hpi', 'Índice de preços da habitação', [{ name: 'HPI', data: n.series.hpi }]);
  renderEuribor();
}

function renderEuribor() {
  const sel = $('#euribor-sel').value, S = NAT.series;
  const all = [['3M', S.euribor_3m], ['6M', S.euribor_6m], ['12M', S.euribor_12m]];
  const pick = sel === 'all' ? all : all.filter(([n]) => n.toLowerCase() === sel);
  const series = pick.map(([name, data]) => ({ name, data: data || [] })).filter((x) => x.data.length);
  lineChart('chart-euribor', sel === 'all' ? 'Euribor (%)' : `Euribor ${sel.toUpperCase()} (%)`, series);
}

function lineChart(id, title, series, opts = {}) {
  const el = document.getElementById(id);
  if (charts[id]) { charts[id].dispose(); delete charts[id]; }
  el.innerHTML = '';
  if (!series.some((s) => s.data && s.data.length)) { el.innerHTML = `<p class="muted">${esc(title)}: sem dados</p>`; return; }
  charts[id] ||= echarts.init(el);
  const txt = css('--muted'), line = css('--line');
  charts[id].setOption({
    animation: false, color: [css('--accent'), '#e08a3b', '#8bc16a', '#b07cc6'],
    title: { text: title, textStyle: { fontSize: 12, color: txt, fontWeight: 500 } },
    grid: { left: 46, right: opts.dual ? 46 : 12, top: 34, bottom: 24 },
    tooltip: { trigger: 'axis' }, legend: series.length > 1 ? { top: 0, right: 0, textStyle: { color: txt } } : undefined,
    xAxis: { type: 'category', data: [...new Set(series.flatMap((s) => s.data.map((d) => d[0])))].sort(), axisLabel: { color: txt }, axisLine: { lineStyle: { color: line } } },
    yAxis: [{ type: 'value', scale: true, axisLabel: { color: txt }, splitLine: { lineStyle: { color: line } } }].concat(opts.dual ? [{ type: 'value', scale: true, axisLabel: { color: txt }, splitLine: { show: false } }] : []),
    series: series.map((s, i) => ({ name: s.name, type: 'line', showSymbol: false, smooth: false, yAxisIndex: s.axis || 0, connectNulls: true, data: s.data })),
  }, true);
}

// ---------- mapa
function metricExpr(m) {
  return ['case', ['==', ['get', m.prop], null], css('--none'), ['interpolate', ['linear'], ['to-number', ['get', m.prop]], ...stops(m)]];
}
function renderLegend(m) {
  const [lo, hi] = domain(m);
  $('#legend').innerHTML = `<span>${m.f(lo)}</span><span class="bar" style="background:linear-gradient(90deg,${m.pal.join(',')})"></span><span>${m.f(hi)}</span><span>· ${esc(m.label)}</span>`;
}
function initMap() {
  if (!GEO) { $('#mapsec').insertAdjacentHTML('beforeend', '<p class="muted">Geometrias indisponíveis nesta build; veja o ranking abaixo.</p>'); $('#map').hidden = true; return; }
  const m = METRICS[$('#metric').value];
  MAP = new maplibregl.Map({ container: 'map', style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': css('--bg') } }] }, attributionControl: false });
  MAP.addControl(new maplibregl.NavigationControl({ showCompass: false }));
  MAP.on('load', () => {
    MAP.addSource('c', { type: 'geojson', data: GEO, promoteId: 'dico' });
    MAP.addLayer({ id: 'fill', type: 'fill', source: 'c', paint: { 'fill-color': metricExpr(m), 'fill-opacity': 0.9 } });
    MAP.addLayer({ id: 'line', type: 'line', source: 'c', paint: { 'line-color': css('--card'), 'line-width': ['case', ['boolean', ['feature-state', 'sel'], false], 2.5, 0.5] } });
    const b = new maplibregl.LngLatBounds();
    const ext = (c) => (typeof c[0] === 'number' ? b.extend(c) : c.forEach(ext));
    GEO.features.forEach((f) => ext(f.geometry.coordinates));
    MAP.fitBounds(b, { padding: 12, animate: false });
    MAP.on('click', 'fill', (e) => e.features[0] && select(e.features[0].properties.dico));
    MAP.on('mouseenter', 'fill', () => (MAP.getCanvas().style.cursor = 'pointer'));
    MAP.on('mouseleave', 'fill', () => (MAP.getCanvas().style.cursor = ''));
  });
  renderLegend(m);
}
function updateMetric() {
  const m = METRICS[$('#metric').value];
  if (MAP && MAP.getLayer('fill')) MAP.setPaintProperty('fill', 'fill-color', metricExpr(m));
  renderLegend(m);
}

// ---------- detalhe / comparação
function select(dico, scroll = true) {
  const m = BY[dico]; if (!m) return;
  if (MAP && MAP.getSource('c')) {
    if (selected) MAP.setFeatureState({ source: 'c', id: selected }, { sel: false });
    MAP.setFeatureState({ source: 'c', id: dico }, { sel: true });
  }
  selected = dico;
  $('#detail').hidden = false;
  $('#d-title').innerHTML = `${esc(m.name)} ${pill(m.band)}${m.volatile ? ' ' + pill(null, '⚠ dados voláteis') : ''}`;
  const st = [
    ['Preço mediano', fmt.eur(m.price) + '/m²'], ['Var. 12m', fmt.pct(m.price_growth_1y)], ['Var. 3 anos', fmt.pct(m.price_growth_3y)],
    ['Renda (novos contratos)', m.rent == null ? '—' : fmt.eur2(m.rent) + '/m²'], ['Rendibilidade bruta', fmt.pct(m.gross_yield, 2)],
    ['Preço/renda (anos)', fmt.n(m.price_to_rent_years, 1)], ['Score valorização', fmt.n(m.score_valuation)], ['Score global', fmt.n(m.score_overall)],
  ];
  $('#d-stats').innerHTML = st.map(([k, v]) => `<div class="stat"><span class="muted">${k}</span><b>${v}</b></div>`).join('');
  const s = [{ name: 'Preço €/m²', data: m.series.price }];
  const q4 = (p) => (p.length === 4 ? p + 'Q4' : p);
  if (m.series.rent.length) s.push({ name: 'Renda €/m²', data: m.series.rent.map(([p, v]) => [q4(p), v]), axis: 1 });
  $('#chart-detail').innerHTML = ''; delete charts['chart-detail'];
  lineChart('chart-detail', 'Evolução', s, { dual: s.length > 1 });
  $('#d-compare').textContent = compare.includes(dico) ? 'Remover da comparação' : 'Comparar';
  if (scroll) $('#detail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function renderCompare() {
  $('#compare').hidden = compare.length === 0;
  if (!compare.length) return;
  $('#c-chips').innerHTML = compare.map((d) => `<span class="chip" data-d="${esc(d)}">${esc(BY[d].name)} ✕</span>`).join('');
  $('#c-hint').textContent = compare.length < 2
    ? 'Escolhe outro concelho (no mapa ou no ranking) e clica em "Comparar" para o juntar. Máximo 4.'
    : compare.length >= 4 ? 'Máximo de 4 concelhos atingido. Clica num concelho acima para o remover.' : 'Podes juntar mais concelhos (máximo 4).';
  const has = (d) => new Map(BY[d].series.price);
  const maps = compare.map((d) => [d, has(d)]);
  const periods = [...new Set(compare.flatMap((d) => BY[d].series.price.map((p) => p[0])))].sort();
  const base = periods.find((p) => maps.every(([, m]) => m.has(p)));   // 1.º período com dados em todos
  const series = maps.map(([d, m]) => ({
    name: BY[d].name,
    data: periods.filter((p) => base && p >= base).map((p) => [p, m.has(p) ? +((m.get(p) / m.get(base)) * 100).toFixed(2) : null]),
  }));
  $('#chart-compare').innerHTML = ''; delete charts['chart-compare'];
  lineChart('chart-compare', base ? `Preço (base 100 em ${base})` : 'Preço', series);
  if (!base) $('#chart-compare').innerHTML = '<p class="muted">Estes concelhos não têm nenhum período de preços em comum.</p>';
}
function toggleCompare(d) {
  const i = compare.indexOf(d);
  if (i >= 0) compare.splice(i, 1); else if (compare.length < 4) compare.push(d);
  renderCompare();
  if (selected) select(selected, false);            // atualiza o texto do botão sem saltar para o detalhe
  if (compare.length) $('#compare').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ---------- ranking
const COLS = [
  ['name', 'Concelho', (m) => esc(m.name) + (m.volatile ? ' <span title="Preços muito voláteis (poucas transações): score atenuado">⚠</span>' : '')], ['price', '€/m²', (m) => fmt.eur(m.price)],
  ['price_growth_1y', 'Var. 12m', (m) => fmt.pct(m.price_growth_1y)], ['rent', 'Renda €/m²', (m) => (m.rent == null ? '—' : fmt.eur2(m.rent))],
  ['gross_yield', 'Rendib.', (m) => fmt.pct(m.gross_yield, 2)], ['score_overall', 'Score', (m) => fmt.n(m.score_overall)],
  ['band', 'Nível', (m) => pill(m.band)],
];
function renderTable() {
  const q = $('#search').value.trim().toLowerCase();
  const rows = MUNIS.filter((m) => !q || m.name.toLowerCase().includes(q))
    .sort((a, b) => {
      const x = a[sortKey], y = b[sortKey];
      if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
      return (typeof x === 'string' ? x.localeCompare(y, 'pt') : x - y) * sortDir;
    });
  $('#table').innerHTML = `<thead><tr>${COLS.map(([k, l]) => `<th data-k="${k}">${l}${k === sortKey ? (sortDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr></thead>` +
    `<tbody>${rows.map((m) => `<tr data-d="${esc(m.dico)}">${COLS.map(([, , f]) => `<td>${f(m)}</td>`).join('')}</tr>`).join('')}</tbody>`;
}

async function main() {
  try {
    [MUNIS, NAT, META] = await Promise.all([j('data/municipalities.json'), j('data/national.json'), j('data/meta.json')]);
  } catch (e) {
    document.querySelector('main').innerHTML = `<div class="card"><p>Não foi possível carregar os dados (${esc(e.message)}). Se abriu o ficheiro diretamente, sirva a pasta por HTTP: <code>python -m http.server -d site</code>.</p></div>`;
    return;
  }
  try { GEO = await j('data/concelhos.geojson'); } catch { GEO = null; }
  MUNIS.forEach((m) => (BY[m.dico] = m));
  $('#stamp').textContent = `Atualizado ${META.built_at.slice(0, 10)} · último período de preços: ${META.latest_price_period} · ${META.n_municipalities} concelhos`;
  $('#demo-banner').hidden = !META.demo;
  $('#disclaimer').textContent = META.disclaimer;
  $('#metric').addEventListener('change', updateMetric);
  $('#euribor-sel').addEventListener('change', renderEuribor);
  $('#search').addEventListener('input', renderTable);
  $('#table').addEventListener('click', (e) => {
    const th = e.target.closest('th'), tr = e.target.closest('tbody tr');
    if (th) { const k = th.dataset.k; sortDir = k === sortKey ? -sortDir : (k === 'name' ? 1 : -1); sortKey = k; renderTable(); }
    else if (tr) select(tr.dataset.d);
  });
  $('#d-compare').addEventListener('click', () => selected && toggleCompare(selected));
  $('#c-clear').addEventListener('click', () => { compare.length = 0; renderCompare(); });
  $('#c-chips').addEventListener('click', (e) => { const c = e.target.closest('.chip'); if (c) toggleCompare(c.dataset.d); });
  // Cada parte é isolada: uma falha (por exemplo o mapa/WebGL no Safari) não impede as restantes.
  const safe = (name, fn) => { try { fn(); } catch (e) { console.error(`Falha em ${name}:`, e); return e; } };
  safe('painel nacional', renderNational);
  safe('ranking', renderTable);
  const mapErr = safe('mapa', initMap);
  if (mapErr) {
    $('#map').innerHTML = '<p class="muted" style="padding:16px">Não foi possível iniciar o mapa neste browser (WebGL?). O resto do painel funciona.</p>';
    $('#legend').innerHTML = '';
  }
  window.addEventListener('resize', () => Object.values(charts).forEach((c) => c.resize()));
}
main();
})();
