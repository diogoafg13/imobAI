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

// ---------- glossário (popover ⓘ)
const GLOSS = {
  nat_score: ['Score macro (0–100)', 'Resume 4 sinais nacionais, cada um comparado com a própria história. Mais alto = mais sinais típicos de sobreaquecimento. Não prevê quando, nem se, haverá correção. Ver a secção "Backtest" mais abaixo para saber como este score se saiu no passado, em vários países.'],
  hpi_yoy: ['Crescimento anual do HPI', 'Variação do Índice de Preços da Habitação face ao mesmo trimestre do ano anterior (nominal). A pontuação compara este ritmo com o histórico da série: quanto mais raro, mais alto o score.'],
  hpi_trend_dev: ['Desvio face à tendência', 'Quantos desvios-padrão o índice está acima (+) ou abaixo (−) da sua tendência de longo prazo. Perto de 0 = em linha; 1,8 = bastante acima do que a tendência sugeria.'],
  euribor_change_12m: ['Variação da Euribor 12M', 'Quanto a Euribor 12M subiu (+) ou desceu (−), em pontos percentuais, nos últimos 12 meses. Subidas encarecem o crédito indexado e tendem a arrefecer a procura.'],
  credit_gap: ['Desvio crédito/PIB (BIS)', 'Crédito ao setor privado em % do PIB menos a sua tendência de longo prazo. Acima de +10 p.p. é alerta de crise bancária; muito negativo = desalavancagem (o crédito não está a alimentar os preços). O filtro de tendência exagera os valores negativos depois de longas desalavancagens.'],
  hpi: ['HPI (2015 = 100)', 'Índice de preços da habitação, base 2015 = 100 (150 = 50% acima de 2015). Nominal: valores correntes. Real: descontado o IHPC (inflação), termina no último trimestre com IHPC publicado.'],
  euribor: ['Euribor', 'Taxa interbancária do euro a 3, 6 ou 12 meses (BCE). Grande parte do crédito à habitação em Portugal é indexada a ela. Só a variação da 12M entra no score.'],
  price: ['Preço mediano', 'Mediana dos preços de venda dos últimos 12 meses, em €/m² (INE): metade das vendas acima, metade abaixo. Abaixo de cada valor mostra-se a mediana dos concelhos.'],
  g1y: ['Variação a 12 meses', 'Variação nominal do preço mediano face ao mesmo trimestre do ano anterior (não desconta a inflação).'],
  g3y: ['Variação a 3 anos', 'Variação nominal do preço mediano face a 3 anos antes (não desconta a inflação).'],
  rent: ['Renda de novos contratos', 'Mediana (2.º quartil) das rendas de contratos novos, em €/m² por mês (INE, anual). Contratos antigos costumam ter rendas mais baixas. Sem valor = INE não publica (poucos contratos).'],
  yield: ['Rendibilidade bruta', 'Renda anual ÷ preço. É "bruta": sem IMI, condomínio, vazio ou obras. Mais baixa = preço mais alto face ao que o imóvel rende.'],
  p2r: ['Preço/renda (anos)', 'Anos de renda bruta necessários para "pagar" o imóvel (preço ÷ renda anual). Regra de bolso: acima de ~20–25 anos é caro face às rendas.'],
  score_valuation: ['Score de valorização', 'Percentil entre concelhos: mistura crescimento do preço a 12 meses e a 3 anos com rendibilidade baixa. 0 = menos esticado, 100 = mais. É relativo, não uma probabilidade de bolha.'],
  score_overall: ['Score global', 'Igual ao de valorização enquanto não houver dados de oferta (licenças, conclusões). Concelhos voláteis (⚠) são atenuados para o meio (50).'],
  band: ['Faixa de risco', 'Baixo: abaixo de 40 · Moderado: 40 a 69 · Elevado: 70 ou mais. Posição relativa entre concelhos, não uma previsão.'],
  volatile: ['Dados voláteis', 'Poucas transações: o preço salta de trimestre para trimestre, por isso o score foi atenuado para o meio (50).'],
  compare: ['Comparação', 'Cada linha é o preço do concelho a dividir pelo preço no primeiro trimestre em que todos têm dados, ×100. 120 = +20% desde a base. Mostra ritmo relativo, não o nível de preços. Concelhos com séries curtas encurtam o período comparado.'],
  ranking: ['Ranking', 'Clica no cabeçalho para ordenar e num concelho para ver o detalhe. Score alto = mais esticado face aos outros concelhos, não previsão de queda.'],
  backtest_intro: ['Backtest do score nacional', 'Testa se o score nacional, calculado à data (sem ver dados futuros), teria sinalizado antes de quedas grandes do preço real da habitação — em vários países da UE, não só Portugal, que sozinho só tem um episódio de queda (2008–2013). Ver a lista de limites abaixo: a amostra é pequena e os episódios não são independentes (crise financeira global de 2008).'],
  backtest_chart: ['Score vs. HPI real', 'O score nacional (linha esquerda, 0–100) tal como teria sido calculado nesse trimestre, sem ver dados futuros, contra o índice de preços real do país (linha direita, 2015 = 100). A linha pontilhada nos 70 é o limiar de alerta usado no painel.'],
  backtest_metrics: ['Métricas do backtest', 'Spearman: correlação entre o score e a variação real do preço nos trimestres seguintes (negativa = score alto antecipa queda, o que é desejável). AUC: capacidade de distinguir trimestres que antecedem uma queda real ≥10% nos 3 anos seguintes — 1 é perfeito, 0,5 é aleatório, 0 é sempre errado na direção oposta. Acerto/Falso alarme: com o limiar do painel (normalmente 70), por trimestre avaliado, comparado com duas regras simples (só o crescimento do HPI; só o desvio crédito/PIB).'],
};
const info = (k) => (GLOSS[k] ? `<button type="button" class="info" data-k="${k}" aria-label="O que é: ${esc(GLOSS[k][0])}">ⓘ</button>` : '');
let tipBtn = null;
function hideTip() { const t = document.getElementById('tip'); if (t) t.hidden = true; tipBtn = null; }
function showTip(btn) {
  const g = GLOSS[btn.dataset.k], t = document.getElementById('tip'); if (!g || !t) return;
  t.innerHTML = `<b>${esc(g[0])}</b>${esc(g[1])}`;
  t.hidden = false;
  const r = btn.getBoundingClientRect(), w = Math.min(320, innerWidth - 24);
  t.style.width = w + 'px';
  t.style.left = Math.max(12, Math.min(r.left + r.width / 2 - w / 2, innerWidth - w - 12)) + scrollX + 'px';
  t.style.top = r.bottom + 8 + scrollY + 'px';
  tipBtn = btn;
}
document.addEventListener('click', (e) => {
  const b = e.target.closest('.info');
  if (b) { e.preventDefault(); tipBtn === b ? hideTip() : showTip(b); }
  else if (!e.target.closest('#tip')) hideTip();
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideTip(); });

