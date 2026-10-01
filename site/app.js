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
  spct: (v, d = 1) => (v == null ? '—' : (v >= 0 ? '+' : '−') + (Math.abs(v) * 100).toFixed(d).replace('.', ',') + '%'),
};
const qpt = (p) => String(p ?? '').replace('Q', 'T');
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
  p2i: ['Preço/rendimento (meses)', 'Meses de ganho médio mensal (por trabalhador, INE/MTSSS) necessários para pagar 1 m². É um indicador simplificado — não é o clássico "anos de salário para comprar casa", que precisaria do preço total do imóvel e do rendimento do agregado familiar, não do ganho médio individual por m². Quanto mais alto, mais esticado o preço face aos salários locais. É sobre COMPRA, não arrendamento.'],
  r2i: ['Renda/rendimento', 'Fração do ganho médio mensal (por trabalhador) necessária para arrendar 1 m². Ao contrário do "Preço/rendimento" (que é sobre comprar), este é sobre ARRENDAR — quanto mais alto, mais pesa a renda no salário local. Só aparece quando o concelho tem renda e rendimento publicados.'],
  outlook: ['Perspetivas', 'Previsões e padrões calculados a partir dos mesmos dados oficiais (INE, BCE, Eurostat). Cada previsão foi testada no passado recente sem ver o futuro (backtest) e comparada com regras ingénuas — os resultados, bons ou maus, estão aqui. Nada disto altera os scores do painel, nem é aconselhamento financeiro.'],
  nowcast: ['Estimativa para hoje', 'O INE publica o preço de venda com meses de atraso. A avaliação bancária (também do INE) sai mais cedo: o modelo usa-a para estimar onde está o preço agora, antes de ser publicado.'],
  fc12: ['Previsão a 12 meses', 'Preço mediano de venda previsto daqui a um ano, com um intervalo onde o valor real caiu cerca de 80% das vezes no backtest. O intervalo é o mais importante: o valor central é só o mais provável.'],
  fc_chart: ['Leque da previsão', 'Linha cheia: preço publicado pelo INE. Tracejado: estimativa para os trimestres ainda não publicados e previsão. Faixa escura: 50% de probabilidade; faixa clara: 80%. Quanto mais longe, mais larga, porque a incerteza cresce.'],
  rent_fc: ['Renda prevista', 'Renda mediana de novos contratos (€/m²) prevista para o próximo ano, com intervalo de 80%. Confiança mais baixa do que a do preço: só há 6 anos de dados por concelho.'],
  fv: ['Valor justo', 'Preço que os fundamentos observáveis explicam: rendimento, densidade, envelhecimento, migração, litoral, distância a Lisboa/Porto e região. Acima = mais caro do que concelhos parecidos. Pode ser sobrevalorização OU algo que o modelo não vê (praia, turismo, universidade, qualidade das casas).'],
  typology: ['Tipologia de mercado', 'Grupo de concelhos com trajetórias parecidas, encontrado automaticamente (k-means) a partir do nível do preço e do ritmo de subida antes e depois de o BCE começar a subir juros (2022T2).'],
  regimes: ['Regimes do mercado', 'O índice de preços nacional (HPI) dividido em fases com ritmo constante. Os pontos de quebra são escolhidos pelos dados (regressão por troços, critério BIC), não à mão.'],
  ripple: ['Distância a Lisboa e Porto', 'Testa se as subidas se propagam das metrópoles para fora: compara o ritmo de subida por distância e procura o desfasamento (em meses) que melhor liga cada concelho à metrópole mais próxima.'],
  rates: ['Cenários de juros', 'Prestação e capacidade de endividamento são aritmética pura (crédito a 30 anos, Euribor + 1 p.p.). O efeito nos preços só é mostrado se a relação histórica for estatisticamente clara.'],
  new_old: ['Casas novas vs existentes', 'Preço mediano de venda (INE, 12 meses) de alojamentos novos e de existentes (usados). O prémio é quanto mais caras são as novas. Muitos concelhos não têm vendas de casas novas suficientes para o INE publicar.'],
  val_type: ['Apartamentos vs moradias', 'Avaliação bancária mediana (€/m², média dos últimos 3 meses) por tipo de casa, e previsão a 12 meses feita com o mesmo método das vendas, mas com 15 anos de histórico (desde 2011). A avaliação bancária não é o preço de transação: só cobre casas com crédito.'],
  rent_q: ['Quartis da renda', '1.º quartil: 25% dos novos contratos têm renda abaixo deste valor — a renda "barata" do concelho. 3.º quartil: 25% acima. Quanto maior a distância entre os dois, mais variado é o mercado de arrendamento.'],
  rent_contracts: ['Novos contratos de arrendamento', 'Número de novos contratos de arrendamento registados no ano (INE). Mede o tamanho do mercado de arrendamento: poucos contratos = renda mediana menos fiável.'],
  tourism: ['Pressão turística', 'Dormidas em alojamento turístico por habitante, no ano (INE). Mede o peso do turismo no concelho — uma das razões para preços acima do que os rendimentos locais explicam. Entra no modelo de valor justo.'],
  credit_pc: ['Crédito à habitação por habitante', 'Stock de crédito à habitação a dividir pela população (INE, anual). Mostra o endividamento das famílias para comprar casa; acompanha naturalmente os preços, por isso não entra no valor justo.'],
  foreign: ['Compradores estrangeiros', 'Preço mediano (€/m², 12 meses) pago por compradores com domicílio fiscal no estrangeiro, comparado com o dos compradores com domicílio em Portugal (INE). Um prémio alto indica procura externa a puxar pelos preços — muitas vezes em casas diferentes (localização, tamanho). O INE só publica onde há vendas suficientes a estrangeiros.'],
  companies: ['Famílias vs empresas', 'Preço mediano (€/m², 12 meses) pago por famílias e por empresas e outras entidades (bancos, fundos, Estado…) — o INE chama-lhes "restantes setores institucionais". Empresas a pagar mais costuma indicar compras para investimento, reabilitação ou alojamento local, muitas vezes em casas diferentes das que as famílias compram. O INE só publica onde há vendas suficientes.'],
  tipologia: ['Preço por tipologia', 'Preço mediano de venda por m² (INE, 12 meses) por número de quartos. Casas pequenas costumam custar mais por m².'],
  val_count: ['Volume de avaliações bancárias', 'Número de avaliações bancárias nos últimos 3 meses (INE): mede quantas compras com crédito estão a acontecer. O volume costuma cair antes dos preços — uma queda forte e generalizada é um sinal clássico de arrefecimento.'],
  tracking: ['Previsões anteriores vs realidade', 'Cada build guarda as previsões que publicou. Quando o INE publica o valor real de um trimestre (ou ano, nas rendas) previsto, o erro é medido aqui — com os dados tal como saíram, sem revisões nem o benefício da retrospetiva. É a avaliação mais honesta, mas precisa de tempo: a 12 meses, os primeiros resultados só aparecem um ano depois do arranque do arquivo.'],
  ol_backtest: ['Como se saiu no passado', 'Para cada trimestre desde 2021, o modelo foi treinado só com o que se sabia nessa data e previu os trimestres seguintes. Erro médio em pontos percentuais (p.p.) de variação do preço, comparado com «fica igual» e «continua o ritmo do último ano». Cobertura: % das vezes em que o valor real caiu dentro do intervalo de 80%.'],
  migration: ['Saldo migratório', 'Diferença entre quem chegou e quem saiu do concelho num ano (INE). Positivo = mais gente a chegar do que a sair. Só contexto demográfico — não entra em nenhum score.'],
  score_valuation: ['Score de valorização', 'Percentil entre concelhos: mistura crescimento do preço a 12 meses e a 3 anos com rendibilidade baixa. 0 = menos esticado, 100 = mais. É relativo, não uma probabilidade de bolha.'],
  score_overall: ['Score global', 'Igual ao de valorização enquanto não houver dados de oferta (licenças, conclusões). Concelhos voláteis (⚠) são atenuados para o meio (50).'],
  band: ['Faixa de risco', 'Baixo: abaixo de 40 · Moderado: 40 a 69 · Elevado: 70 ou mais. Posição relativa entre concelhos, não uma previsão.'],
  volatile: ['Dados voláteis', 'Poucas transações: o preço salta de trimestre para trimestre, por isso o score foi atenuado para o meio (50).'],
  compare: ['Comparação', 'Gráfico: cada linha é o preço (ou renda) do concelho a dividir pelo valor no primeiro período em que todos têm dados, ×100. 120 = +20% desde a base. Mostra ritmo relativo, não o nível. Concelhos com séries curtas encurtam o período comparado. Tabela abaixo: valores atuais de todos os indicadores, lado a lado, sem normalização.'],
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