let MUNIS = [], BY = {}, NAT = null, META = null, GEO = null, MAP = null, BT = null;
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
  score: { prop: 'score', pal: PAL, fixed: [0, 100], f: (v) => fmt.n(v), label: 'Score',
    help: 'Quão "esticado" está cada concelho face aos outros: preço a subir depressa e rendibilidade baixa = mais vermelho. Verde < 40 (baixo), amarelo/laranja 40–69 (moderado), vermelho ≥ 70 (elevado). É relativo, não uma probabilidade de bolha. Cinzento = sem dados.' },
  price: { prop: 'price', pal: SEQ, f: fmt.eur, label: '€/m²',
    help: 'Preço mediano de venda (INE, últimos 12 meses). Mais escuro = mais caro. A escala vai do 5.º ao 95.º percentil para os extremos não achatarem o resto do mapa.' },
  yield: { prop: 'yield', pal: SEQ, f: (v) => fmt.pct(v, 2), label: 'Rendibilidade bruta',
    help: 'Renda anual ÷ preço, antes de custos. Mais escuro = a renda paga mais do preço; claro = preço alto face à renda. Cinzento = INE não publica renda para o concelho.' },
  g1y: { prop: 'g1y', pal: SEQ, f: (v) => fmt.pct(v), label: 'Var. 12m',
    help: 'Variação nominal do preço face ao mesmo trimestre do ano anterior (não desconta a inflação). Mais escuro = subiu mais.' },
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
    : `<div class="num">${Math.round(ov)}</div><div>${pill(n.band)}</div><div class="muted">score macro (0–100) ${info('nat_score')}</div>`;
  const li = Object.entries(n.components).map(([key, c]) => {
    const isPct = /anual|Crescimento/.test(c.label);
    const val = c.value == null ? '—' : isPct ? fmt.pct(c.value) : fmt.n(c.value, 2);
    const band = c.score == null ? null : c.score < 40 ? 'green' : c.score < 70 ? 'amber' : 'red';
    return `<li><span>${esc(c.label)} ${info(key)}</span><span>${val} ${pill(band, c.score == null ? 'n/d' : Math.round(c.score))}</span></li>`;
  });
  $('#nat-components').innerHTML = li.join('') || '<li class="muted">Sem componentes disponíveis</li>';
  const fHpi = (v) => fmt.n(v, 1) + ' (2015 = 100)';
  lineChart('chart-hpi', 'HPI', [
    { name: 'Nominal', data: n.series.hpi, fmt: fHpi },
    ...(n.series.hpi_real && n.series.hpi_real.length ? [{ name: 'Real (sem inflação)', data: n.series.hpi_real, fmt: fHpi, dashed: true }] : []),
  ], { notitle: true, refs: [{ y: 100, label: '2015' }] });
  lineChart('chart-credit', 'Crédito/PIB', [{ name: 'Desvio crédito/PIB', data: n.series.credit_gap || [], fmt: (v) => fmt.n(v, 1) + ' p.p.' }],
    { notitle: true, refs: [{ y: 0, label: 'tendência' }, { y: 10, label: 'alerta (+10)' }] });
  renderEuribor();
}

function renderEuribor() {
  const sel = $('#euribor-sel').value, S = NAT.series;
  const all = [['3M', S.euribor_3m], ['6M', S.euribor_6m], ['12M', S.euribor_12m]];
  const pick = sel === 'all' ? all : all.filter(([n]) => n.toLowerCase() === sel);
  const series = pick.map(([name, data]) => ({ name, data: data || [] })).filter((x) => x.data.length);
  const fE = (v) => fmt.n(v, 2) + ' %';
  lineChart('chart-euribor', 'Euribor', series.map((x) => ({ ...x, fmt: fE })), { notitle: true, refs: [{ y: 0, label: '0 %' }] });
}

function lineChart(id, title, series, opts = {}) {
  const el = document.getElementById(id);
  // Liberta SEMPRE a instância anterior (mesmo que já não esteja em `charts`): o ECharts prende-se ao
  // elemento, e limpar o innerHTML sem dispose deixava o gráfico seguinte em branco.
  const prev = echarts.getInstanceByDom(el);
  if (prev) prev.dispose();
  delete charts[id];
  el.innerHTML = '';
  if (!series.some((s) => s.data && s.data.length)) { el.innerHTML = `<p class="muted">${esc(title)}: sem dados</p>`; return; }
  charts[id] = echarts.init(el);
  const txt = css('--muted'), line = css('--line');
  const crowded = !!opts.names || series.length > 1;
  const refs = (opts.refs || []).map((r) => ({ yAxis: r.y, label: { show: true, formatter: r.label, color: txt, fontSize: 10, position: 'insideEndTop' } }));
  const yAxis = [0, 1].slice(0, opts.dual ? 2 : 1).map((i) => ({
    type: 'value', scale: true, name: opts.names && opts.names[i], nameTextStyle: { color: txt, fontSize: 11, align: i ? 'right' : 'left' },
    axisLabel: { color: txt }, splitLine: { show: !i, lineStyle: { color: line } },
  }));
  charts[id].setOption({
    animation: false, color: [css('--accent'), '#e08a3b', '#8bc16a', '#b07cc6'],
    title: opts.notitle ? undefined : { text: title, textStyle: { fontSize: 12, color: txt, fontWeight: 500 } },
    grid: { left: 46, right: opts.dual ? 50 : 12, top: crowded ? (opts.notitle ? 34 : 50) : (opts.notitle ? 12 : 34), bottom: 24 },
    tooltip: {
      trigger: 'axis', confine: true,
      formatter: (ps) => {
        const a = (Array.isArray(ps) ? ps : [ps]).filter((p) => p.value && p.value[1] != null);
        if (!a.length) return '';
        return `<b>${esc(a[0].axisValueLabel || a[0].value[0])}</b><br>` + a.map((p) => {
          const f = (series[p.seriesIndex] && series[p.seriesIndex].fmt) || ((v) => String(v));
          return `${p.marker} ${esc(p.seriesName)}: <b>${esc(f(p.value[1]))}</b>`;
        }).join('<br>');
      },
    },
    legend: series.length > 1 ? { top: 0, right: 0, textStyle: { color: txt } } : undefined,
    xAxis: { type: 'category', data: [...new Set(series.flatMap((s) => s.data.map((d) => d[0])))].sort(), axisLabel: { color: txt }, axisLine: { lineStyle: { color: line } } },
    yAxis,
    series: series.map((s, i) => ({
      name: s.name, type: 'line', showSymbol: !!s.dots, symbolSize: 6, smooth: false, yAxisIndex: s.axis || 0, connectNulls: true, data: s.data,
      lineStyle: s.dashed ? { type: 'dashed', width: 2 } : { width: 2 },
      ...(i === 0 && refs.length ? { markLine: { silent: true, symbol: 'none', lineStyle: { type: 'dotted', color: txt, width: 1 }, data: refs } } : {}),
    })),
  }, true);
}