let MUNIS = [], BY = {}, NAT = null, META = null, GEO = null, MAP = null, BT = null, OL = null;
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
  fc: { prop: 'fc', pal: SEQ, f: (v) => fmt.spct(v), label: 'Previsão 12 meses',
    help: 'Variação prevista do preço mediano de venda nos próximos 12 meses (valor central; cada concelho tem um intervalo no detalhe). Ver a secção "Perspetivas" para saber como a previsão se saiu no passado. Cinzento = sem previsão.' },
  fv: { prop: 'fv', pal: ['#256abf', '#86b6ef', '#e2e2df', '#f4a07c', '#c9531f'], diverge: true, f: (v) => fmt.spct(v, 0), label: 'Face ao valor justo',
    help: 'Laranja = preço acima do que rendimento, demografia, litoral, distância e região explicam; azul = abaixo; cinzento claro = em linha. Não é prova de bolha: pode ser praia, turismo ou qualidade das casas, que o modelo não vê. Cinzento escuro = sem dados.' },
};
METRICS.fp = { prop: 'fp', pal: ['#256abf', '#86b6ef', '#e2e2df', '#f4a07c', '#c9531f'], diverge: true, f: (v) => fmt.spct(v, 0), label: 'Prémio de estrangeiros',
  help: 'Quanto mais (laranja) ou menos (azul) pagam por m² os compradores com domicílio no estrangeiro face aos residentes em Portugal. Cinzento = INE não publica (poucas vendas a estrangeiros).' };
const METRIC_VAL = { score: (x) => x.score_overall, price: (x) => x.price, yield: (x) => x.gross_yield, g1y: (x) => x.price_growth_1y,
  fc: (x) => x.fc_growth_12m, fv: (x) => x.fv_gap, fp: (x) => x.foreign_premium };