// ---------- mapa
function metricExpr(m) {
  return ['case', ['==', ['get', m.prop], null], css('--none'), ['interpolate', ['linear'], ['to-number', ['get', m.prop]], ...stops(m)]];
}
function renderLegend(m) {
  const [lo, hi] = domain(m);
  $('#legend').innerHTML = `<span>${m.f(lo)}</span><span class="bar" style="background:linear-gradient(90deg,${m.pal.join(',')})"></span><span>${m.f(hi)}</span><span>· ${esc(m.label)}</span>`;
  $('#map-help').textContent = m.help || '';
}
const BOUNDS = { pt: [[-9.7, 36.85], [-6.1, 42.2]], az: [[-31.4, 36.8], [-24.9, 39.8]], ma: [[-17.4, 32.55], [-16.15, 33.15]] };
function fitTo(k) {
  if (!MAP) return;
  if (k === 'pt' && META.demo) {
    const b = new maplibregl.LngLatBounds();
    const ext = (c) => (typeof c[0] === 'number' ? b.extend(c) : c.forEach(ext));
    GEO.features.forEach((f) => ext(f.geometry.coordinates));
    MAP.fitBounds(b, { padding: 12, animate: false }); return;
  }
  MAP.fitBounds(BOUNDS[k], { padding: 12, duration: k === 'pt' ? 0 : 500 });
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
    fitTo('pt');
    const pop = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
    const nz = (x) => (x == null || x === 'null' || x === '' ? null : Number(x));
    MAP.on('mousemove', 'fill', (e) => {
      const f = e.features[0]; if (!f) return;
      const p = f.properties, k = $('#metric').value;
      const val = { score: fmt.n(nz(p.score)), price: fmt.eur(nz(p.price)), yield: fmt.pct(nz(p.yield), 2), g1y: fmt.pct(nz(p.g1y)) }[k];
      pop.setLngLat(e.lngLat).setHTML(`<b>${esc(p.name)}</b><br>${esc(METRICS[k].label)}: ${esc(val)}<br><span style="color:#555">clica para o detalhe</span>`).addTo(MAP);
    });
    MAP.on('mouseleave', 'fill', () => pop.remove());
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
// contexto: mediana e posição do concelho entre todos
const col = (g) => MUNIS.map(g).filter((x) => x != null && !Number.isNaN(x));
const median = (arr) => (arr.length ? quantile([...arr].sort((x, y) => x - y), 0.5) : null);
const ctx = (g, v, f) => {
  if (v == null) return '';
  const all = col(g); if (all.length < 5) return '';
  const above = Math.round((all.filter((x) => x < v).length / all.length) * 100);
  return `<span class="ctx">mediana dos concelhos ${f(median(all))} · acima de ${above}%</span>`;
};
const rel = (x) => `${Math.round(Math.abs(x) * 100)}% ${x >= 0 ? 'acima' : 'abaixo'}`;
function readList(m) {
  const li = [];
  const mp = median(col((x) => x.price));
  if (m.price != null && mp) li.push(`Preço de ${fmt.eur(m.price)}/m²: ${m.price / mp >= 2 ? fmt.n(m.price / mp, 1) + '× a' : rel(m.price / mp - 1) + ' da'} mediana dos concelhos (${fmt.eur(mp)}).`);
  const mg = median(col((x) => x.price_growth_1y));
  if (m.price_growth_1y != null) li.push(`Subiu ${fmt.pct(m.price_growth_1y)} em 12 meses (mediana dos concelhos: ${fmt.pct(mg)}) e ${fmt.pct(m.price_growth_3y)} em 3 anos, sem descontar inflação.`);
  const my = median(col((x) => x.gross_yield));
  if (m.gross_yield != null && my != null) {
    li.push(`Rendibilidade bruta de ${fmt.pct(m.gross_yield, 2)} (mediana ${fmt.pct(my, 2)}): ${m.gross_yield < my ? 'o preço está esticado face à renda, pois cada € investido rende menos do que no concelho típico' : 'a renda paga melhor o preço do que no concelho típico'}.`);
  } else li.push('Sem renda publicada pelo INE para este concelho (poucos contratos): não há rendibilidade nem preço/renda, e o score assenta só no ritmo de subida dos preços.');
  const sc = m.score_overall;
  if (sc != null) li.push(`Score ${fmt.n(sc)}: ${sc >= 70 ? 'entre os concelhos mais "esticados"' : sc >= 40 ? 'a meio do pelotão de concelhos' : 'entre os concelhos menos "esticados"'}. É uma posição relativa, não uma previsão de queda.`);
  if (m.volatile) li.push('⚠ Poucos negócios: o preço é muito volátil e o score foi atenuado. Lê estes números com cautela.');
  return li.map((t) => `<li>${esc(t)}</li>`).join('');
}
function select(dico, scroll = true) {
  const m = BY[dico]; if (!m) return;
  if (MAP && MAP.getSource('c')) {
    if (selected) MAP.setFeatureState({ source: 'c', id: selected }, { sel: false });
    MAP.setFeatureState({ source: 'c', id: dico }, { sel: true });
  }
  selected = dico;
  $('#detail').hidden = false;
  $('#detail').style.borderLeftColor = `var(--${m.band || 'none'})`;
  $('#d-title').innerHTML = `${esc(m.name)} ${pill(m.band)} ${info('band')}${m.volatile ? ' ' + pill(null, '⚠ dados voláteis') + ' ' + info('volatile') : ''}`;
  const tile = (k, label, val, c = '') => `<div class="stat"><span class="muted">${label} ${info(k)}</span><b>${val}</b>${c}</div>`;
  $('#d-stats').innerHTML = [
    tile('price', 'Preço mediano', fmt.eur(m.price) + '/m²', ctx((x) => x.price, m.price, fmt.eur)),
    tile('g1y', 'Var. 12m', fmt.pct(m.price_growth_1y), ctx((x) => x.price_growth_1y, m.price_growth_1y, (v) => fmt.pct(v))),
    tile('g3y', 'Var. 3 anos', fmt.pct(m.price_growth_3y), ctx((x) => x.price_growth_3y, m.price_growth_3y, (v) => fmt.pct(v))),
    tile('rent', 'Renda (novos contratos)', m.rent == null ? '—' : fmt.eur2(m.rent) + '/m²', ctx((x) => x.rent, m.rent, fmt.eur2)),
    tile('yield', 'Rendibilidade bruta', fmt.pct(m.gross_yield, 2), ctx((x) => x.gross_yield, m.gross_yield, (v) => fmt.pct(v, 2))),
    tile('p2r', 'Preço/renda (anos)', fmt.n(m.price_to_rent_years, 1), ctx((x) => x.price_to_rent_years, m.price_to_rent_years, (v) => fmt.n(v, 1))),
    tile('score_valuation', 'Score valorização', fmt.n(m.score_valuation)),
    tile('score_overall', 'Score global', fmt.n(m.score_overall)),
  ].join('');
  $('#d-read').innerHTML = readList(m);
  const s = [{ name: 'Preço', data: m.series.price, fmt: (v) => fmt.eur(v) + '/m²' }];
  const q4 = (p) => (p.length === 4 ? p + 'Q4' : p);
  if (m.series.rent.length) s.push({ name: 'Renda', data: m.series.rent.map(([p, v]) => [q4(p), v]), axis: 1, dots: true, fmt: (v) => fmt.eur2(v) + '/m²/mês' });
  lineChart('chart-detail', 'Evolução', s, { dual: s.length > 1, names: s.length > 1 ? ['Preço (€/m²)', 'Renda (€/m²/mês)'] : ['Preço (€/m²)'], notitle: true });
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
  const fC = (v) => `${fmt.n(v, 0)} (${v >= 100 ? '+' : '−'}${fmt.n(Math.abs(v - 100), 1)}% desde a base)`;
  lineChart('chart-compare', 'Preço', series.map((x) => ({ ...x, fmt: fC })), { names: [base ? `Preço, base 100 em ${base}` : 'Preço'], refs: [{ y: 100, label: 'base' }], notitle: true });
  if (!base) $('#chart-compare').innerHTML = '<p class="muted">Estes concelhos não têm nenhum período de preços em comum.</p>';
}
function toggleCompare(d) {
  const i = compare.indexOf(d);
  if (i >= 0) compare.splice(i, 1); else if (compare.length < 4) compare.push(d);
  renderCompare();
  if (selected) select(selected, false);            // atualiza o texto do botão sem saltar para o detalhe
  if (compare.length) $('#compare').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ---------- backtest
const BT_MODELS = [
  ['score', 'Score nacional (painel)'], ['baseline_hpi_yoy', 'Só crescimento do HPI'], ['baseline_credit_gap', 'Só desvio crédito/PIB'],
];
function renderBacktest() {
  const body = $('#backtest-body');
  if (!BT) {
    body.innerHTML = '<p class="muted">Backtest ainda não gerado nesta build. Corre <code>python -m imopt backtest</code> (ver README).</p>';
    return;
  }
  $('#bt-generated').textContent = 'Gerado ' + BT.generated_at.slice(0, 10) + (BT.demo ? ' · dados sintéticos de demonstração' : '');
  const countryOpts = BT.countries.map((c) => `<option value="${esc(c.code)}">${esc(c.name)}${c.group === 'control' ? ' (controlo)' : ''}</option>`).join('');
  body.innerHTML = `
    <p id="bt-verdict" class="verdict"></p>
    <div class="row">
      <label>País <select id="bt-country" aria-label="País do backtest">${countryOpts}</select></label>
    </div>
    <div class="chart-cap"><span>Score vs. HPI real ${info('backtest_chart')}</span></div>
    <div id="chart-backtest" class="chart tall"></div>
    <div class="table-wrap"><table id="bt-table"></table></div>
    <p id="bt-robust" class="muted"></p>
    <p class="muted"><b>Limites deste backtest</b> ${info('backtest_intro')}</p>
    <ul id="bt-limits" class="read"></ul>`;
  $('#bt-verdict').textContent = BT.summary.verdict_pt;
  $('#bt-limits').innerHTML = BT.limits.map((l) => `<li>${esc(l)}</li>`).join('');
  const sel = $('#bt-country');
  if (BT.countries.some((c) => c.code === 'PT')) sel.value = 'PT';
  const drawChart = () => {
    try { renderBacktestChart(); } catch (e) {
      console.error('Falha no gráfico do backtest:', e);
      $('#chart-backtest').innerHTML = '<p class="muted">Não foi possível desenhar este gráfico.</p>';
    }
  };
  sel.addEventListener('change', drawChart);
  drawChart();          // isolado: uma falha no gráfico não deve esconder a tabela e os limites abaixo
  renderBacktestTable();
  renderBacktestRobustness();
}
function renderBacktestChart() {
  const cc = $('#bt-country').value, s = BT.series[cc];
  if (!s) return;
  const scoreSeries = { name: 'Score', data: s.period.map((p, i) => [p, s.score[i]]), fmt: (v) => fmt.n(v) };
  const hpiSeries = { name: 'HPI real', data: s.period.map((p, i) => [p, s.hpi_real[i]]), axis: 1, fmt: (v) => fmt.n(v, 1) };
  lineChart('chart-backtest', 'Backtest', [scoreSeries, hpiSeries],
    { dual: true, names: ['Score (0–100)', 'HPI real (2015 = 100)'], notitle: true, refs: [{ y: 70, label: 'limiar 70' }] });
}
function renderBacktestTable() {
  const m = BT.metrics.pooled;
  const panelThr = BT.params.thresholds.includes(70) ? 70 : BT.params.thresholds[0];
  const rows = BT_MODELS.map(([k, label]) => {
    const mm = m[k];
    if (!mm) return `<tr><td>${esc(label)}</td><td colspan="6" class="muted">sem dados</td></tr>`;
    const t = mm.thresholds[String(panelThr)];
    return `<tr><td>${esc(label)}</td><td>${fmt.n(mm.spearman_real_4q, 2)}</td><td>${fmt.n(mm.spearman_real_8q, 2)}</td>` +
      `<td>${fmt.n(mm.spearman_real_12q, 2)}</td><td>${fmt.n(mm.auc_drawdown, 2)}</td>` +
      `<td>${t && t.hit_rate != null ? fmt.pct(t.hit_rate) : '—'}</td><td>${t && t.false_alarm_rate != null ? fmt.pct(t.false_alarm_rate) : '—'}</td></tr>`;
  }).join('');
  $('#bt-table').innerHTML = '<thead><tr><th style="text-align:left">Modelo</th><th>Spearman 4T</th><th>Spearman 8T</th>' +
    `<th>Spearman 12T</th><th>AUC queda ${info('backtest_metrics')}</th><th>Acerto @${panelThr}</th><th>Falso alarme @${panelThr}</th></tr></thead><tbody>${rows}</tbody>`;
}
function renderBacktestRobustness() {
  const loo = Object.values(BT.metrics.leave_one_out).map((v) => v.auc_drawdown).filter((v) => v != null);
  const mh = BT.metrics.min_history_sensitivity || {};
  const mhVals = Object.values(mh).map((v) => v.auc_drawdown).filter((v) => v != null);
  const pt = BT.metrics.portugal_only && BT.metrics.portugal_only.score;
  const parts = [];
  if (loo.length > 1) parts.push(`Excluindo um país de cada vez, o AUC do score varia entre ${fmt.n(Math.min(...loo), 2)} e ${fmt.n(Math.max(...loo), 2)}.`);
  if (mhVals.length) parts.push(`Com um histórico mínimo diferente (${Object.keys(mh).join(' ou ')} trimestres, em vez de ${BT.params.min_history_quarters}), o AUC vai de ${fmt.n(Math.min(...mhVals), 2)} a ${fmt.n(Math.max(...mhVals), 2)}.`);
  if (pt) parts.push(`Só Portugal: Spearman a 12 trimestres (real) de ${fmt.n(pt.spearman_real_12q, 2)}, AUC de ${fmt.n(pt.auc_drawdown, 2)} — amostra pequena, um único episódio independente.`);
  $('#bt-robust').textContent = parts.join(' ');
}

// ---------- ranking
const COL_HELP = { price: 'price', price_growth_1y: 'g1y', rent: 'rent', gross_yield: 'yield', score_overall: 'score_overall', band: 'band' };
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
  $('#table').innerHTML = `<thead><tr>${COLS.map(([k, l]) => `<th data-k="${k}"${COL_HELP[k] ? ` title="${esc(GLOSS[COL_HELP[k]][1])}"` : ''}>${l}${k === sortKey ? (sortDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr></thead>` +
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
  try { BT = await j('data/backtest.json'); } catch { BT = null; }
  MUNIS.forEach((m) => (BY[m.dico] = m));
  $('#stamp').textContent = `Atualizado ${META.built_at.slice(0, 10)} · último período de preços: ${META.latest_price_period} · ${META.n_municipalities} concelhos`;
  $('#demo-banner').hidden = !META.demo;
  $('#disclaimer').textContent = META.disclaimer;
  $('#metric').addEventListener('change', updateMetric);
  document.querySelector('.mapnav').addEventListener('click', (e) => { const b = e.target.closest('[data-b]'); if (b) fitTo(b.dataset.b); });
  $('#euribor-sel').addEventListener('change', renderEuribor);
  $('#search').addEventListener('input', renderTable);
  $('#table').addEventListener('click', (e) => {
    if (e.target.closest('.info')) return;
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
  safe('backtest', renderBacktest);
  const mapErr = safe('mapa', initMap);
  if (mapErr) {
    $('#map').innerHTML = '<p class="muted" style="padding:16px">Não foi possível iniciar o mapa neste browser (WebGL?). O resto do painel funciona.</p>';
    $('#legend').innerHTML = '';
  }
  window.addEventListener('resize', () => Object.values(charts).forEach((c) => c.resize()));
}
main();
})();