function quantile(sorted, q) { const i = (sorted.length - 1) * q, lo = Math.floor(i), hi = Math.ceil(i); return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo); }
function domain(m) {
  if (m.fixed) return m.fixed;
  const v = MUNIS.map(METRIC_VAL[m.prop]).filter((x) => x != null).sort((a, b) => a - b);
  if (v.length < 2) return [0, 1];
  const lo = quantile(v, 0.05), hi = quantile(v, 0.95);
  if (m.diverge) { const a = Math.max(Math.abs(lo), Math.abs(hi)) || 1; return [-a, a]; }
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
  $('#nat-read').innerHTML = natReadList(n);
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

// Traduz os números do score nacional em frases — a leitura que, de outra forma, só se tem perguntando.
const NAT_BAND_TXT = {
  green: 'poucos sinais de sobreaquecimento neste momento.',
  amber: 'há sinais presentes, mas não os suficientes para soar o alarme.',
  red: 'a maioria dos sinais aponta para sobreaquecimento — historicamente associado a mais risco de correção ' +
    'nos 3 anos seguintes (ver a secção "Backtest" mais abaixo), mas isso não é uma certeza, nem diz quando.',
};
const NAT_DESCR = {
  hpi_yoy: (c) => `Os preços da habitação (HPI) sobem ${fmt.pct(c.value)} ao ano — ` +
    (c.score >= 65 ? 'ritmo invulgarmente rápido face à história da série.'
      : c.score <= 35 ? 'ritmo lento face ao habitual.' : 'perto do ritmo típico.'),
  hpi_trend_dev: (c) => `O índice está ${fmt.n(Math.abs(c.value), 1)} desvios-padrão ${c.value >= 0 ? 'acima' : 'abaixo'} ` +
    `da sua tendência de longo prazo — ${Math.abs(c.value) >= 1.5 ? 'bastante fora do habitual.' : 'relativamente perto da tendência.'}`,
  euribor_change_12m: (c) => `A Euribor 12M ${c.value >= 0 ? 'subiu' : 'desceu'} ${fmt.n(Math.abs(c.value), 2)} p.p. no último ano — ` +
    (c.value >= 0 ? 'crédito mais caro, o que tende a arrefecer a procura.' : 'crédito mais barato, o que tende a aquecer a procura.'),
  credit_gap: (c) => `O crédito ao setor privado está ${fmt.n(Math.abs(c.value), 1)} p.p. ${c.value >= 0 ? 'acima' : 'abaixo'} ` +
    `da sua tendência de longo prazo — ${c.value >= 10 ? 'zona de alerta de alavancagem alta.'
      : c.value <= -10 ? 'desalavancagem: o crédito não está a alimentar os preços.' : 'perto da tendência.'}`,
};
function natReadList(n) {
  if (n.overall == null) return '<li class="muted">Sem dados macro suficientes para uma leitura.</li>';
  const li = [`Score global de ${fmt.n(n.overall)}, na faixa <b>${esc(BAND_LABEL[n.band] || 'n/d')}</b>: ${esc(NAT_BAND_TXT[n.band] || '')}`];
  const withScore = [];
  Object.entries(n.components).forEach(([key, c]) => {
    if (c.value == null || c.score == null || !NAT_DESCR[key]) return;
    li.push(`${esc(NAT_DESCR[key](c))} <span class="muted">(score ${fmt.n(c.score)})</span>`);
    withScore.push([key, c]);
  });
  if (withScore.length > 1) {
    const [, top] = withScore.slice().sort((a, b) => b[1].score - a[1].score)[0];
    li.push(`O sinal mais forte agora é <b>${esc(top.label)}</b> (score ${fmt.n(top.score)}).`);
  }
  return li.map((t) => `<li>${t}</li>`).join('');
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
    // Com eixos duplos e nome em cada eixo, a legenda ficaria por cima do nome do eixo direito
    // (ambos no canto superior direito): o nome do eixo já diz a que série pertence cada linha.
    legend: (series.length > 1 && !(opts.dual && opts.names)) ? { top: 0, right: 0, textStyle: { color: txt } } : undefined,
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
      const val = METRICS[k].f(nz(p[METRICS[k].prop]));
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
  const demoBits = [];
  if (m.density != null) {
    const md = median(col((x) => x.density));
    demoBits.push(`${fmt.n(m.density, 0)} hab/km²${md ? ` (mediana ${fmt.n(md, 0)})` : ''}`);
  }
  if (m.migration_balance != null) demoBits.push(`saldo migratório ${m.migration_balance >= 0 ? '+' : ''}${fmt.n(m.migration_balance, 0)}/ano`);
  if (m.ageing_index != null) demoBits.push(`índice de envelhecimento ${fmt.n(m.ageing_index, 0)} (idosos por 100 jovens)`);
  if (demoBits.length) {
    const thin = m.density != null && m.density < 50;
    li.push(`Contexto demográfico: ${demoBits.join(', ')}.${thin ? ' Densidade baixa costuma significar poucas transações por trimestre — um salto grande em percentagem pode ser só uma ou duas vendas, não uma tendência de mercado.' : ''}`);
  }
  if (m.fc_price != null) {
    const now = m.nowcast_price != null ? `Estimativa para hoje (${qpt(m.nowcast_period)}): ${fmt.eur(m.nowcast_price)}/m², ${fmt.spct(m.nowcast_price / m.price - 1)} face ao último valor publicado. ` : '';
    const band = m.fc_lo80 != null ? ` — com 80% de probabilidade entre ${fmt.eur(m.fc_lo80)} e ${fmt.eur(m.fc_hi80)}` : '';
    const err = m.fc_mae != null ? ` No passado recente, a previsão para este concelho errou em média ${fmt.n(m.fc_mae * 100, 1)} p.p.` : '';
    li.push(`${now}Previsão para ${qpt(m.fc_period)}: ${fmt.eur(m.fc_price)}/m² (${fmt.spct(m.fc_growth_12m)} em 12 meses)${band}.${err}`);
  }
  if (m.rent_fc != null) li.push(`Renda de novos contratos prevista para ${m.rent_fc_year}: ${fmt.eur2(m.rent_fc)}/m² (${fmt.spct(m.rent_fc_growth)}), intervalo de 80% entre ${fmt.eur2(m.rent_fc_lo80)} e ${fmt.eur2(m.rent_fc_hi80)} — confiança baixa (só 6 anos de dados).`);
  if (m.fv_gap != null) {
    const g = m.fv_gap;
    li.push(`Face ao valor justo (${fmt.eur(m.fv_price)}/m²): ${Math.abs(g) <= 0.15 ? 'em linha com concelhos de fundamentos parecidos' : `${fmt.spct(g, 0)} — ${g > 0 ? 'mais caro' : 'mais barato'} do que rendimento, demografia, litoral e região explicam`}.${g > 0.15 ? ' Pode ser sobrevalorização ou algo que o modelo não vê (praia, turismo, universidade, qualidade das casas).' : ''}`);
  }
  if (m.typology_name) li.push(`Tipologia: «${m.typology_name}» (ver "Perspetivas").`);
  if (m.new_premium != null) li.push(`Casas novas a ${fmt.eur(m.price_new)}/m² e existentes a ${fmt.eur(m.price_existing)}/m²: as novas custam ${fmt.spct(m.new_premium, 0)}${m.new_premium > 0.3 ? ' — um prémio alto, comum onde a construção nova é de gama alta' : ''}.`);
  const tp = [['apartamentos', m.val_apt, m.apt_fc_growth_12m, m.apt_fc_lo80, m.apt_fc_hi80], ['moradias', m.val_house, m.house_fc_growth_12m, m.house_fc_lo80, m.house_fc_hi80]]
    .filter((x) => x[1] != null)
    .map(([n, v, g, lo, hi]) => `${n} ${fmt.eur(v)}/m²${g != null ? ` (previsão ${fmt.spct(g)} em 12 meses${lo != null ? `, 80% entre ${fmt.eur(lo)} e ${fmt.eur(hi)}` : ''})` : ''}`);
  if (tp.length) li.push(`Avaliação bancária: ${tp.join('; ')}.`);
  if (m.foreign_premium != null) li.push(`Compradores com domicílio no estrangeiro pagam ${fmt.eur(m.price_foreign)}/m², ${fmt.spct(m.foreign_premium, 0)} face aos residentes em Portugal (${fmt.eur(m.price_domestic)}/m²)${m.foreign_premium > 0.3 ? ' — sinal de procura externa forte' : ''}.`);
  if (m.companies_premium != null) li.push(`Empresas e outras entidades pagam ${fmt.eur(m.price_companies)}/m², ${fmt.spct(m.companies_premium, 0)} face às famílias (${fmt.eur(m.price_households)}/m²)${m.companies_premium > 0.3 ? ' — sinal de compra para investimento' : ''}.`);
  const tps = [['T0/T1', m.price_t01], ['T2', m.price_t2], ['T3', m.price_t3], ['T4+', m.price_t4]].filter((x) => x[1] != null);
  if (tps.length >= 2) li.push(`Preço por tipologia: ${tps.map(([k, v]) => `${k} ${fmt.eur(v)}/m²`).join(', ')}${m.price_apt_sales != null ? `; apartamentos ${fmt.eur(m.price_apt_sales)}/m²` : ''}.`);
  if (m.val_count != null && m.val_count_growth_1y != null) {
    const vt = [['apartamentos', m.val_count_apt, m.val_count_apt_growth_1y], ['moradias', m.val_count_house, m.val_count_house_growth_1y]]
      .filter((x) => x[1] != null).map(([k, n, g]) => `${k} ${fmt.n(n, 0)} (${fmt.spct(g, 0)})`);
    li.push(`Volume: ${fmt.n(m.val_count, 0)} avaliações bancárias nos últimos 3 meses, ${fmt.spct(m.val_count_growth_1y, 0)} num ano${vt.length ? ` — ${vt.join(', ')}` : ''}${m.val_count_growth_1y < -0.15 ? '. Queda forte do volume, que costuma anteceder abrandamento de preços' : m.val_count_growth_1y > 0.15 ? '. Mais compras com crédito' : ''}.`);
  }
  if (m.rent_q1 != null && m.rent_q3 != null) li.push(`Renda de novos contratos: 25% abaixo de ${fmt.eur2(m.rent_q1)}/m² e 25% acima de ${fmt.eur2(m.rent_q3)}/m²${m.rent_contracts != null ? `, em ${fmt.n(m.rent_contracts, 0)} contratos em ${m.rent_contracts_year}` : ''}.`);
  if (m.tourism_pc != null) {
    const mt = median(col((x) => x.tourism_pc));
    li.push(`Pressão turística: ${fmt.n(m.tourism_pc, 1)} dormidas por habitante no ano${mt != null ? ` (mediana dos concelhos ${fmt.n(mt, 1)})` : ''}.`);
  }
  if (m.volatile) li.push('⚠ Poucos negócios: o preço é muito volátil e o score foi atenuado. Lê estes números com cautela.');
  return li.map((t) => `<li>${esc(t)}</li>`).join('');
}

// Leque: preço publicado + estimativa/previsão com faixas de 50% e 80% (um só eixo).
function fanChart(id, m) {
  const el = document.getElementById(id);
  const prev = echarts.getInstanceByDom(el);
  if (prev) prev.dispose();
  delete charts[id];
  el.innerHTML = '';
  const hist = (m.series.price || []).slice(-12), f = m.fc;
  if (!f || !f.mid.length || !hist.length) { el.innerHTML = '<p class="muted">Sem previsão para este concelho.</p>'; return; }
  const [p0, v0] = hist[hist.length - 1];
  const periods = [...hist.map((h) => h[0]), ...f.periods];
  const at = (arr) => [[p0, v0], ...f.periods.map((p, i) => [p, arr[i]])];
  const hasBand = f.lo80.every((x) => x != null);
  const s1 = css('--s1'), txt = css('--muted'), line = css('--line');
  const rgba = (hex, a) => `rgba(${[1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(',')},${a})`;
  const band = (lo, hi, name, op) => [
    { name, type: 'line', stack: name, data: at(lo), lineStyle: { opacity: 0 }, itemStyle: { color: rgba(s1, op) }, symbol: 'none', silent: true },
    { name, type: 'line', stack: name, data: at(hi).map(([p, v], i) => [p, v - at(lo)[i][1]]), lineStyle: { opacity: 0 }, symbol: 'none',
      itemStyle: { color: rgba(s1, op) }, areaStyle: { color: rgba(s1, op) }, silent: true },
  ];
  const nowIdx = f.kind.lastIndexOf('nowcast');
  const past = (m.fc_past || []).filter((x) => hist.some((h) => h[0] === x.target));
  const pastBy = Object.fromEntries(past.map((x) => [x.target, x]));
  const s2 = css('--s2');
  charts[id] = echarts.init(el);
  charts[id].setOption({
    animation: false,
    grid: { left: 56, right: 16, top: 34, bottom: 24 },
    legend: { top: 0, right: 0, textStyle: { color: txt },
      data: ['Publicado (INE)', 'Estimativa e previsão', ...(past.length ? ['Previsto antes'] : []),
        ...(hasBand ? [{ name: '80%', icon: 'rect' }, { name: '50%', icon: 'rect' }] : [])] },
    tooltip: {
      trigger: 'axis', confine: true,
      formatter: (ps) => {
        const p = (Array.isArray(ps) ? ps : [ps])[0].axisValue;
        const hi = hist.find((h) => h[0] === p), i = f.periods.indexOf(p);
        const pb = pastBy[p];
        if (hi) return `<b>${esc(qpt(p))}</b><br>Publicado: <b>${fmt.eur(hi[1])}/m²</b>` + (pb
          ? `<br>Previsto a ${esc(pb.issued.split('-').reverse().join('/'))} (${pb.h} trim. antes): ${fmt.eur(pb.mid)}` +
            (pb.lo80 != null ? `<br>80%: ${fmt.eur(pb.lo80)} – ${fmt.eur(pb.hi80)} · ${hi[1] >= pb.lo80 && hi[1] <= pb.hi80 ? 'acertou no intervalo' : 'fora do intervalo'}` : '')
          : '');
        if (i < 0) return '';
        const kind = f.kind[i] === 'nowcast' ? 'Estimativa (ainda não publicado)' : 'Previsão';
        return `<b>${esc(qpt(p))}</b> · ${kind}<br>Central: <b>${fmt.eur(f.mid[i])}/m²</b>` +
          (f.lo80[i] != null ? `<br>50%: ${fmt.eur(f.lo50[i])} – ${fmt.eur(f.hi50[i])}<br>80%: ${fmt.eur(f.lo80[i])} – ${fmt.eur(f.hi80[i])}` : '');
      },
    },
    xAxis: { type: 'category', data: periods, axisLabel: { color: txt, formatter: qpt }, axisLine: { lineStyle: { color: line } } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: txt, formatter: (v) => Math.round(v).toLocaleString('pt-PT') }, splitLine: { lineStyle: { color: line } } },
    series: [
      ...(hasBand ? [...band(f.lo80, f.hi80, '80%', 0.12), ...band(f.lo50, f.hi50, '50%', 0.22)] : []),
      { name: 'Publicado (INE)', type: 'line', data: hist, symbol: 'none', lineStyle: { width: 2, color: s1 }, itemStyle: { color: s1 } },
      ...(past.length ? [{ name: 'Previsto antes', type: 'scatter', data: past.map((x) => [x.target, x.mid]), symbolSize: 9,
        itemStyle: { color: s2, borderColor: css('--card'), borderWidth: 2 } }] : []),
      { name: 'Estimativa e previsão', type: 'line', data: at(f.mid), symbol: 'circle', symbolSize: 8, showSymbol: true,
        lineStyle: { width: 2, type: 'dashed', color: s1 }, itemStyle: { color: s1 },
        markLine: nowIdx >= 0 ? { silent: true, symbol: 'none', lineStyle: { type: 'solid', color: txt, width: 1 },
          label: { formatter: 'hoje', color: txt, fontSize: 10 }, data: [{ xAxis: f.periods[nowIdx] }] } : undefined },
    ],
  }, true);
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
    tile('p2i', 'Preço/rendimento (meses)', fmt.n(m.price_to_income_months, 1), ctx((x) => x.price_to_income_months, m.price_to_income_months, (v) => fmt.n(v, 1))),
    tile('r2i', 'Renda/rendimento', fmt.pct(m.rent_to_income, 1), ctx((x) => x.rent_to_income, m.rent_to_income, (v) => fmt.pct(v, 1))),
    tile('score_valuation', 'Score valorização', fmt.n(m.score_valuation)),
    tile('score_overall', 'Score global', fmt.n(m.score_overall)),
    ...(m.nowcast_price != null ? [tile('nowcast', `Estimativa hoje (${qpt(m.nowcast_period)})`, fmt.eur(m.nowcast_price) + '/m²',
      `<span class="ctx">${fmt.spct(m.nowcast_price / m.price - 1)} face ao último publicado</span>`)] : []),
    ...(m.fc_price != null ? [tile('fc12', `Previsão ${qpt(m.fc_period)}`, fmt.eur(m.fc_price) + '/m²',
      `<span class="ctx">${fmt.spct(m.fc_growth_12m)} em 12 meses${m.fc_lo80 != null ? ` · 80%: ${fmt.eur(m.fc_lo80)}–${fmt.eur(m.fc_hi80)}` : ''}</span>`)] : []),
    ...(m.rent_fc != null ? [tile('rent_fc', `Renda prevista ${m.rent_fc_year}`, fmt.eur2(m.rent_fc) + '/m²',
      `<span class="ctx">${fmt.spct(m.rent_fc_growth)} · 80%: ${fmt.eur2(m.rent_fc_lo80)}–${fmt.eur2(m.rent_fc_hi80)}</span>`)] : []),
    ...(m.fv_gap != null ? [tile('fv', 'Face ao valor justo', fmt.spct(m.fv_gap, 0),
      `<span class="ctx">valor justo ${fmt.eur(m.fv_price)}/m²</span>`)] : []),
    ...(m.price_new != null || m.price_existing != null ? [tile('new_old', 'Novas / existentes', `${fmt.eur(m.price_new)} / ${fmt.eur(m.price_existing)}`,
      m.new_premium != null ? `<span class="ctx">novas ${fmt.spct(m.new_premium, 0)} face às existentes</span>` : '')] : []),
    ...[['val_apt', 'apt', 'Apartamentos'], ['val_house', 'house', 'Moradias']].filter(([k]) => m[k] != null).map(([k, p, label]) =>
      tile('val_type', `${label} (avaliação)`, fmt.eur(m[k]) + '/m²',
        `<span class="ctx">${fmt.spct(m[k + '_growth_1y'])} num ano${m[p + '_fc_growth_12m'] != null ? ` · prev. ${fmt.spct(m[p + '_fc_growth_12m'])}` : ''}</span>`)),
    ...(m.rent_q1 != null ? [tile('rent_q', 'Renda 1.º–3.º quartil', `${fmt.eur2(m.rent_q1)}–${fmt.eur2(m.rent_q3)}`,
      m.rent_contracts != null ? `<span class="ctx">${fmt.n(m.rent_contracts, 0)} contratos em ${m.rent_contracts_year}</span>` : '')] : []),
    ...(m.foreign_premium != null ? [tile('foreign', 'Estrangeiros vs residentes', fmt.spct(m.foreign_premium, 0),
      `<span class="ctx">${fmt.eur(m.price_foreign)} vs ${fmt.eur(m.price_domestic)}/m²</span>`)] : []),
    ...(m.companies_premium != null ? [tile('companies', 'Empresas vs famílias', fmt.spct(m.companies_premium, 0),
      `<span class="ctx">${fmt.eur(m.price_companies)} vs ${fmt.eur(m.price_households)}/m²</span>`)] : []),
    ...(m.price_t2 != null || m.price_t3 != null ? [tile('tipologia', 'T2 / T3 (€/m²)', `${fmt.eur(m.price_t2)} / ${fmt.eur(m.price_t3)}`,
      `<span class="ctx">T0/T1 ${fmt.eur(m.price_t01)} · T4+ ${fmt.eur(m.price_t4)}</span>`)] : []),
    ...(m.val_count != null ? [tile('val_count', 'Avaliações (3 meses)', fmt.n(m.val_count, 0),
      `<span class="ctx">${fmt.spct(m.val_count_growth_1y, 0)} num ano${m.val_count_apt != null || m.val_count_house != null
        ? ` · apart. ${fmt.n(m.val_count_apt, 0)} (${fmt.spct(m.val_count_apt_growth_1y, 0)}) · morad. ${fmt.n(m.val_count_house, 0)} (${fmt.spct(m.val_count_house_growth_1y, 0)})` : ''}</span>`)] : []),
    ...(m.tourism_pc != null ? [tile('tourism', 'Dormidas por habitante', fmt.n(m.tourism_pc, 1),
      ctx((x) => x.tourism_pc, m.tourism_pc, (v) => fmt.n(v, 1)))] : []),
    ...(m.housing_credit_pc != null ? [tile('credit_pc', 'Crédito habitação/hab.', fmt.eur(m.housing_credit_pc),
      ctx((x) => x.housing_credit_pc, m.housing_credit_pc, fmt.eur))] : []),
  ].join('');
  $('#d-read').innerHTML = readList(m);
  const s = [{ name: 'Preço', data: m.series.price, fmt: (v) => fmt.eur(v) + '/m²' }];
  const q4 = (p) => (p.length === 4 ? p + 'Q4' : p);
  if (m.series.rent.length) s.push({ name: 'Renda', data: m.series.rent.map(([p, v]) => [q4(p), v]), axis: 1, dots: true, fmt: (v) => fmt.eur2(v) + '/m²/mês' });
  $('#d-fc-wrap').hidden = !m.fc;
  $('#d-fc-note').textContent = m.fc ? `Estimativa e previsão calculadas em ${OL && OL.build_date ? OL.build_date : '—'} com dados do INE até ${qpt(OL && OL.sales ? OL.sales.origin : '')} (vendas) e ${OL && OL.sales && OL.sales.last_valuation ? OL.sales.last_valuation : '—'} (avaliação bancária). Ver "Perspetivas" para o erro no passado.` : '';
  try {
    lineChart('chart-detail', 'Evolução', s, { dual: s.length > 1, names: s.length > 1 ? ['Preço (€/m²)', 'Renda (€/m²/mês)'] : ['Preço (€/m²)'], notitle: true });
  } catch (e) { console.error('Falha no gráfico do detalhe:', e); }
  if (m.fc) try { fanChart('chart-fc', m); } catch (e) { console.error('Falha no gráfico da previsão:', e); }
  $('#d-compare').textContent = compare.includes(dico) ? 'Remover da comparação' : 'Comparar';
  if (scroll) $('#detail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
const COMPARE_ROWS = [
  ['price', 'Preço mediano', (m) => fmt.eur(m.price) + '/m²'],
  ['g1y', 'Variação 12 meses', (m) => fmt.pct(m.price_growth_1y)],
  ['g3y', 'Variação 3 anos', (m) => fmt.pct(m.price_growth_3y)],
  ['rent', 'Renda (novos contratos)', (m) => (m.rent == null ? '—' : fmt.eur2(m.rent) + '/m²')],
  ['yield', 'Rendibilidade bruta', (m) => fmt.pct(m.gross_yield, 2)],
  ['p2r', 'Preço/renda (anos)', (m) => fmt.n(m.price_to_rent_years, 1)],
  ['p2i', 'Preço/rendimento (meses)', (m) => fmt.n(m.price_to_income_months, 1)],
  ['r2i', 'Renda/rendimento', (m) => (m.rent_to_income == null ? '—' : fmt.pct(m.rent_to_income, 1))],
  ['migration', 'Saldo migratório', (m) => (m.migration_balance == null ? '—' : (m.migration_balance >= 0 ? '+' : '') + fmt.n(m.migration_balance, 0))],
  ['score_overall', 'Score global', (m) => fmt.n(m.score_overall)],
  ['nowcast', 'Estimativa hoje', (m) => (m.nowcast_price == null ? '—' : fmt.eur(m.nowcast_price) + '/m²')],
  ['fc12', 'Previsão 12 meses', (m) => (m.fc_growth_12m == null ? '—' : `${fmt.spct(m.fc_growth_12m)} (${fmt.eur(m.fc_price)})`)],
  ['rent_fc', 'Renda prevista', (m) => (m.rent_fc == null ? '—' : `${fmt.eur2(m.rent_fc)}/m² (${fmt.spct(m.rent_fc_growth)})`)],
  ['fv', 'Face ao valor justo', (m) => fmt.spct(m.fv_gap, 0)],
  ['typology', 'Tipologia', (m) => esc(m.typology_name || '—')],
  ['new_old', 'Novas / existentes (€/m²)', (m) => (m.price_new == null && m.price_existing == null ? '—' : `${fmt.eur(m.price_new)} / ${fmt.eur(m.price_existing)}`)],
  ['val_type', 'Apartamentos: avaliação e previsão', (m) => (m.val_apt == null ? '—' : `${fmt.eur(m.val_apt)} (${fmt.spct(m.apt_fc_growth_12m)})`)],
  ['val_type', 'Moradias: avaliação e previsão', (m) => (m.val_house == null ? '—' : `${fmt.eur(m.val_house)} (${fmt.spct(m.house_fc_growth_12m)})`)],
  ['rent_q', 'Renda 1.º–3.º quartil', (m) => (m.rent_q1 == null ? '—' : `${fmt.eur2(m.rent_q1)}–${fmt.eur2(m.rent_q3)}`)],
  ['foreign', 'Estrangeiros vs residentes', (m) => (m.foreign_premium == null ? '—' : `${fmt.spct(m.foreign_premium, 0)} (${fmt.eur(m.price_foreign)})`)],
  ['companies', 'Empresas vs famílias', (m) => (m.companies_premium == null ? '—' : `${fmt.spct(m.companies_premium, 0)} (${fmt.eur(m.price_companies)})`)],
  ['tipologia', 'T0-T1 / T2 / T3 / T4+ (€/m²)', (m) => [m.price_t01, m.price_t2, m.price_t3, m.price_t4].map(fmt.eur).join(' / ')],
  ['val_count', 'Avaliações bancárias (3 meses)', (m) => (m.val_count == null ? '—' : `${fmt.n(m.val_count, 0)} (${fmt.spct(m.val_count_growth_1y, 0)})`)],
  ['val_count', 'Avaliações: apartamentos / moradias', (m) => (m.val_count_apt == null && m.val_count_house == null ? '—'
    : `${fmt.n(m.val_count_apt, 0)} (${fmt.spct(m.val_count_apt_growth_1y, 0)}) / ${fmt.n(m.val_count_house, 0)} (${fmt.spct(m.val_count_house_growth_1y, 0)})`)],
  ['tourism', 'Dormidas por habitante', (m) => fmt.n(m.tourism_pc, 1)],
  ['credit_pc', 'Crédito habitação/hab.', (m) => fmt.eur(m.housing_credit_pc)],
];
let compareMetric = 'price';
function renderCompare() {
  $('#compare').hidden = compare.length === 0;
  if (!compare.length) return;
  $('#c-chips').innerHTML = compare.map((d) => `<span class="chip" data-d="${esc(d)}">${esc(BY[d].name)} ✕</span>`).join('');
  $('#c-hint').textContent = compare.length < 2
    ? 'Escolhe outro concelho (no mapa ou no ranking) e clica em "Comparar" para o juntar. Máximo 4.'
    : compare.length >= 4 ? 'Máximo de 4 concelhos atingido. Clica num concelho acima para o remover.' : 'Podes juntar mais concelhos (máximo 4).';
  const label = compareMetric === 'rent' ? 'Renda' : 'Preço';
  const has = (d) => new Map(BY[d].series[compareMetric]);
  const maps = compare.map((d) => [d, has(d)]);
  const periods = [...new Set(compare.flatMap((d) => BY[d].series[compareMetric].map((p) => p[0])))].sort();
  const base = periods.find((p) => maps.every(([, m]) => m.has(p)));   // 1.º período com dados em todos
  const series = maps.map(([d, m]) => ({
    name: BY[d].name,
    data: periods.filter((p) => base && p >= base).map((p) => [p, m.has(p) ? +((m.get(p) / m.get(base)) * 100).toFixed(2) : null]),
  }));
  $('#c-table').innerHTML = `<thead><tr><th style="text-align:left">Indicador</th>${compare.map((d) => `<th>${esc(BY[d].name)}</th>`).join('')}</tr></thead>` +
    `<tbody>${COMPARE_ROWS.map(([k, rlabel, f]) => `<tr><td style="text-align:left">${rlabel} ${info(k)}</td>${compare.map((d) => `<td>${f(BY[d])}</td>`).join('')}</tr>`).join('')}</tbody>`;
  // Isolado do resto: uma falha no gráfico (ex. biblioteca de gráficos bloqueada) não deve esconder a tabela acima.
  try {
    const fC = (v) => `${fmt.n(v, 0)} (${v >= 100 ? '+' : '−'}${fmt.n(Math.abs(v - 100), 1)}% desde a base)`;
    lineChart('chart-compare', label, series.map((x) => ({ ...x, fmt: fC })), { names: [base ? `${label}, base 100 em ${base}` : label], refs: [{ y: 100, label: 'base' }], notitle: true });
    if (!base) $('#chart-compare').innerHTML = `<p class="muted">Estes concelhos não têm nenhum período de ${label.toLowerCase()} em comum.</p>`;
  } catch (e) { console.error('Falha no gráfico de comparação:', e); }
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

// ---------- perspetivas
function freshChart(id) {
  const el = document.getElementById(id);
  const prev = echarts.getInstanceByDom(el);
  if (prev) prev.dispose();
  el.innerHTML = '';
  charts[id] = echarts.init(el);
  return charts[id];
}
function barChart(id, cats, series, f, titles) {
  const txt = css('--muted'), line = css('--line');
  freshChart(id).setOption({
    animation: false,
    grid: { left: 8, right: 12, top: 34, bottom: 8, containLabel: true },
    legend: { top: 0, right: 0, textStyle: { color: txt } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, confine: true,
      formatter: (ps) => `<b>${esc((titles || {})[ps[0].axisValue] || ps[0].axisValue)}</b><br>` +
        ps.map((p) => `${p.marker} ${esc(p.seriesName)}: <b>${esc(f(p.value))}</b>`).join('<br>') },
    xAxis: { type: 'category', data: cats, axisLabel: { color: txt, interval: 0, fontSize: 11 }, axisLine: { lineStyle: { color: line } } },
    yAxis: { type: 'value', axisLabel: { color: txt, formatter: (v) => f(v) }, splitLine: { lineStyle: { color: line } } },
    series: series.map((s) => ({ name: s.name, type: 'bar', barMaxWidth: 24, barGap: '15%', itemStyle: { color: s.color },
      data: s.data.map((v) => ({ value: v, itemStyle: { borderRadius: v < 0 ? [0, 0, 4, 4] : [4, 4, 0, 0] } })) })),
  }, true);
}
function regimesChart(id, R) {
  const txt = css('--muted'), line = css('--line'), s1 = css('--s1'), s2 = css('--s2');
  const segs = R.segments.map((sg, i) => {
    const pts = R.fit.filter((x) => x[2] === i).map((x) => [x[0], x[1]]);
    const mid = pts[Math.floor(pts.length / 2)];
    return { name: 'Tendência por fase', type: 'line', data: pts, symbol: 'none', lineStyle: { width: 2, type: 'dashed', color: s2 }, itemStyle: { color: s2 },
      markPoint: { symbol: 'circle', symbolSize: 1, itemStyle: { color: 'transparent' },
        label: { show: true, position: 'top', offset: [-14, -12], color: txt, fontSize: 11, formatter: `${fmt.spct(sg.growth_ann, 1)}/ano` }, data: [{ coord: mid }] } };
  });
  freshChart(id).setOption({
    animation: false,
    grid: { left: 46, right: 12, top: 34, bottom: 24 },
    legend: { top: 0, right: 0, textStyle: { color: txt }, data: ['HPI nominal', 'Tendência por fase'] },
    tooltip: { trigger: 'axis', confine: true, formatter: (ps) => {
      const p = ps[0].axisValue, v = R.series.find((x) => x[0] === p);
      const sg = R.segments.find((s) => s.start <= p && p <= s.end);
      return `<b>${esc(qpt(p))}</b><br>HPI: <b>${v ? fmt.n(v[1], 1) : '—'}</b>` + (sg ? `<br>Fase ${esc(qpt(sg.start))}–${esc(qpt(sg.end))}: ${fmt.spct(sg.growth_ann)}/ano` : '');
    } },
    xAxis: { type: 'category', data: R.series.map((x) => x[0]), axisLabel: { color: txt, formatter: qpt }, axisLine: { lineStyle: { color: line } } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: txt }, splitLine: { lineStyle: { color: line } } },
    series: [{ name: 'HPI nominal', type: 'line', data: R.series, symbol: 'none', lineStyle: { width: 2, color: s1 }, itemStyle: { color: s1 } }, ...segs],
  }, true);
}
const lnk = (d, name) => `<a href="#" class="lnk" data-d="${esc(d)}">${esc(name)}</a>`;
const pp = (v) => (v == null ? '—' : fmt.n(v * 100, 1) + ' p.p.');
function olSales(S) {
  const nowG = median(col((x) => (x.nowcast_price != null && x.price ? x.nowcast_price / x.price - 1 : null)));
  const intro = [];
  if (S.nowcast_period && nowG != null) {
    intro.push(`<b>Hoje (${qpt(S.nowcast_period)}):</b> no concelho típico, o preço estimado está ${fmt.spct(nowG)} acima do último valor publicado pelo INE (${qpt(S.origin)}) — estimativa feita com a avaliação bancária até ${esc(S.last_valuation)}.`);
  }
  if (S.median_growth_12m != null) {
    intro.push(`<b>Próximos 12 meses (até ${qpt(S.target_period)}):</b> previsão central mediana de ${fmt.spct(S.median_growth_12m)}; metade dos concelhos entre ${fmt.spct(S.p25_growth_12m)} e ${fmt.spct(S.p75_growth_12m)}; ${Math.round(S.share_up * 100)}% com subida prevista.`);
  }
  const regions = (S.by_region || []).map((r) => `<tr><td>${esc(r.name)}</td><td>${r.n}</td><td>${fmt.spct(r.median)}</td><td>${fmt.spct(r.p25)} a ${fmt.spct(r.p75)}</td></tr>`).join('');
  const ok = MUNIS.filter((m) => m.fc_growth_12m != null && !m.volatile);
  const item = (m) => `<li><span>${lnk(m.dico, m.name)}</span><span class="v">${fmt.spct(m.fc_growth_12m)} <span class="muted">${m.fc_lo80 != null ? `(${fmt.eur(m.fc_lo80)}–${fmt.eur(m.fc_hi80)})` : ''}</span></span></li>`;
  const top = ok.slice().sort((a, b) => b.fc_growth_12m - a.fc_growth_12m).slice(0, 8).map(item).join('');
  const bottom = ok.slice().sort((a, b) => a.fc_growth_12m - b.fc_growth_12m).slice(0, 8).map(item).join('');
  const bt = S.backtest || {};
  const rows = (S.horizons || []).filter((h) => bt[String(h.h)]).map((h) => {
    const m = bt[String(h.h)], nv = m.best_naive;
    const tag = h.h === S.h_now ? ' · <b>hoje</b>' : String(h.period) === String(S.target_period) ? ' · <b>12 meses</b>' : '';
    const cov = m.coverage80 == null ? '—' : fmt.pct(m.coverage80, 0);
    return `<tr><td>${qpt(h.period)} (${h.h} trim.)${tag}</td><td><b>${pp(m.mae_model)}</b></td><td>${pp(m.mae_rw)}</td><td>${pp(m.mae_drift)}</td>` +
      `<td>${pp(m.mdae_model)} / ${pp(m['mdae_' + nv])}</td><td>${m.skill == null ? '—' : fmt.spct(m.skill, 0)}</td><td>${cov}</td></tr>`;
  }).join('');
  const coefs = (S.coefficients || []).slice(0, 4).map((c) => `${esc(c.label)} (${c.coef_std >= 0 ? 'quanto maior, mais subida' : 'quanto maior, menos subida'})`);
  return `<p class="verdict">${intro.join('<br>')}</p>
    <h3>Preço de venda: estimativa para hoje e próximos 12 meses ${info('fc12')}</h3>
    <div class="table-wrap"><table class="ol-table"><thead><tr><th>Região</th><th>Concelhos</th><th>Previsão mediana 12m</th><th>Metade dos concelhos entre</th></tr></thead><tbody>${regions}</tbody></table></div>
    <div class="ol-cols">
      <div><p class="muted"><b>Maior subida prevista</b> (intervalo de 80% em €/m²)</p><ul class="ol-list">${top}</ul></div>
      <div><p class="muted"><b>Menor subida prevista</b> (intervalo de 80% em €/m²)</p><ul class="ol-list">${bottom}</ul></div>
    </div>
    <p class="muted">Excluídos das listas os concelhos com dados voláteis (⚠). Clica num concelho para ver o leque da previsão.${coefs.length ? ` O que mais pesa na previsão, mantendo o resto igual: ${coefs.join('; ')}.` : ''}</p>
    <h3>Como se saiu no passado ${info('ol_backtest')}</h3>
    <div class="table-wrap"><table class="ol-table"><thead><tr><th>Alvo</th><th>Erro médio: modelo</th><th>«Fica igual»</th><th>«Continua o ritmo»</th><th>Concelho típico: modelo / ingénua</th><th>Menos erro</th><th>Cobertura 80%</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${S.verdict_nowcast_pt ? `<p>${esc(S.verdict_nowcast_pt)}</p>` : ''}<p>${esc(S.verdict_pt)}</p>`;
}
function olTracking(T) {
  const d = (s) => (s ? s.split('-').reverse().join('/') : '—');
  const head = `<h3>Previsões anteriores vs realidade ${info('tracking')}</h3>`;
  if (!T.n_evaluated) {
    const next = (T.next_targets || []).map(qpt).join(' e ');
    return `${head}<p>Arquivo iniciado a ${d(T.first_issued)}: ${T.n_archived} previsões guardadas (${T.n_vintages} ${T.n_vintages === 1 ? 'conjunto' : 'conjuntos'} de dados), à espera dos valores reais.${next ? ` A primeira avaliação aparece quando o INE publicar ${next}.` : ''}</p>`;
  }
  const row = (label, m) => `<tr><td>${label}</td><td>${m.n_vintages}</td><td>${m.n}</td><td><b>${pp(m.mae_model)}</b></td><td>${pp(m.mae_naive)}</td>` +
    `<td>${m.skill == null ? '—' : fmt.spct(m.skill, 0)}</td><td>${fmt.pct(m.coverage80, 0)}</td><td>${fmt.spct(m.bias)}</td></tr>`;
  const rows = (T.sales || []).map((m) => row(`Venda, ${m.h} trim. à frente <span class="muted">(${m.targets.map(qpt).join(', ')})</span>`, m)).join('') +
    (T.rent ? row(`Renda, 1 ano <span class="muted">(${T.rent.targets.join(', ')})</span>`, T.rent) : '');
  const all = (T.sales || []);
  const n = all.reduce((a, m) => a + m.n, 0);
  const cov = n ? all.reduce((a, m) => a + m.coverage80 * m.n, 0) / n : null;
  const small = all.reduce((a, m) => Math.max(a, m.n_vintages), 0) < 4;
  return `${head}<p>${n} previsões de preço já confrontadas com o valor publicado pelo INE; o intervalo de 80% conteve o valor real em ${fmt.pct(cov, 0)} dos casos (o esperado é ~80%). ${T.n_pending} previsões ainda à espera de dados.${small ? ' <b>Amostra ainda pequena</b>: poucos conjuntos de dados, todos sob a mesma conjuntura nacional — não tire conclusões fortes.' : ''}</p>
    <div class="table-wrap"><table class="ol-table"><thead><tr><th>Previsão</th><th>Conjuntos de dados</th><th>Casos</th><th>Erro médio: modelo</th><th>«Fica igual»</th><th>Menos erro</th><th>Cobertura 80%</th><th>Enviesamento</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="muted">Enviesamento positivo = previsões acima do valor real. No detalhe de cada concelho, o leque mostra as previsões passadas (pontos laranja) ao lado do valor publicado.</p>`;
}
function olTypes(A, H) {
  const rows = [['Apartamentos', A, 'apt_fc_growth_12m', 'val_apt'], ['Moradias', H, 'house_fc_growth_12m', 'val_house']].filter(([, S]) => S && S.n_concelhos);
  if (!rows.length) return '';
  const tr = rows.map(([label, S, gk, vk]) => {
    const m = (S.backtest || {})[String(S.horizons[S.horizons.length - 1].h)] || {};
    const vals = col((x) => x[vk]);
    return `<tr><td>${label}</td><td>${S.n_concelhos}</td><td>${fmt.eur(median(vals))}</td><td><b>${fmt.spct(S.median_growth_12m)}</b></td>` +
      `<td>${fmt.spct(S.p25_growth_12m)} a ${fmt.spct(S.p75_growth_12m)}</td><td>${m.n_origins ?? '—'}</td>` +
      `<td>${m.skill == null ? '—' : fmt.spct(m.skill, 0)}</td><td>${m.coverage80 == null ? '—' : fmt.pct(m.coverage80, 0)}</td></tr>`;
  }).join('');
  const S0 = rows[0][1];
  return `<h3>Apartamentos e moradias ${info('val_type')}</h3>
    <p>Previsão a 12 meses (até ${qpt(S0.target_period)}) da avaliação bancária por tipo de casa. Usa 15 anos de dados mensais (desde 2011, crise incluída), por isso o backtest é muito mais longo do que o das vendas.</p>
    <div class="table-wrap"><table class="ol-table"><thead><tr><th>Tipo</th><th>Concelhos</th><th>Avaliação mediana (€/m²)</th><th>Previsão mediana 12m</th><th>Metade dos concelhos entre</th><th>Origens no backtest</th><th>Menos erro que a melhor regra ingénua</th><th>Cobertura 80%</th></tr></thead><tbody>${tr}</tbody></table></div>
    ${rows.map(([label, S]) => `<p><b>${label}:</b> ${esc(S.verdict_pt)}</p>`).join('')}`;
}
function olDemand(D) {
  const parts = [];
  if (D.volume) {
    const v = D.volume;
    const bt = v.by_type || {};
    const types = [['apartamentos', bt.apartments], ['moradias', bt.houses]].filter(([, x]) => x)
      .map(([k, x]) => `${k} ${fmt.n(x.total, 0)} (${fmt.spct(x.total_growth_1y, 0)}; caiu em ${Math.round(x.share_falling * 100)}% dos concelhos)`);
    parts.push(`<p><b>Volume ${info('val_count')}:</b> ${fmt.n(v.total, 0)} avaliações bancárias nos últimos 3 meses nos ${v.n} concelhos com dados, ${fmt.spct(v.total_growth_1y, 0)} face a um ano antes; o volume caiu em ${Math.round(v.share_falling * 100)}% dos concelhos (variação mediana ${fmt.spct(v.median_growth_1y, 0)}). ${v.share_falling > 0.6 && v.total_growth_1y < -0.1 ? 'Queda generalizada — historicamente um sinal de arrefecimento que costuma chegar antes dos preços.' : v.total_growth_1y > 0 ? 'Sem sinal de arrefecimento pelo lado do volume.' : 'Ligeiro abrandamento do volume; a acompanhar.'}${types.length ? ` Por tipo: ${types.join('; ')}.` : ''}</p>`);
  }
  if (D.foreign) {
    const f = D.foreign;
    const item = (x) => `<li><span>${lnk(x.dico, x.name)}</span><span class="v">${fmt.spct(x.premium, 0)} <span class="muted">${fmt.eur(x.price_foreign)} vs ${fmt.eur(x.price_domestic)}</span></span></li>`;
    parts.push(`<p><b>Compradores estrangeiros ${info('foreign')}:</b> em ${f.n} concelhos com dados, quem tem domicílio fiscal no estrangeiro paga em mediana ${fmt.spct(f.median_premium, 0)} por m² face a quem reside em Portugal; pagam mais em ${Math.round(f.share_above * 100)}% desses concelhos. O mapa tem este indicador ("Prémio pago por estrangeiros").</p>
      <p class="muted"><b>Maior prémio pago por estrangeiros</b> (estrangeiros vs residentes, €/m²)</p><ul class="ol-list">${f.top.map(item).join('')}</ul>`);
  }
  if (D.companies) {
    const c = D.companies;
    const item = (x) => `<li><span>${lnk(x.dico, x.name)}</span><span class="v">${fmt.spct(x.premium, 0)} <span class="muted">${fmt.eur(x.price_companies)} vs ${fmt.eur(x.price_households)}</span></span></li>`;
    parts.push(`<p><b>Empresas vs famílias ${info('companies')}:</b> em ${c.n} concelhos com dados, empresas e outras entidades pagam em mediana ${fmt.spct(c.median_premium, 0)} por m² face às famílias; pagam mais em ${Math.round(c.share_above * 100)}% desses concelhos.</p>
      <p class="muted"><b>Maior prémio pago por empresas</b> (empresas vs famílias, €/m²)</p><ul class="ol-list">${c.top.map(item).join('')}</ul>`);
  }
  return parts.length ? `<h3>Procura: volume, estrangeiros e empresas</h3>${parts.join('')}` : '';
}
function olRent(R) {
  const m = R.backtest;
  const ok = MUNIS.filter((x) => x.rent_fc_growth != null);
  const first = Math.min(...MUNIS.map((x) => (x.series.rent.length ? Number(x.series.rent[0][0]) : Infinity)));
  return `<h3>Rendas: próximo ano ${info('rent_fc')}</h3>
    <p>Renda de novos contratos prevista para ${esc(R.target_year)}${R.target_in_progress ? ' (ano em curso)' : ''}, em ${ok.length} concelhos: variação mediana de <b>${fmt.spct(R.median_growth)}</b> face a ${esc(R.origin_year)}; metade dos concelhos entre ${fmt.spct(R.p25_growth)} e ${fmt.spct(R.p75_growth)}. Os valores e intervalos de cada concelho estão no detalhe e na comparação.</p>
    ${m ? `<p>${esc(R.verdict_pt)}</p>` : ''}
    <p class="muted">Confiança baixa: só há renda anual por concelho desde ${Number.isFinite(first) ? first : '—'} — o backtest tem ${m ? m.n_origins : 0} anos.</p>`;
}
function olTypologies(T) {
  const split = qpt(T.split);
  const cards = T.clusters.map((c) => `<div class="tcard"><b>${c.id}. ${esc(c.name)}</b>${c.n} concelhos · preço mediano ${fmt.eur(c.price_median)}/m² (${fmt.spct(c.level_vs_median, 0)} face à mediana)<br>
    Subida anual: ${fmt.spct(c.growth_before)} até ${split} → ${fmt.spct(c.growth_after)} desde então.
    ${c.valuation_2011_2013 != null ? `<br>Na crise (2011–2013), a avaliação bancária variou ${fmt.spct(c.valuation_2011_2013)} (${c.valuation_2011_2013_n} concelhos com dados).` : ''}
    <br><span class="muted">Mais típicos: ${c.examples.map((e) => lnk(e.dico, e.name)).join(', ')}</span></div>`).join('');
  const q = T.silhouette >= 0.5 ? 'clara' : T.silhouette >= 0.25 ? 'moderada' : 'fraca';
  return `<h3>Tipologias de mercado ${info('typology')}</h3>
    <p>${T.n} concelhos agrupados em ${T.k} tipos pelo nível do preço e pelo ritmo de subida antes e depois de ${split} (início da subida dos juros do BCE). Separação entre grupos ${q} (silhueta ${fmt.n(T.silhouette, 2)}; 0 = sem estrutura, 1 = grupos perfeitos).</p>
    <div id="ol-typo" class="chart"></div><div class="cards">${cards}</div>`;
}
function olRipple(R) {
  const bands = R.bands.filter((b) => b.growth_after != null);
  const lagB = R.bands.filter((b) => b.best_lag_months != null);
  let lagTxt = '';
  if (lagB.length >= 2) {
    const maxLag = Math.max(...lagB.map((b) => b.best_lag_months));
    const corr = lagB.map((b) => `${esc(b.band)}: ${fmt.n(b.peak_corr, 2)}${b.n_lag < 10 ? ` (só ${b.n_lag} concelhos)` : ''}`).join('; ');
    lagTxt = maxLag <= 2
      ? `Sem atraso detetável: a variação anual da avaliação bancária de cada concelho acompanha a da metrópole mais próxima no mesmo mês (desfasamento ótimo de 0 a ${maxLag} meses em todas as faixas). O que muda com a distância é a força da ligação (correlação): ${corr}.`
      : `Desfasamento que melhor liga cada faixa à metrópole mais próxima: ${lagB.map((b) => `${esc(b.band)}: ${b.best_lag_months} meses`).join('; ')}. Correlação: ${corr}.`;
  }
  const g = bands.length >= 2 ? `Subida anual mediana desde ${qpt(R.split)}, por distância a Lisboa/Porto: ${bands.map((b) =>
    `${esc(b.band)} ${fmt.spct(b.growth_after)}${b.n_growth < 10 ? ` (só ${b.n_growth} concelhos)` : ''}`).join('; ')}.` : '';
  return `<h3>Distância a Lisboa e Porto: há efeito de propagação? ${info('ripple')}</h3>
    <p>${g} ${lagTxt}</p>${bands.length ? '<div id="ol-ripple" class="chart"></div>' : ''}<p class="muted">Ilhas excluídas. Cada concelho é comparado com a metrópole mais próxima (Lisboa ou Porto).</p>`;
}
function olFair(F) {
  const eff = F.effects.map((e) => e.kind === 'elasticity'
    ? `+10% de ${esc(e.label)} → ${fmt.spct(e.effect_10pct)} no preço`
    : e.feature === 'coastal' ? `estar no litoral → ${fmt.spct(e.effect_unit, 0)} no preço` : `${esc(e.label)} → ${fmt.spct(e.effect_unit, 2)} no preço`);
  const item = (x) => `<li><span>${lnk(x.dico, x.name)}${x.volatile ? ' ⚠' : ''}${x.coastal ? ' <span class="muted">(litoral)</span>' : ''}</span><span class="v">${fmt.spct(x.gap, 0)} <span class="muted">${fmt.eur(x.price)} vs ${fmt.eur(x.fv_price)}</span></span></li>`;
  return `<h3>Valor justo: o que os fundamentos explicam ${info('fv')}</h3>
    <p>Rendimento, densidade, envelhecimento, migração, litoral, distância a Lisboa/Porto e região explicam <b>${fmt.pct(F.r2_cv, 0)}</b> das diferenças de preço entre ${F.n} concelhos (validação cruzada: medido em concelhos que o modelo não viu). ${Math.round(F.share_within_20pct * 100)}% dos concelhos estão a menos de 20% do seu valor justo. Mantendo o resto igual: ${eff.join('; ')}.</p>
    <div class="ol-cols">
      <div><p class="muted"><b>Mais acima do valor justo</b> (preço vs valor justo, €/m²)</p><ul class="ol-list">${F.top_above.map(item).join('')}</ul></div>
      <div><p class="muted"><b>Mais abaixo do valor justo</b></p><ul class="ol-list">${F.top_below.map(item).join('')}</ul></div>
    </div>
    <p class="muted">Um desvio grande não é prova de bolha: pode ser praia, turismo, universidade ou qualidade das casas, que o modelo não vê. A deteção do litoral a partir das fronteiras simplificadas falha alguns casos (ex.: a costa de Alcácer do Sal). O mapa tem este indicador ("Preço face ao valor justo").</p>`;
}
function olRates(R) {
  const rows = R.shocks.map((s) => `<tr><td>Euribor ${s.shock > 0 ? '+' : '−'}${fmt.n(Math.abs(s.shock), 0)} p.p.</td><td>${fmt.spct(s.payment_change)}</td><td>${fmt.spct(s.capacity_change)}</td>` +
    `<td>${s.price_effect_12m != null ? `${fmt.spct(s.price_effect_12m)} <span class="muted">(${fmt.spct(s.price_effect_12m_ci90[0])} a ${fmt.spct(s.price_effect_12m_ci90[1])})</span>` : '<span class="muted">não identificável</span>'}</td></tr>`).join('');
  let hist = '';
  if (R.beta != null) {
    const e = Math.exp(R.beta) - 1, lo = Math.exp(R.beta_ci90[0]) - 1, hi = Math.exp(R.beta_ci90[1]) - 1;
    hist = R.credible
      ? `Historicamente (HPI ${qpt(R.hpi_start)}–${qpt(R.hpi_end)}), cada +1 p.p. da Euribor num ano associou-se a ${fmt.spct(e)} no preço nesse ano (intervalo de 90%: ${fmt.spct(lo)} a ${fmt.spct(hi)}).`
      : `A relação histórica entre Euribor e preços (HPI ${qpt(R.hpi_start)}–${qpt(R.hpi_end)}) aponta para ${fmt.spct(e)} por cada +1 p.p., mas o intervalo de 90% (${fmt.spct(lo)} a ${fmt.spct(hi)}) inclui zero: em Portugal, a subida de 2022 coincidiu com inflação alta e procura externa forte, e os dados não isolam o efeito. Por isso não mostramos um efeito nos preços — só a aritmética, que é certa.`;
  }
  return `<h3>Juros: e se a Euribor mudar 1 p.p.? ${info('rates')}</h3>
    <p>Hoje: Euribor 12M de ${fmt.n(R.euribor_now, 2)}% (${esc(R.euribor_month)}); taxa típica de ${fmt.n(R.rate_now, 2)}% (Euribor + ${fmt.n(R.spread, 2)} p.p.${R.spread_source && R.spread_source !== 'assumed'
      ? `: diferença real entre a taxa média dos novos créditos à habitação em Portugal e a Euribor, ${esc(R.spread_source)}` : ', valor assumido'}), crédito a ${R.years} anos.</p>
    <div class="table-wrap"><table class="ol-table"><thead><tr><th>Cenário</th><th>Prestação (mesmo empréstimo)</th><th>Quanto se pode pedir (mesma prestação)</th><th>Efeito histórico no preço (12m)</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p>${hist}</p>`;
}
function renderOutlook() {
  const body = $('#outlook-body');
  if (!OL || !(OL.sales || OL.rent || OL.regimes)) {
    body.innerHTML = '<p class="muted">Perspetivas ainda não geradas nesta build (corre <code>python -m imopt build</code>).</p>';
    return;
  }
  $('#ol-generated').textContent = `Calculado ${OL.build_date || ''}${OL.demo ? ' · dados sintéticos de demonstração' : ''}`;
  const parts = [];
  const add = (name, fn) => { try { parts.push(fn()); } catch (e) { console.error(`Falha em perspetivas/${name}:`, e); } };
  if (OL.sales) add('vendas', () => olSales(OL.sales));
  if (OL.tracking) add('arquivo', () => olTracking(OL.tracking));
  if (OL.demand) add('procura', () => olDemand(OL.demand));
  if (OL.fc_apt || OL.fc_house) add('tipos', () => olTypes(OL.fc_apt, OL.fc_house));
  if (OL.rent) add('rendas', () => olRent(OL.rent));
  if (OL.regimes) add('regimes', () => `<h3>Regimes do mercado (HPI nacional) ${info('regimes')}</h3><div id="ol-regimes" class="chart tall"></div><ul class="read">${OL.regimes.segments.map((s, i) =>
    `<li>${qpt(s.start)} a ${qpt(s.end)}: ${fmt.spct(s.growth_ann)}/ano${s.growth_ann_real != null ? ` (${fmt.spct(s.growth_ann_real)} descontada a inflação)` : ''}${i === OL.regimes.segments.length - 1 ? ' — <b>fase atual</b>' : ''}</li>`).join('')}</ul>`);
  if (OL.typologies) add('tipologias', () => olTypologies(OL.typologies));
  if (OL.ripple) add('propagação', () => olRipple(OL.ripple));
  if (OL.fair_value) add('valor justo', () => olFair(OL.fair_value));
  if (OL.rates) add('juros', () => olRates(OL.rates));
  parts.push(`<h3>Limites</h3><ul class="read">${(OL.limits || []).map((l) => `<li>${esc(l)}</li>`).join('')}</ul>`);
  body.innerHTML = parts.join('');
  const chart = (name, fn) => { try { fn(); } catch (e) { console.error(`Falha no gráfico ${name}:`, e); } };
  if ($('#ol-regimes')) chart('regimes', () => regimesChart('ol-regimes', OL.regimes));
  if ($('#ol-typo')) chart('tipologias', () => {
    const T = OL.typologies, sp = qpt(T.split);
    barChart('ol-typo', T.clusters.map((c) => `Grupo ${c.id}`), [
      { name: `Até ${sp}`, data: T.clusters.map((c) => c.growth_before), color: css('--s1') },
      { name: `Desde ${sp}`, data: T.clusters.map((c) => c.growth_after), color: css('--s2') },
    ], (v) => fmt.spct(v), Object.fromEntries(T.clusters.map((c) => [`Grupo ${c.id}`, `${c.id}. ${c.name}`])));
  });
  if ($('#ol-ripple')) chart('propagação', () => {
    const R = OL.ripple, b = R.bands.filter((x) => x.growth_after != null), sp = qpt(R.split);
    barChart('ol-ripple', b.map((x) => x.band), [
      { name: `Até ${sp}`, data: b.map((x) => x.growth_before), color: css('--s1') },
      { name: `Desde ${sp}`, data: b.map((x) => x.growth_after), color: css('--s2') },
    ], (v) => fmt.spct(v));
  });
}

// ---------- ranking
const COL_HELP = { price: 'price', price_growth_1y: 'g1y', rent: 'rent', gross_yield: 'yield', price_to_income_months: 'p2i',
  rent_to_income: 'r2i', migration_balance: 'migration', fc_growth_12m: 'fc12', score_overall: 'score_overall', band: 'band' };
const COLS = [
  ['name', 'Concelho', (m) => esc(m.name) + (m.volatile ? ' <span title="Preços muito voláteis (poucas transações): score atenuado">⚠</span>' : '')], ['price', '€/m²', (m) => fmt.eur(m.price)],
  ['price_growth_1y', 'Var. 12m', (m) => fmt.pct(m.price_growth_1y)], ['rent', 'Renda €/m²', (m) => (m.rent == null ? '—' : fmt.eur2(m.rent))],
  ['gross_yield', 'Rendib.', (m) => fmt.pct(m.gross_yield, 2)],
  ['price_to_income_months', 'Preço/rend. (m)', (m) => fmt.n(m.price_to_income_months, 1)],
  ['rent_to_income', 'Renda/rend.', (m) => (m.rent_to_income == null ? '—' : fmt.pct(m.rent_to_income, 1))],
  ['migration_balance', 'Saldo migrat.', (m) => (m.migration_balance == null ? '—' : (m.migration_balance >= 0 ? '+' : '') + fmt.n(m.migration_balance, 0))],
  ['fc_growth_12m', 'Prev. 12m', (m) => fmt.spct(m.fc_growth_12m)],
  ['score_overall', 'Score', (m) => fmt.n(m.score_overall)],
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
// Contexto geral do ranking, uma vez (não depende da pesquisa/ordenação): quantos concelhos em cada
// faixa, e se "Elevado" está ligado a ser caro ou só a subir depressa — a pergunta que motivou isto.
function renderRankingSummary() {
  const el = document.getElementById('ranking-summary');
  if (!el) return;
  const bands = { green: 0, amber: 0, red: 0, none: 0 };
  MUNIS.forEach((m) => bands[m.band || 'none']++);
  let txt = `${bands.red} concelhos em risco elevado, ${bands.amber} em moderado, ${bands.green} em baixo` +
    (bands.none ? `, ${bands.none} sem dados suficientes` : '') + '.';
  const prices = (b) => MUNIS.filter((m) => m.band === b).map((m) => m.price).filter((x) => x != null);
  const medRed = median(prices('red')), medGreen = median(prices('green'));
  if (medRed != null && medGreen != null) {
    const ratio = medRed / medGreen;
    if (ratio <= 0.85) {
      txt += ` Os concelhos "Elevado" tendem a ser mais baratos (mediana ${fmt.eur(medRed)}/m²) do que os "Baixo" ` +
        `(${fmt.eur(medGreen)}/m²): o score mede a velocidade de subida recente, não o preço em si — concelhos ` +
        'pequenos e baratos que sobem depressa em percentagem pontuam mais alto do que mercados caros e ' +
        'estáveis como Lisboa ou o Porto.';
    } else if (ratio >= 1.15) {
      txt += ` Os concelhos "Elevado" são, em geral, mais caros (mediana ${fmt.eur(medRed)}/m²) do que os "Baixo" ` +
        `(${fmt.eur(medGreen)}/m²) — aqui preço alto e crescimento rápido andam juntos, mas há exceções nos dois ` +
        'sentidos (clica num concelho para ver o caso concreto). O score continua a medir velocidade de subida, ' +
        'não o nível de preço em si.';
    } else {
      txt += ` Os concelhos "Elevado" (mediana ${fmt.eur(medRed)}/m²) e "Baixo" (${fmt.eur(medGreen)}/m²) não ` +
        'têm preços claramente diferentes nesta leitura — o score mede sobretudo a velocidade de subida recente, ' +
        'não se o concelho é caro ou barato.';
    }
  }
  el.textContent = txt;
}

function initTopNav() {
  const links = [...document.querySelectorAll('#topnav a')];
  const byId = new Map(links.map((a) => [a.getAttribute('href').slice(1), a]));
  const obs = new IntersectionObserver((entries) => {
    entries.forEach((e) => { const a = byId.get(e.target.id); if (a) a.classList.toggle('active', e.isIntersecting); });
  }, { rootMargin: '-56px 0px -70% 0px' });
  byId.forEach((_, id) => { const el = document.getElementById(id); if (el) obs.observe(el); });
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
  try { OL = await j('data/outlook.json'); } catch { OL = null; }
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
  $('#c-metric').addEventListener('change', (e) => { compareMetric = e.target.value; renderCompare(); });
  // Cada parte é isolada: uma falha (por exemplo o mapa/WebGL no Safari) não impede as restantes.
  const safe = (name, fn) => { try { fn(); } catch (e) { console.error(`Falha em ${name}:`, e); return e; } };
  safe('painel nacional', renderNational);
  safe('ranking', () => { renderTable(); renderRankingSummary(); });
  safe('backtest', renderBacktest);
  safe('perspetivas', renderOutlook);
  $('#outlook-body').addEventListener('click', (e) => {
    const a = e.target.closest('a[data-d]');
    if (a) { e.preventDefault(); select(a.dataset.d); }
  });
  safe('navegação', initTopNav);
  const mapErr = safe('mapa', initMap);
  if (mapErr) {
    $('#map').innerHTML = '<p class="muted" style="padding:16px">Não foi possível iniciar o mapa neste browser (WebGL?). O resto do painel funciona.</p>';
    $('#legend').innerHTML = '';
  }
  window.addEventListener('resize', () => Object.values(charts).forEach((c) => c.resize()));
}
main();
})();
