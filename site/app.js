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
  parishes: ['Freguesias', 'Preço mediano de venda por freguesia (INE, últimos 12 meses), comparado com a mediana do concelho e com a mediana das freguesias vizinhas que têm dados. O INE só publica cerca de 400 das ~3000 freguesias (onde há vendas suficientes), quase todas urbanas. Com poucas vendas, a mediana depende muito do tipo de casas vendidas nesse período.'],
  real: ['Descontada a inflação', 'Variação do preço já sem o efeito da subida geral de preços (inflação, IHPC do Eurostat). +12% real = o preço subiu 12% mais do que o custo de vida. O IHPC sai depois do preço da habitação: usa-se o último trimestre publicado.'],
  changes: ['O que mudou', 'Compara o trimestre mais recente publicado pelo INE com o anterior: variação do preço e do score de cada concelho, e quem mudou de faixa de risco. O score do trimestre anterior é recalculado com o mesmo método. As listas de maiores movimentos só incluem concelhos com mercado suficiente (pelo menos 20 avaliações bancárias em 3 meses), porque em concelhos pequenos o preço salta com poucas vendas.'],
  tracking: ['Previsões anteriores vs realidade', 'Cada build guarda as previsões que publicou. Quando o INE publica o valor real de um trimestre (ou ano, nas rendas) previsto, o erro é medido aqui — com os dados tal como saíram, sem revisões nem o benefício da retrospetiva. É a avaliação mais honesta, mas precisa de tempo: a 12 meses, os primeiros resultados só aparecem um ano depois do arranque do arquivo.'],
  ol_backtest: ['Como se saiu no passado', 'Para cada trimestre desde 2021, o modelo foi treinado só com o que se sabia nessa data e previu os trimestres seguintes. Erro médio em pontos percentuais (p.p.) de variação do preço, comparado com «fica igual» e «continua o ritmo do último ano». Cobertura: % das vezes em que o valor real caiu dentro do intervalo de 80%.'],
  effort: ['Esforço de compra', 'Prestação mensal do crédito para comprar uma casa ao preço mediano do concelho (área, entrada, prazo e taxa escolhidos na secção "Comprar casa"), a dividir pelo rendimento mensal escolhido: a mediana do rendimento declarado no IRS, após imposto, de quem VIVE no concelho (quando publicada), ou o salário médio bruto de quem TRABALHA no concelho. É o rendimento de uma pessoa: com dois rendimentos, escolhe "2". O Banco de Portugal limita a prestação a 50% do rendimento líquido — cerca de 45% do rendimento após IRS ou 40% do salário bruto. Os rendimentos publicados são de 1 a 2 anos antes do preço, por isso o esforço real tende a ser um pouco menor.'],
  buy_rent: ['Comprar ou arrendar', 'Compara a prestação do crédito com a renda da mesma casa (mesma área, renda mediana de novos contratos). A prestação inclui amortização, que é poupança, por isso não é um custo puro. A medida mais justa é o ponto de equilíbrio: custo anual de ser dono (juros à taxa escolhida sobre o preço todo — assume que a entrada renderia o mesmo —, mais cerca de 1,3% do preço para IMI, manutenção e seguros) menos a renda que se deixa de pagar, em % do preço. Comprar só sai mais barato do que arrendar se a casa valorizar mais do que isso por ano. Não inclui IMT, imposto do selo e escritura (pesam mais em quem fica poucos anos), nem impostos sobre mais-valias ou benefícios fiscais.'],
  val_gap: ['Avaliação bancária vs preço pago', 'Avaliação bancária média dos 12 meses que o preço de venda do INE cobre, face a esse preço. O nível da diferença é sobretudo composição: a avaliação só cobre casas compradas com crédito, e o preço mediano inclui todas as vendas. O sinal é a VARIAÇÃO num ano: se a avaliação fica para trás do preço pago, os bancos estão mais cautelosos ou há mais compras sem crédito; se a avaliação avança mais depressa, a banca acompanha (ou puxa) a subida.'],
  cycle: ['Ciclo preço–volume', 'Cruza a variação do preço a 12 meses com a variação do número de avaliações bancárias (compras com crédito) num ano. Preço a subir com menos compras é a fase típica de fim de ciclo: a procura já arrefece mas os preços, que reagem mais devagar, ainda sobem. Não diz quando, nem se, os preços vão cair. Só concelhos com pelo menos 20 avaliações em 3 meses.'],
  stress: ['Teste de juros', 'Prestação e esforço se a taxa subir os pontos escolhidos, mantendo o mesmo empréstimo. A maioria dos créditos em Portugal tem taxa variável ou mista: uma subida da Euribor passa para a prestação. O Banco de Portugal também pede aos bancos que testem a prestação com uma subida de juros antes de conceder o crédito.'],
  irs: ['Rendimento declarado (IRS)', 'Mediana do rendimento bruto declarado no IRS, depois de pago o imposto, por sujeito passivo (cada pessoa que declara; num casal com declaração conjunta contam os dois), no concelho onde a pessoa VIVE (INE, dados da Autoridade Tributária). Inclui salários, pensões e outros rendimentos; não desconta a Segurança Social. Por ser a mediana de todas as pessoas que declaram (incluindo pensionistas e quem trabalha a tempo parcial), fica bem abaixo do salário médio de quem trabalha a tempo inteiro. Valor anual; a calculadora usa ÷ 12. Sai com cerca de 2 anos de atraso.'],
  supply_new: ['Construção nova', 'Fogos licenciados (aprovados pela câmara, mensal) e concluídos (prontos, trimestral) em construções novas para habitação familiar (INE), somados por ano, e por 1000 alojamentos existentes no país. O INE só publica estas séries até às regiões (NUTS), não por concelho. Licenças são oferta futura: a conclusão chega 2 a 3 anos depois, e nem todas são construídas. Não conta as casas usadas que chegam ao mercado.'],
  census: ['Censos 2021: vagos e 2.ª habitação', 'Parte dos alojamentos familiares clássicos do concelho que estavam vagos (para venda ou arrendamento, ou por outros motivos: obras, heranças, abandono) ou eram de residência secundária (férias, fim de semana) no dia dos Censos 2021 (INE). Fotografia de 2021: o mercado mudou desde então. Muitas casas vagas não estão em condições de ser habitadas.'],
  beds: ['Alojamento turístico', 'Camas em alojamento turístico por 100 alojamentos familiares do concelho (INE): alojamento local e total (hotelaria, alojamento local e turismo rural). O alojamento local é o que mais compete com a habitação, porque usa casas. O INE só conta estabelecimentos com 10 ou mais camas, por isso o alojamento local pequeno (a maioria dos registos) fica de fora: o valor subestima o peso real. O parque habitacional usado é a estimativa mais recente do INE (2022).'],
  afford_hist: ['Esforço ao longo do tempo', 'Prestação de uma casa de 90 m² à avaliação bancária mediana do país, 90% financiada a 30 anos à taxa média dos novos créditos à habitação em cada trimestre (BCE), a dividir pelo rendimento nacional desse ano: salário médio bruto (INE) e mediana do rendimento declarado no IRS após imposto (÷ 12). Nos trimestres depois do último ano de rendimento publicado usa-se esse último ano (até 2 anos), o que exagera um pouco o esforço mais recente.'],
  score_why: ['Porque é este o score', 'O score de valorização é a média de três percentis entre concelhos: quão depressa o preço subiu em 12 meses, quão depressa subiu em 3 anos e quão baixa é a rendibilidade bruta (renda ÷ preço). Cada barra diz em que posição o concelho está nessa peça (100 = o mais esticado de todos). Sem renda publicada, a média faz-se só com as duas subidas. Concelhos com dados voláteis são puxados para o meio (50).'],
  rent_effort: ['Esforço de arrendar', 'Renda da mesma casa (renda mediana de novos contratos × área escolhida) a dividir pelo rendimento mensal escolhido na calculadora. É o par do esforço de compra para quem arrenda. Como referência, o Eurostat considera sobrecarga gastar mais de 40% do rendimento disponível com a casa.'],
  fc_vs_be: ['Previsão vs ponto de equilíbrio', 'Compara a variação do preço prevista pelo modelo para os próximos 12 meses (e o intervalo onde o valor real caiu 80% das vezes no passado) com a valorização anual a partir da qual comprar sai mais barato do que arrendar. É só uma comparação de números: uma previsão a 12 meses não diz nada sobre os anos seguintes, o modelo erra, e não é aconselhamento financeiro.'],
  europe: ['Portugal face à Europa', 'Índice de preços da habitação de cada país da UE (Eurostat, 2015 = 100) dividido pelo índice de preços no consumidor desse país (IHPC): a subida dos preços das casas acima da inflação. Compara ritmos de subida, não níveis de preço (um m² em Lisboa e em Paris não é comparável por este índice). Cada país publica com atrasos diferentes: usa-se o último trimestre com dados em pelo menos 2/3 dos países.'],
  follow: ['Os teus concelhos', 'Concelhos que escolheste seguir (botão ☆ no detalhe). A lista fica guardada só neste browser. Mostra o que mudou desde o trimestre anterior e os números principais.'],
  par_irs: ['Freguesias: rendimento e Censos', 'Por freguesia: mediana do rendimento declarado no IRS depois do imposto (por pessoa que declara, ÷ 12; o INE não publica freguesias com poucos declarantes), e a parte das casas vagas e de segunda habitação no Censos 2021. O esforço de compra por freguesia usa o preço da freguesia (só onde o INE o publica) e o rendimento do IRS de quem lá vive, com a casa e o crédito da calculadora.'],
  tourism_guests: ['Hóspedes e ocupação', 'Hóspedes em alojamento turístico nos últimos 12 meses publicados (INE, mensal; hotelaria, alojamento local com 10+ camas e turismo rural) e variação face aos 12 meses anteriores; parte dos hóspedes em alojamento local; taxa líquida de ocupação-cama no último ano (camas ocupadas ÷ camas disponíveis). Turismo a crescer depressa num concelho costuma puxar pelos preços e pelas rendas, sobretudo pelo alojamento local.'],
  effort_hist_muni: ['Esforço ao longo do tempo (concelho)', 'Para cada trimestre: prestação de 90 m² ao preço mediano de venda do concelho nesse trimestre (INE), 90% financiados a 30 anos à taxa média dos novos créditos desse trimestre (BCE), a dividir pelo rendimento do concelho desse ano (ou do último publicado, até 2 anos antes): mediana do IRS após imposto de quem lá vive (÷ 12) e salário médio bruto de quem lá trabalha. A casa e o crédito são fixos (não seguem a calculadora) para a série ser comparável no tempo.'],
  rent_parish: ['Rendas por freguesia', 'Renda mediana de novos contratos por freguesia (INE, anual) e a variação face a 1 e 3 anos antes. Só freguesias onde o INE publica a renda; nas listas, só as com pelo menos 50 novos contratos no ano, porque com poucos contratos a mediana salta muito.'],
  sources: ['Estado das fontes', 'Cada build tenta descarregar todos os indicadores. Se o INE não responder (acontece com os servidores do GitHub), usa os dados do último build que chegou ao INE e volta a tentar automaticamente mais tarde no mesmo dia. Indicadores opcionais com erro ficam simplesmente de fora do painel.'],
  credit: ['Crédito à habitação novo', 'Montante de novos empréstimos à habitação concedidos pelos bancos em Portugal (BCE, estatísticas de taxas de juro MIR), somado nos últimos 12 meses. "Novas operações" inclui renegociações de créditos antigos; "crédito novo puro" exclui-as. Mede quanto dinheiro novo entra no mercado: costuma mudar antes dos preços. Valores nominais.'],
  costs: ['Custo de construção', 'Índice de custo de construção de habitação nova do INE (materiais e mão de obra, mensal, nacional, 2021 = 100), comparado com o preço mediano de venda das casas novas e usadas (INE, 12 meses, nacional). Se os preços sobem muito mais do que o custo de construir, a subida vem sobretudo da procura e do preço do terreno, não do custo da obra. O índice não inclui terreno, licenças, impostos nem margem do promotor.'],
  signals: ['Que sinais ajudam a prever', 'Cada sinal é acrescentado à previsão do preço de venda e testado no passado sem ver o futuro, contra a mesma previsão sem ele. Só entra se reduzir o erro a 12 meses em pelo menos 1% sem piorar o trimestre seguinte em mais de 1% — regra fixada antes de ver os resultados. O teste é refeito em cada atualização. O teste exploratório usa a avaliação bancária de apartamentos e moradias (15 anos de histórico) e não decide nada: serve para ver se a conclusão se mantém.'],
  imovel: ['O meu imóvel', 'Aplica ao preço que indicaste índices oficiais do mercado local: avaliação bancária do concelho por tipo de casa (INE, desde 2011), preço mediano de venda do concelho e da freguesia (INE, desde 2019) e o índice nacional de preços da habitação. Compara o €/m² pago com as medianas da altura, estima a renda de mercado a partir das rendas de novos contratos e calcula prestação, esforço e rendibilidade com os pressupostos que escolheres. É estatística sobre medianas, não uma avaliação do teu imóvel.'],
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

let MUNIS = [], BY = {}, NAT = null, META = null, GEO = null, MAP = null, BT = null, OL = null, CH = null;
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
const DIV_PAL = ['#256abf', '#86b6ef', '#e2e2df', '#f4a07c', '#c9531f'];
const METRICS = {
  score: { prop: 'score', pal: PAL, fixed: [0, 100], f: (v) => fmt.n(v), label: 'Score',
    help: 'Quão "esticado" está cada concelho face aos outros: preço a subir depressa e rendibilidade baixa = mais vermelho. Verde < 40 (baixo), amarelo/laranja 40–69 (moderado), vermelho ≥ 70 (elevado). É relativo, não uma probabilidade de bolha. Cinzento = sem dados.' },
  price: { prop: 'price', pal: SEQ, f: fmt.eur, label: '€/m²',
    help: 'Preço mediano de venda (INE, últimos 12 meses). Mais escuro = mais caro. A escala vai do 5.º ao 95.º percentil para os extremos não achatarem o resto do mapa.' },
  yield: { prop: 'yield', pal: SEQ, f: (v) => fmt.pct(v, 2), label: 'Rendibilidade bruta',
    help: 'Renda anual ÷ preço, antes de custos. Mais escuro = a renda paga mais do preço; claro = preço alto face à renda. Cinzento = INE não publica renda para o concelho.' },
  g1yr: { prop: 'g1yr', pal: ['#256abf', '#86b6ef', '#e2e2df', '#f4a07c', '#c9531f'], diverge: true, f: (v) => fmt.spct(v), label: 'Var. 12m real',
    help: 'Variação do preço num ano já descontada a inflação. Laranja = subiu mais do que o custo de vida; azul = ficou para trás (desceu em termos reais).' },
  g1y: { prop: 'g1y', pal: SEQ, f: (v) => fmt.pct(v), label: 'Var. 12m',
    help: 'Variação nominal do preço face ao mesmo trimestre do ano anterior (não desconta a inflação). Mais escuro = subiu mais.' },
  fc: { prop: 'fc', pal: SEQ, f: (v) => fmt.spct(v), label: 'Previsão 12 meses',
    help: 'Variação prevista do preço mediano de venda nos próximos 12 meses (valor central; cada concelho tem um intervalo no detalhe). Ver a secção "Perspetivas" para saber como a previsão se saiu no passado. Cinzento = sem previsão.' },
  fv: { prop: 'fv', pal: ['#256abf', '#86b6ef', '#e2e2df', '#f4a07c', '#c9531f'], diverge: true, f: (v) => fmt.spct(v, 0), label: 'Face ao valor justo',
    help: 'Laranja = preço acima do que rendimento, demografia, litoral, distância e região explicam; azul = abaixo; cinzento claro = em linha. Não é prova de bolha: pode ser praia, turismo ou qualidade das casas, que o modelo não vê. Cinzento escuro = sem dados.' },
};
METRICS.fp = { prop: 'fp', pal: ['#256abf', '#86b6ef', '#e2e2df', '#f4a07c', '#c9531f'], diverge: true, f: (v) => fmt.spct(v, 0), label: 'Prémio de estrangeiros',
  help: 'Quanto mais (laranja) ou menos (azul) pagam por m² os compradores com domicílio no estrangeiro face aos residentes em Portugal. Cinzento = INE não publica (poucas vendas a estrangeiros).' };
METRICS.ef = { prop: 'ef', pal: PAL, fixed: [0.1, 0.7], f: (v) => fmt.pct(v, 0), label: 'Esforço de compra',
  help: 'Prestação do crédito ÷ rendimento mensal do concelho, para a casa, o crédito e o rendimento escolhidos em "Comprar casa". Verde = prestação leve; amarelo ≈ 40%, perto do limite do Banco de Portugal; laranja e vermelho = acima de 55%. Cinzento = sem rendimento ou preço publicado.' };
METRICS.br = { prop: 'br', pal: DIV_PAL, diverge: true, f: (v) => fmt.spct(v, 0), label: 'Prestação face à renda',
  help: 'Prestação do crédito face à renda da mesma casa (renda mediana de novos contratos). Azul = a prestação é mais baixa do que a renda; laranja = mais alta. A prestação inclui amortização (poupança): ver o ponto de equilíbrio em "Comprar casa". Cinzento = sem renda publicada.' };
METRICS.rf = { prop: 'rf', pal: PAL, fixed: [0.1, 0.7], f: (v) => fmt.pct(v, 0), label: 'Esforço de arrendar',
  help: 'Renda da mesma casa (novos contratos) ÷ rendimento mensal, com a área e o rendimento escolhidos em "Comprar casa". Verde = renda leve; amarelo ≈ 40%; laranja e vermelho = acima de 55%. Cinzento = sem renda ou rendimento publicado.' };
METRICS.tg = { prop: 'tg', pal: DIV_PAL, diverge: true, f: (v) => fmt.spct(v, 0), label: 'Hóspedes: variação num ano',
  help: 'Variação do número de hóspedes em alojamento turístico nos últimos 12 meses face aos 12 anteriores (INE). Laranja = turismo a crescer; azul = a cair. Cinzento = sem dados (poucos estabelecimentos).' };
METRICS.al = { prop: 'al', pal: SEQ, f: (v) => fmt.n(v, 1), label: 'Camas de alojamento local por 100 alojamentos',
  help: 'Camas em alojamento local (estabelecimentos com 10+ camas, INE) por 100 alojamentos familiares. Mais escuro = mais casas a servir turistas. Não inclui o alojamento local pequeno, que é a maioria: o peso real é maior. Cinzento = sem alojamento local publicado.' };
METRICS.vac = { prop: 'vac', pal: SEQ, f: (v) => fmt.pct(v, 0), label: 'Alojamentos vagos (Censos 2021)',
  help: 'Parte dos alojamentos vagos no Censos 2021 (para venda ou arrendamento, ou por outros motivos). Mais escuro = mais casas vazias. Muitas precisam de obras; é uma fotografia de 2021.' };
METRICS.sec = { prop: 'sec', pal: SEQ, f: (v) => fmt.pct(v, 0), label: 'Residência secundária (Censos 2021)',
  help: 'Parte dos alojamentos de residência secundária (férias, fim de semana) no Censos 2021. Mais escuro = mais casas que não servem quem vive no concelho.' };
const METRIC_VAL = { score: (x) => x.score_overall, price: (x) => x.price, yield: (x) => x.gross_yield, g1y: (x) => x.price_growth_1y, g1yr: (x) => x.price_growth_1y_real,
  fc: (x) => x.fc_growth_12m, fv: (x) => x.fv_gap, fp: (x) => x.foreign_premium, ef: (x) => x.aff_effort, br: (x) => x.aff_pay_vs_rent, rf: (x) => x.aff_rent_effort, tg: (x) => x.guests_growth_1y,
  al: (x) => x.al_beds_per_100, vac: (x) => x.vacant_share, sec: (x) => x.secondary_share };
const DIV = ['#256abf', '#86b6ef', '#e2e2df', '#f4a07c', '#c9531f'];
const PMETRICS = {
  f_rel_nb: { prop: 'rel_nb', src: 'par', pal: DIV, diverge: true, f: (v) => fmt.spct(v, 0), label: 'Face às freguesias vizinhas',
    help: 'Azul = mais barata do que a mediana das freguesias vizinhas com dados; laranja = mais cara. Cinzento = INE não publica a freguesia ou sem vizinhas suficientes com dados. As medianas de freguesia assentam em poucas vendas: confirma a tendência no detalhe do concelho.' },
  f_rel_muni: { prop: 'rel_muni', src: 'par', pal: DIV, diverge: true, f: (v) => fmt.spct(v, 0), label: 'Face ao concelho',
    help: 'Preço mediano da freguesia face à mediana do concelho. Azul = mais barata do que o concelho; laranja = mais cara.' },
  f_price: { prop: 'price', src: 'par', pal: SEQ, f: fmt.eur, label: '€/m² (freguesia)',
    help: 'Preço mediano de venda da freguesia (INE, últimos 12 meses). O INE só publica cerca de 400 freguesias, quase todas urbanas.' },
  f_irs: { prop: 'irs_m', src: 'par', pal: SEQ, f: fmt.eur, label: 'Rendimento IRS €/mês (freguesia)',
    help: 'Mediana do rendimento declarado no IRS depois do imposto, por pessoa que declara, ÷ 12 (INE). Mais escuro = rendimento mais alto. Cinzento = o INE não publica (freguesias com poucos declarantes).' },
  f_ef: { prop: 'ef', src: 'par', pal: PAL, fixed: [0.1, 0.7], f: (v) => fmt.pct(v, 0), label: 'Esforço de compra (freguesia)',
    help: 'Prestação de uma casa ao preço da freguesia (casa e crédito da calculadora "Comprar casa") ÷ rendimento do IRS de quem lá vive. Só onde o INE publica preço E rendimento da freguesia. Verde = leve; amarelo ≈ 40%; vermelho = acima de 55%.' },
  f_vac: { prop: 'vac', src: 'par', pal: SEQ, f: (v) => fmt.pct(v, 0), label: 'Vagos (Censos 2021)',
    help: 'Parte dos alojamentos vagos na freguesia no Censos 2021 (para venda, arrendamento ou outros motivos). Muitos precisam de obras.' },
  f_sec: { prop: 'sec', src: 'par', pal: SEQ, f: (v) => fmt.pct(v, 0), label: '2.ª habitação (Censos 2021)',
    help: 'Parte dos alojamentos de residência secundária na freguesia no Censos 2021.' },
  f_rg: { prop: 'rent_g3y', src: 'par', pal: SEQ, f: (v) => fmt.spct(v, 0), label: 'Renda: variação 3 anos (freguesia)',
    help: 'Variação da renda mediana de novos contratos da freguesia face a 3 anos antes (INE). Mais escuro = renda a subir mais. Só freguesias onde o INE publica a renda; com poucos contratos salta muito.' },
  f_g1y: { prop: 'g1y', src: 'par', pal: SEQ, f: (v) => fmt.pct(v), label: 'Var. 12m (freguesia)',
    help: 'Variação do preço mediano da freguesia face a um ano antes. Com poucas vendas, salta muito: lê com cautela.' },
};
let LEVEL = 'c', PAR = null, PGJ = null, PARBY = {};
let serP = null, SER = false, parP = null;
function ensureSeries() {
  if (!serP) {
    serP = j('data/series.json').then((d) => {
      MUNIS.forEach((m) => Object.assign(m, { series: { price: [], rent: [] } }, d[m.dico] || {}));
    }).catch((e) => { console.error('séries:', e); MUNIS.forEach((m) => { m.series = m.series || { price: [], rent: [] }; }); })
      .then(() => { SER = true; });
  }
  return serP;
}
function ensurePar() {
  if (!parP) {
    parP = j('data/freguesias.json').then((d) => {
      PAR = d; PARBY = Object.fromEntries(PAR.rows.map((r) => [r.code, r]));
      parishDerive();          // calcula irs_m, ef, vac, sec antes de ver que indicadores têm dados
      [...$('#metric-f').options].forEach((o) => {
        const pm = PMETRICS[o.value];
        if (pm && !PAR.rows.some((r) => r[pm.prop] != null)) o.remove();
      });
      renderParList();
    }).catch(() => { PAR = null; });
  }
  return parP;
}
function parishDerive() {
  if (!PAR) return;
  const rate = affRate();
  PAR.rows.forEach((r) => {
    r.irs_m = r.irs_median != null ? r.irs_median / 12 : null;
    r.vac = r.vacant_share; r.sec = r.secondary_share;
    const pay = r.price != null ? annuity(r.price * AFF.area * (1 - AFF.down / 100), rate, AFF.years) : null;
    r.ef = pay != null && r.irs_m ? pay / (r.irs_m * AFF.earners) : null;
  });
  if (PGJ) {
    PGJ.features.forEach((f) => { const r = PARBY[f.properties.code]; ['irs_m', 'ef', 'vac', 'sec', 'rent_g3y'].forEach((k) => { f.properties[k] = r ? r[k] ?? null : null; }); });
    if (MAP && MAP.getSource('f')) MAP.getSource('f').setData(PGJ);
  }
}
const curMetric = () => (LEVEL === 'f' ? PMETRICS[$('#metric-f').value] : METRICS[$('#metric').value]);
function quantile(sorted, q) { const i = (sorted.length - 1) * q, lo = Math.floor(i), hi = Math.ceil(i); return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo); }
function domain(m) {
  if (m.fixed) return m.fixed;
  const src = m.src === 'par' ? (PAR ? PAR.rows.map((r) => r[m.prop]) : []) : MUNIS.map(METRIC_VAL[m.prop]);
  const v = src.filter((x) => x != null).sort((a, b) => a - b);
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
  const m = curMetric();
  const layer = LEVEL === 'f' ? 'f-fill' : 'fill';
  if (MAP && MAP.getLayer(layer)) MAP.setPaintProperty(layer, 'fill-color', metricExpr(m));
  renderLegend(m);
}
async function addParishLayer() {
  if (MAP.getSource('f')) return true;
  let gj;
  try { gj = await j('data/freguesias.geojson'); } catch { return false; }
  PGJ = gj; parishDerive();
  MAP.addSource('f', { type: 'geojson', data: gj, promoteId: 'code' });
  MAP.addLayer({ id: 'f-fill', type: 'fill', source: 'f', paint: { 'fill-color': metricExpr(curMetric()), 'fill-opacity': 0.92 } }, 'line');
  MAP.addLayer({ id: 'f-line', type: 'line', source: 'f', paint: { 'line-color': css('--card'), 'line-width': 0.4 } }, 'line');
  const pop = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
  const nz = (x) => (x == null || x === 'null' || x === '' ? null : Number(x));
  MAP.on('mousemove', 'f-fill', (e) => {
    const f = e.features[0]; if (!f) return;
    const p = f.properties, m = curMetric(), conc = BY[String(p.code).slice(0, 4)];
    pop.setLngLat(e.lngLat).setHTML(`<b>${esc(p.name || "Freguesia sem dados")}</b>${conc ? ` <span style="color:#555">(${esc(conc.name)})</span>` : ''}<br>${esc(m.label)}: ${esc(m.f(nz(p[m.prop])))}<br>€/m²: ${esc(fmt.eur(nz(p.price)))}<br><span style="color:#555">clica para o concelho</span>`).addTo(MAP);
  });
  MAP.on('mouseleave', 'f-fill', () => pop.remove());
  MAP.on('click', 'f-fill', (e) => { const f = e.features[0]; if (f) select(String(f.properties.code).slice(0, 4)); });
  MAP.on('mouseenter', 'f-fill', () => (MAP.getCanvas().style.cursor = 'pointer'));
  MAP.on('mouseleave', 'f-fill', () => (MAP.getCanvas().style.cursor = ''));
  return true;
}
async function setLevel(lvl) {
  if (lvl === 'f') await ensurePar();
  if (lvl === 'f' && !(PAR && PAR.with_map)) {
    $('#map-help').textContent = PAR && PAR.rows.length
      ? 'As fronteiras das freguesias não estão disponíveis nesta build. A lista de freguesias por concelho continua no detalhe de cada concelho, e as mais baratas do que as vizinhas aparecem abaixo quando houver fronteiras.'
      : 'Sem dados de freguesias nesta build.';
    return;
  }
  LEVEL = lvl;
  document.querySelectorAll('#lvlnav .btn').forEach((b) => b.classList.toggle('on', b.dataset.lvl === lvl));
  $('#metric').hidden = lvl === 'f';
  $('#metric-f').hidden = lvl !== 'f';
  $('#par-list').hidden = lvl !== 'f';
  if (MAP && MAP.getLayer('fill')) {
    if (lvl === 'f' && !(await addParishLayer())) { LEVEL = 'c'; return setLevel('c'); }
    MAP.setLayoutProperty('fill', 'visibility', lvl === 'f' ? 'none' : 'visible');
    ['f-fill', 'f-line'].forEach((id) => MAP.getLayer(id) && MAP.setLayoutProperty(id, 'visibility', lvl === 'f' ? 'visible' : 'none'));
  }
  updateMetric();
}
function renderParList() {
  const el = $('#par-list');
  if (!PAR) return;
  const ok = PAR.rows.filter((r) => r.rel_nb != null);
  if (!ok.length) { el.innerHTML = rentRisers(); return; }
  const item = (r) => `<li><span>${lnk(r.dico, r.name)} <span class="muted">(${esc((BY[r.dico] || {}).name || r.dico)})</span></span><span class="v">${fmt.spct(r.rel_nb, 0)} <span class="muted">${fmt.eur(r.price)}/m² · ${fmt.spct(r.rel_muni, 0)} vs concelho</span></span></li>`;
  const cheap = ok.slice().sort((a, b) => a.rel_nb - b.rel_nb).slice(0, 12).map(item).join('');
  el.innerHTML = `<h3>Freguesias mais baratas do que as vizinhas ${info('parishes')}</h3>
    <p class="muted">Preço mediano de venda (${qpt(PAR.period)}) face à mediana das freguesias vizinhas com dados. Pode ser oportunidade, ou só casas diferentes (mais pequenas, mais antigas, a precisar de obras): confirma no terreno.</p>
    <ul class="ol-list">${cheap}</ul>${rentRisers()}`;
}
function rentRisers() {
  const ok = PAR.rows.filter((r) => r.rent_g3y != null && (r.rent_contracts == null || r.rent_contracts >= 50));
  if (ok.length < 10) return '';
  const y = (ok.find((r) => r.rent_year) || {}).rent_year;
  const it = (r) => `<li><span>${lnk(r.dico, r.name)} <span class="muted">(${esc((BY[r.dico] || {}).name || r.dico)})</span></span><span class="v">${fmt.spct(r.rent_g3y, 0)} <span class="muted">${fmt.eur2(r.rent)}/m²${r.rent_contracts != null ? ` · ${fmt.n(r.rent_contracts, 0)} contratos` : ''}</span></span></li>`;
  return `<h3>Freguesias onde a renda mais subiu ${info('rent_parish')}</h3>
    <p class="muted">Renda mediana de novos contratos em ${y ?? '—'} face a 3 anos antes; só freguesias com pelo menos 50 novos contratos no ano.</p>
    <ul class="ol-list wrap-list">${ok.sort((a, b) => b.rent_g3y - a.rent_g3y).slice(0, 12).map(it).join('')}</ul>`;
}
function renderParTable(dico) {
  if (!PAR) { $('#d-par').hidden = true; return; }
  const rows = PAR ? PAR.rows.filter((r) => r.dico === dico).sort((a, b) => (b.price ?? -1) - (a.price ?? -1) || String(a.name).localeCompare(String(b.name), 'pt')) : [];
  $('#d-par').hidden = !rows.length;
  if (!rows.length) return;
  const has = (k) => rows.some((r) => r[k] != null);
  const hasP = has('price'), hasRent = has('rent'), hasNb = has('rel_nb'), hasIrs = has('irs_median'), hasCen = has('vacant_share');
  const hasRg = has('rent_g3y');
  const th = [['Freguesia', true], ['€/m²', hasP], ['Face ao concelho', hasP], ['Face às vizinhas', hasNb], ['Var. 12m', hasP], ['Renda €/m²', hasRent], ['Renda 3 anos', hasRg],
    ['IRS €/mês', hasIrs], ['Esforço', hasP && hasIrs], ['Vagos', hasCen], ['2.ª hab.', hasCen]];
  const td = (r) => [esc(r.name), fmt.eur(r.price), fmt.spct(r.rel_muni, 0), fmt.spct(r.rel_nb, 0), fmt.pct(r.g1y), r.rent == null ? '—' : fmt.eur2(r.rent), fmt.spct(r.rent_g3y, 0),
    fmt.eur(r.irs_m), fmt.pct(r.ef, 0), fmt.pct(r.vacant_share, 0), fmt.pct(r.secondary_share, 0)];
  $('#d-par-table').innerHTML = `<thead><tr>${th.filter((x) => x[1]).map((x) => `<th>${x[0]}</th>`).join('')}</tr></thead><tbody>` +
    rows.map((r) => `<tr>${td(r).filter((_, i) => th[i][1]).map((v) => `<td>${v}</td>`).join('')}</tr>`).join('') + '</tbody>';
  const np = rows.filter((r) => r.price != null).length;
  $('#d-par-note').textContent = `${rows.length} freguesias; ${np} com preço publicado pelo INE (${qpt(PAR.period)}, últimos 12 meses) — as restantes têm poucas vendas.${hasRent ? ` Renda: novos contratos em ${rows.find((r) => r.rent_year)?.rent_year ?? '—'}.` : ''}${hasIrs ? ` IRS: mediana após imposto por pessoa que declara (${rows.find((r) => r.irs_year)?.irs_year ?? '—'}), ÷ 12; esforço com a casa e o crédito da calculadora.` : ''}${hasCen ? ' Vagos e 2.ª habitação: Censos 2021.' : ''} Medianas de freguesia assentam em poucas vendas — diferenças grandes podem ser só o tipo de casas vendidas.`;
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
  if (m.price_growth_1y != null) li.push(`Subiu ${fmt.pct(m.price_growth_1y)} em 12 meses (mediana dos concelhos: ${fmt.pct(mg)}) e ${fmt.pct(m.price_growth_3y)} em 3 anos${m.price_growth_1y_real != null ? `; descontada a inflação, ${fmt.spct(m.price_growth_1y_real)} e ${fmt.spct(m.price_growth_3y_real)}` : ', sem descontar inflação'}.`);
  if (m.price_qoq != null && m.score_prev != null && CH) li.push(`Desde ${qpt(CH.prev_period)}: preço ${fmt.spct(m.price_qoq)} no trimestre; score de ${fmt.n(m.score_prev)} para ${fmt.n(m.score_overall)}${m.band_prev && m.band_prev !== m.band ? ` (mudou de ${BAND_LABEL[m.band_prev]} para ${BAND_LABEL[m.band] || 'n/d'})` : ''}.`);
  const my = median(col((x) => x.gross_yield));
  if (m.gross_yield != null && my != null) {
    li.push(`Rendibilidade bruta de ${fmt.pct(m.gross_yield, 2)} (mediana ${fmt.pct(my, 2)}): ${m.gross_yield < my ? 'o preço está esticado face à renda, pois cada € investido rende menos do que no concelho típico' : 'a renda paga melhor o preço do que no concelho típico'}.`);
  } else li.push('Sem renda publicada pelo INE para este concelho (poucos contratos): não há rendibilidade nem preço/renda, e o score assenta só no ritmo de subida dos preços.');
  if (m.aff_pay != null) li.push(affReadTxt(m));
  if (m.vacant_share != null) {
    const mv = median(col((x) => x.vacant_share)), ms = median(col((x) => x.secondary_share));
    li.push(`Censos 2021: ${fmt.pct(m.vacant_share, 0)} dos alojamentos estavam vagos (mediana dos concelhos ${fmt.pct(mv, 0)}; ${fmt.pct(m.vacant_market_share, 1)} para venda ou arrendamento) e ${fmt.pct(m.secondary_share, 0)} eram de residência secundária (mediana ${fmt.pct(ms, 0)}).`);
  }
  if (m.guests_12m != null) li.push(`Turismo: ${fmt.n(m.guests_12m, 0)} hóspedes nos 12 meses até ${esc(m.guests_until)} (${fmt.spct(m.guests_growth_1y, 0)} face aos 12 anteriores)${m.guests_al_share != null ? `, ${fmt.pct(m.guests_al_share, 0)} em alojamento local` : ''}${m.occupancy != null ? `; ocupação-cama de ${fmt.pct(m.occupancy, 0)} em ${m.occupancy_year}${m.occupancy_chg != null ? ` (${m.occupancy_chg >= 0 ? '+' : '−'}${fmt.n(Math.abs(m.occupancy_chg) * 100, 1)} p.p.)` : ''}` : ''}.`);
  if (m.beds_per_100 != null) li.push(`Alojamento turístico (${m.tourism_beds_year}): ${fmt.n(m.beds_per_100, 1)} camas por 100 alojamentos${m.al_beds_per_100 != null ? `, ${fmt.n(m.al_beds_per_100, 1)} delas em alojamento local` : ''} (mediana dos concelhos ${fmt.n(median(col((x) => x.beds_per_100)), 1)}; sem o alojamento local com menos de 10 camas).`);
  if (m.cycle_phase) li.push(`Ciclo: preço ${fmt.spct(m.price_growth_1y)} e compras com crédito ${fmt.spct(m.val_count_growth_1y, 0)} num ano — «${CYCLE_SHORT[m.cycle_phase]}»${m.cycle_phase === 'up_down' ? ', a fase típica de fim de ciclo (a procura arrefece antes dos preços)' : ''}.`);
  if (m.val_gap_chg != null) li.push(`A avaliação bancária está ${fmt.spct(m.val_gap, 0)} face ao preço pago e ${Math.abs(m.val_gap_chg) < 0.03 ? 'acompanhou os preços' : m.val_gap_chg < 0 ? `ficou ${fmt.n(-m.val_gap_chg * 100, 0)} p.p. mais para trás num ano (bancos mais cautelosos ou mais compras sem crédito)` : `avançou ${fmt.n(m.val_gap_chg * 100, 0)} p.p. mais do que o preço num ano`}.`);
  const sc = m.score_overall;
  if (sc != null) li.push(`Score ${fmt.n(sc)}: ${sc >= 70 ? 'entre os concelhos mais "esticados"' : sc >= 40 ? 'a meio do pelotão de concelhos' : 'entre os concelhos menos "esticados"'}. É uma posição relativa, não uma previsão de queda.`);
  const demoBits = [];
  if (m.population != null) demoBits.push(`${fmt.n(m.population, 0)} habitantes (${m.population_year})`);
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
function scoreWhy(m) {
  const parts = [['Subida do preço em 12 meses', m.score_part_g1y, fmt.pct(m.price_growth_1y)],
    ['Subida do preço em 3 anos', m.score_part_g3y, fmt.pct(m.price_growth_3y)],
    ['Rendibilidade baixa (renda ÷ preço)', m.score_part_yield, m.gross_yield == null ? 'sem renda publicada' : `rendibilidade ${fmt.pct(m.gross_yield, 2)}`]];
  const ok = parts.filter((x) => x[1] != null);
  if (!ok.length || m.score_overall == null) return '';
  const raw = ok.reduce((a, x) => a + x[1], 0) / ok.length;
  const bar = ([label, v, ctxt]) => `<div class="why-row"><span>${esc(label)}</span><span class="why-bar"><i style="width:${v == null ? 0 : Math.max(2, v)}%"></i></span><b>${v == null ? '—' : fmt.n(v)}</b><span class="muted">${esc(ctxt)}</span></div>`;
  return `<h3>Porque é este o score ${info('score_why')}</h3>${parts.map(bar).join('')}
    <p class="muted">Score = média ${ok.length < 3 ? `das ${ok.length} peças com dados` : 'das três peças'} = ${fmt.n(raw)}${m.volatile ? `; com dados voláteis é puxado para o meio: 50 + (${fmt.n(raw)} − 50) ÷ 2 = ${fmt.n(m.score_overall)}` : ''}. Cada número é o percentil entre concelhos (100 = o mais esticado).</p>`;
}
function select(dico, scroll = true) {
  const m = BY[dico]; if (!m) return;
  if (!SER) { ensureSeries().then(() => select(dico, scroll)); return; }
  if (!parP) ensurePar().then(() => { if (selected === dico) { try { renderParTable(dico); } catch (e) { console.error(e); } } });
  if (MAP && MAP.getSource('c')) {
    if (selected) MAP.setFeatureState({ source: 'c', id: selected }, { sel: false });
    MAP.setFeatureState({ source: 'c', id: dico }, { sel: true });
  }
  selected = dico;
  $('#detail').hidden = false;
  $('#d-print-head').textContent = `Painel de Risco Imobiliário — ficha de ${m.name} · ${META.built_at.slice(0, 10)} · preços até ${qpt(META.latest_price_period)} · fontes: INE, BCE, Eurostat · não é aconselhamento financeiro`;
  $('#detail').style.borderLeftColor = `var(--${m.band || 'none'})`;
  $('#d-title').innerHTML = `${esc(m.name)} ${pill(m.band)} ${info('band')}${m.volatile ? ' ' + pill(null, '⚠ dados voláteis') + ' ' + info('volatile') : ''}`;
  const tile = (k, label, val, c = '') => `<div class="stat"><span class="muted">${label} ${info(k)}</span><b>${val}</b>${c}</div>`;
  $('#d-stats').innerHTML = [
    tile('price', 'Preço mediano', fmt.eur(m.price) + '/m²', ctx((x) => x.price, m.price, fmt.eur)),
    tile('g1y', 'Var. 12m', fmt.pct(m.price_growth_1y), ctx((x) => x.price_growth_1y, m.price_growth_1y, (v) => fmt.pct(v))),
    tile('g3y', 'Var. 3 anos', fmt.pct(m.price_growth_3y), ctx((x) => x.price_growth_3y, m.price_growth_3y, (v) => fmt.pct(v))),
    ...(m.price_growth_1y_real != null ? [tile('real', 'Var. 12m real', fmt.spct(m.price_growth_1y_real),
      `<span class="ctx">3 anos: ${fmt.spct(m.price_growth_3y_real)} · 5 anos: ${fmt.spct(m.price_growth_5y_real)}</span>`)] : []),
    tile('rent', 'Renda (novos contratos)', m.rent == null ? '—' : fmt.eur2(m.rent) + '/m²', ctx((x) => x.rent, m.rent, fmt.eur2)),
    tile('yield', 'Rendibilidade bruta', fmt.pct(m.gross_yield, 2), ctx((x) => x.gross_yield, m.gross_yield, (v) => fmt.pct(v, 2))),
    tile('p2r', 'Preço/renda (anos)', fmt.n(m.price_to_rent_years, 1), ctx((x) => x.price_to_rent_years, m.price_to_rent_years, (v) => fmt.n(v, 1))),
    tile('p2i', 'Preço/rendimento (meses)', fmt.n(m.price_to_income_months, 1), ctx((x) => x.price_to_income_months, m.price_to_income_months, (v) => fmt.n(v, 1))),
    tile('r2i', 'Renda/rendimento', fmt.pct(m.rent_to_income, 1), ctx((x) => x.rent_to_income, m.rent_to_income, (v) => fmt.pct(v, 1))),
    ...(m.aff_effort != null ? [tile('effort', `Esforço de compra (${AFF.area} m²)`, fmt.pct(m.aff_effort, 0),
      `<span class="ctx">prestação ${fmt.eur(m.aff_pay)}/mês · ${fmt.n(m.aff_years_salary, 1)} anos de ${incTxt().short} · com +${fmt.n(AFF.shock, 0)} p.p. de juros: ${fmt.pct(m.aff_effort_stress, 0)} · ${ctx((x) => x.aff_effort, m.aff_effort, (v) => fmt.pct(v, 0)).replace(/<[^>]+>/g, '')}</span>`)] : []),
    ...(m.aff_rent_home != null ? [tile('buy_rent', 'Prestação vs renda', `${fmt.eur(m.aff_pay)} vs ${fmt.eur(m.aff_rent_home)}`,
      `<span class="ctx">${breakevenTxt(m.aff_breakeven)}${m.aff_rent_effort != null ? ` · renda = ${fmt.pct(m.aff_rent_effort, 0)} do ${incTxt().short}` : ''}${fcBeShort(m)}</span>`)] : []),
    ...(m.cycle_phase ? [tile('cycle', 'Ciclo preço–volume', esc(CYCLE_SHORT[m.cycle_phase]),
      `<span class="ctx">preço ${fmt.spct(m.price_growth_1y)} · compras com crédito ${fmt.spct(m.val_count_growth_1y, 0)} num ano</span>`)] : []),
    ...(m.val_gap != null ? [tile('val_gap', 'Avaliação vs preço pago', fmt.spct(m.val_gap, 0),
      `<span class="ctx">${m.val_gap_chg != null ? `${m.val_gap_chg >= 0 ? '+' : '−'}${fmt.n(Math.abs(m.val_gap_chg) * 100, 1)} p.p. num ano` : 'sem comparação a um ano'}</span>`)] : []),
    ...(m.irs_median != null ? [tile('irs', `Rendimento IRS (${m.irs_year})`, fmt.eur(m.irs_median / 12) + '/mês',
      `<span class="ctx">${fmt.eur(m.irs_median)}/ano por pessoa, após imposto${m.irs_growth_1y != null ? ` · ${fmt.spct(m.irs_growth_1y)} num ano` : ''}</span>`)] : []),
    ...(m.vacant_share != null ? [tile('census', 'Vagos / 2.ª habitação (2021)', `${fmt.pct(m.vacant_share, 0)} / ${fmt.pct(m.secondary_share, 0)}`,
      `<span class="ctx">vagos para venda ou arrendamento: ${fmt.pct(m.vacant_market_share, 1)} · ${fmt.n(m.census_total, 0)} alojamentos</span>`)] : []),
    ...(m.guests_12m != null ? [tile('tourism_guests', 'Hóspedes (12 meses)', `${fmt.n(m.guests_12m / 1000, m.guests_12m < 10000 ? 1 : 0)} mil`,
      `<span class="ctx">${fmt.spct(m.guests_growth_1y, 0)} num ano${m.guests_al_share != null ? ` · ${fmt.pct(m.guests_al_share, 0)} em AL` : ''}${m.occupancy != null ? ` · ocupação ${fmt.pct(m.occupancy, 0)} (${m.occupancy_year})` : ''}</span>`)] : []),
    ...(m.beds_per_100 != null ? [tile('beds', 'Camas turísticas /100 aloj.', `${m.al_beds_per_100 != null ? fmt.n(m.al_beds_per_100, 1) + ' AL · ' : ''}${fmt.n(m.beds_per_100, 1)} total`,
      `<span class="ctx">${m.tourism_beds_year}; AL = alojamento local com 10+ camas</span>`)] : []),
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
  $('#d-why').innerHTML = scoreWhy(m);
  const fb = $('#d-follow'); fb.textContent = FOLLOW.includes(dico) ? '★ A seguir' : '☆ Seguir'; fb.setAttribute('aria-pressed', FOLLOW.includes(dico));
  try { renderParTable(dico); } catch (e) { console.error('Falha nas freguesias:', e); }
  const s = [{ name: 'Preço', data: m.series.price, fmt: (v) => fmt.eur(v) + '/m²' }];
  if (m.series.price_real && m.series.price_real.length) s.push({ name: `Preço real (€ de ${qpt(m.hicp_period)})`, data: m.series.price_real, dashed: true, fmt: (v) => fmt.eur(v) + '/m²' });
  $('#d-chart-note').textContent = 'Preço: mediana de vendas dos últimos 12 meses, trimestral (eixo esquerdo)' + (m.series.price_real && m.series.price_real.length ? `; tracejado: o mesmo preço descontada a inflação, em € de ${qpt(m.hicp_period)}` : '') + '. Renda: mediana de novos contratos, anual (eixo direito, pontos).';
  const q4 = (p) => (p.length === 4 ? p + 'Q4' : p);
  if (m.series.rent.length) s.push({ name: 'Renda', data: m.series.rent.map(([p, v]) => [q4(p), v]), axis: 1, dots: true, fmt: (v) => fmt.eur2(v) + '/m²/mês' });
  $('#d-fc-wrap').hidden = !m.fc;
  $('#d-fc-note').textContent = m.fc ? `Estimativa e previsão calculadas em ${OL && OL.build_date ? OL.build_date : '—'} com dados do INE até ${qpt(OL && OL.sales ? OL.sales.origin : '')} (vendas) e ${OL && OL.sales && OL.sales.last_valuation ? OL.sales.last_valuation : '—'} (avaliação bancária). Ver "Perspetivas" para o erro no passado.` : '';
  try {
    const hasRent = s.some((x) => x.axis === 1);
    lineChart('chart-detail', 'Evolução', s, { dual: hasRent, names: hasRent ? ['Preço (€/m²)', 'Renda (€/m²/mês)'] : ['Preço (€/m²)'], notitle: true });
  } catch (e) { console.error('Falha no gráfico do detalhe:', e); }
  if (m.fc) try { fanChart('chart-fc', m); } catch (e) { console.error('Falha no gráfico da previsão:', e); }
  const eh = m.effort_hist || [];
  $('#d-eff-wrap').hidden = !eh.length;
  if (eh.length) {
    try {
      lineChart('chart-eff', 'Esforço', [
        ...(eh.some((r) => r[1] != null) ? [{ name: 'IRS de quem vive', data: eh.filter((r) => r[1] != null).map((r) => [qpt(r[0]), +(r[1] * 100).toFixed(1)]), fmt: (v) => fmt.n(v, 0) + '%' }] : []),
        ...(eh.some((r) => r[2] != null) ? [{ name: 'Salário de quem trabalha', data: eh.filter((r) => r[2] != null).map((r) => [qpt(r[0]), +(r[2] * 100).toFixed(1)]), fmt: (v) => fmt.n(v, 0) + '%' }] : []),
      ], { names: ['% do rendimento mensal'], notitle: true });
    } catch (e) { console.error('Falha no gráfico do esforço:', e); }
    const a = eh.find((r) => r[1] != null), b = [...eh].reverse().find((r) => r[1] != null);
    $('#d-eff-note').textContent = `Prestação de 90 m² ao preço mediano do concelho (90% a 30 anos, taxa média dos novos créditos de cada trimestre) em % do rendimento.${a && b ? ` Com o IRS: ${fmt.pct(a[1], 0)} em ${qpt(a[0])}, ${fmt.pct(b[1], 0)} em ${qpt(b[0])}.` : ''} O rendimento do último ano publicado repete-se até 2 anos.`;
  }
  $('#d-compare').textContent = compare.includes(dico) ? 'Remover da comparação' : 'Comparar';
  if (scroll) $('#detail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
const COMPARE_ROWS = [
  ['price', 'Preço mediano', (m) => fmt.eur(m.price) + '/m²'],
  ['g1y', 'Variação 12 meses', (m) => fmt.pct(m.price_growth_1y)],
  ['g3y', 'Variação 3 anos', (m) => fmt.pct(m.price_growth_3y)],
  ['real', 'Variação 12m / 3 anos real', (m) => `${fmt.spct(m.price_growth_1y_real)} / ${fmt.spct(m.price_growth_3y_real)}`],
  ['rent', 'Renda (novos contratos)', (m) => (m.rent == null ? '—' : fmt.eur2(m.rent) + '/m²')],
  ['yield', 'Rendibilidade bruta', (m) => fmt.pct(m.gross_yield, 2)],
  ['p2r', 'Preço/renda (anos)', (m) => fmt.n(m.price_to_rent_years, 1)],
  ['p2i', 'Preço/rendimento (meses)', (m) => fmt.n(m.price_to_income_months, 1)],
  ['r2i', 'Renda/rendimento', (m) => (m.rent_to_income == null ? '—' : fmt.pct(m.rent_to_income, 1))],
  ['effort', 'Esforço de compra (prestação/rendimento)', (m) => (m.aff_effort == null ? '—' : `${fmt.pct(m.aff_effort, 0)} (${fmt.eur(m.aff_pay)}/mês)`)],
  ['buy_rent', 'Prestação vs renda da mesma casa', (m) => (m.aff_rent_home == null ? '—' : `${fmt.eur(m.aff_pay)} vs ${fmt.eur(m.aff_rent_home)}`)],
  ['rent_effort', 'Esforço de arrendar (renda/rendimento)', (m) => (m.aff_rent_effort == null ? '—' : `${fmt.pct(m.aff_rent_effort, 0)} (${fmt.eur(m.aff_rent_home)}/mês)`)],
  ['buy_rent', 'Valorização para comprar compensar', (m) => (m.aff_breakeven == null ? '—' : fmt.spct(m.aff_breakeven) + '/ano')],
  ['irs', 'Rendimento IRS (mediana, após imposto)', (m) => (m.irs_median == null ? '—' : `${fmt.eur(m.irs_median / 12)}/mês (${m.irs_year})`)],
  ['census', 'Vagos / 2.ª habitação (Censos 2021)', (m) => (m.vacant_share == null ? '—' : `${fmt.pct(m.vacant_share, 0)} / ${fmt.pct(m.secondary_share, 0)}`)],
  ['tourism_guests', 'Hóspedes 12 meses (variação; ocupação)', (m) => (m.guests_12m == null ? '—' : `${fmt.n(m.guests_12m, 0)} (${fmt.spct(m.guests_growth_1y, 0)}; ${fmt.pct(m.occupancy, 0)})`)],
  ['beds', 'Camas turísticas por 100 aloj. (AL / total)', (m) => (m.beds_per_100 == null ? '—' : `${fmt.n(m.al_beds_per_100, 1)} / ${fmt.n(m.beds_per_100, 1)}`)],
  ['stress', 'Esforço com subida de juros', (m) => (m.aff_effort_stress == null ? '—' : `${fmt.pct(m.aff_effort_stress, 0)} (+${fmt.n(AFF.shock, 0)} p.p.)`)],
  ['cycle', 'Ciclo preço–volume', (m) => esc(m.cycle_phase ? CYCLE_SHORT[m.cycle_phase] : '—')],
  ['val_gap', 'Avaliação vs preço pago', (m) => (m.val_gap == null ? '—' : `${fmt.spct(m.val_gap, 0)}${m.val_gap_chg != null ? ` (${m.val_gap_chg >= 0 ? '+' : '−'}${fmt.n(Math.abs(m.val_gap_chg) * 100, 1)} p.p.)` : ''}`)],
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
const FOLLOW_KEY = 'imopt.follow.v1';
let FOLLOW = [];
try { FOLLOW = JSON.parse(localStorage.getItem(FOLLOW_KEY) || '[]').filter((d) => typeof d === 'string'); } catch { FOLLOW = []; }
function toggleFollow(d) {
  const i = FOLLOW.indexOf(d);
  if (i >= 0) FOLLOW.splice(i, 1); else FOLLOW.push(d);
  try { localStorage.setItem(FOLLOW_KEY, JSON.stringify(FOLLOW)); } catch { /* sem armazenamento */ }
  renderFollow();
  if (selected) select(selected, false);
}
function renderFollow() {
  const sec = $('#follow'), list = FOLLOW.filter((d) => BY[d]);
  sec.hidden = !list.length;
  if (!list.length) return;
  const row = (m) => `<tr><td>${lnk(m.dico, m.name)}</td><td>${fmt.eur(m.price)}</td><td>${fmt.spct(m.price_qoq)}</td><td>${fmt.pct(m.price_growth_1y)}</td>
    <td>${m.score_prev != null ? `${fmt.n(m.score_prev)} → ` : ''}${fmt.n(m.score_overall)} ${pill(m.band)}${m.band_prev && m.band_prev !== m.band ? ' <span class="muted">mudou</span>' : ''}</td>
    <td>${fmt.spct(m.fc_growth_12m)}</td><td>${fmt.pct(m.aff_effort, 0)}</td><td>${m.cycle_phase ? esc(CYCLE_SHORT[m.cycle_phase]) : '—'}</td>
    <td><button type="button" class="btn small" data-unfollow="${esc(m.dico)}" aria-label="Deixar de seguir ${esc(m.name)}">✕</button></td></tr>`;
  $('#follow-body').innerHTML = `<div class="table-wrap"><table class="ol-table"><thead><tr><th>Concelho</th><th>€/m²</th><th>Trimestre${CH ? ` (${qpt(CH.prev_period)}→${qpt(CH.period)})` : ''}</th><th>12 meses</th><th>Score</th><th>Previsão 12m</th><th>Esforço</th><th>Ciclo</th><th></th></tr></thead><tbody>${list.map((d) => row(BY[d])).join('')}</tbody></table></div>`;
}
function renderCompare() {
  $('#compare').hidden = compare.length === 0;
  if (!compare.length) return;
  if (!SER) { ensureSeries().then(renderCompare); return; }
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

// ---------- o que mudou
function renderChanges() {
  if (!CH) return;
  $('#changes').hidden = false;
  $('#changes-title').innerHTML = `O que mudou: ${qpt(CH.prev_period)} → ${qpt(CH.period)} ${info('changes')}`;
  const up = CH.band_changes.filter((c) => BAND_ORDER_JS[c.to] > BAND_ORDER_JS[c.from]);
  const down = CH.band_changes.filter((c) => BAND_ORDER_JS[c.to] < BAND_ORDER_JS[c.from]);
  const toRed = up.filter((c) => c.to === 'red');
  const band = (c) => `<li><span>${lnk(c.dico, c.name)}</span><span class="v">${pill(c.from)} → ${pill(c.to)} <span class="muted">${fmt.n(c.score_prev)} → ${fmt.n(c.score)}</span></span></li>`;
  const mv = (x, pct) => `<li><span>${lnk(x.dico, x.name)}</span><span class="v">${pct ? fmt.spct(x.value) : (x.value >= 0 ? '+' : '−') + fmt.n(Math.abs(x.value), 1)} <span class="muted">${pct ? `${fmt.eur(x.price)}/m²` : `${fmt.n(x.score_prev)} → ${fmt.n(x.score)}`}</span></span></li>`;
  const list = (title, items, f) => (items.length ? `<div><p class="muted"><b>${title}</b></p><ul class="ol-list">${items.map(f).join('')}</ul></div>` : '');
  $('#changes-body').innerHTML = `
    <p class="verdict">No concelho típico, o preço mediano variou <b>${fmt.spct(CH.median_qoq)}</b> num trimestre e subiu em ${Math.round(CH.share_up * 100)}% dos ${CH.n} concelhos.
      Concelhos em risco <b>Elevado</b>: ${CH.n_red_prev} → <b>${CH.n_red}</b>. ${CH.n_band_up} subiram de faixa e ${CH.n_band_down} desceram${toRed.length ? `; ${toRed.length} ${toRed.length === 1 ? 'entrou' : 'entraram'} em Elevado` : ''}.</p>
    <div class="ol-cols">${list('Entraram em Elevado', toRed.slice(0, 10), band)}${list('Desceram de faixa', down.slice(0, 10), band)}</div>
    <div class="ol-cols">${list('Maior subida de preço no trimestre', CH.price_up, (x) => mv(x, true))}${list('Maior descida de preço no trimestre', CH.price_down, (x) => mv(x, true))}</div>
    <div class="ol-cols">${list('Score que mais subiu', CH.score_up, (x) => mv(x, false))}${list('Score que mais desceu', CH.score_down, (x) => mv(x, false))}</div>
    <p class="muted">O preço do INE é uma mediana dos últimos 12 meses: a variação trimestral é suave e chega com atraso.${CH.min_volume ? ` As listas de preço e score só incluem concelhos com pelo menos ${CH.min_volume} avaliações bancárias em 3 meses (mercado com dimensão suficiente) e sem dados voláteis.` : ''} As mudanças de faixa incluem todos os concelhos. A renda é a mesma nos dois trimestres, por isso as mudanças de score vêm dos preços.</p>`;
}
const BAND_ORDER_JS = { green: 0, amber: 1, red: 2 };

// ---------- comprar casa: esforço e comprar ou arrendar
// Calculado no browser com os parâmetros escolhidos; não entra em nenhum score.
const AFF_KEY = 'imopt.afford.v1';
const OWN_COST = 0.013;     // IMI (~0,3%) + manutenção e seguros (~1%) por ano, em % do preço
// Limite aproximado do Banco de Portugal (prestação até 50% do rendimento líquido) na escala de cada rendimento:
// ~40% do salário bruto; ~45% do rendimento após IRS (ainda falta a Segurança Social, ~11%).
const LIMIT = { wage: 0.40, irs: 0.45 };
const hasIrs = () => MUNIS.some((m) => m.irs_median != null);
const affBase = () => (AFF.base === 'irs' && hasIrs() ? 'irs' : 'wage');
const IRS_NOTE = 'O IRS é a mediana por pessoa que declara, incluindo pensionistas e tempo parcial: fica abaixo do salário médio, e o esforço sobe. Com um casal, escolhe 2.';
let PRUDENT = LIMIT.wage;
const incOf = (m) => (affBase() === 'irs' ? (m.irs_median != null ? m.irs_median / 12 : null) : m.income);
const incYear = (m) => (affBase() === 'irs' ? m.irs_year : (m.income_year ? String(m.income_year).slice(0, 4) : null));
const INC_TXT = {
  wage: { one: 'salário médio bruto de quem trabalha no concelho', many: (n) => `${n} salários médios brutos`, short: 'salário', basis: 'bruto' },
  irs: { one: 'rendimento mediano de quem vive no concelho (IRS, após imposto)', many: (n) => `${n} rendimentos medianos (IRS, após imposto)`, short: 'rendimento', basis: 'após IRS' },
};
const incTxt = () => INC_TXT[affBase()];
const AFF_FALLBACK_RATE = 3.5;
const affDefaults = () => ({ area: 90, down: 10, years: 30, rate: null, earners: 1, shock: 2, base: 'wage' });
let AFF = affDefaults();
const affRateNow = () => (OL && OL.rates && OL.rates.rate_now != null ? +OL.rates.rate_now.toFixed(2) : AFF_FALLBACK_RATE);
const affRate = () => (AFF.rate != null ? AFF.rate : affRateNow());
function annuity(loan, ratePct, years) {
  const r = ratePct / 100 / 12, n = years * 12;
  return Math.abs(r) < 1e-12 ? loan / n : (loan * r) / (1 - (1 + r) ** -n);
}
function affordOf(m) {
  if (m.price == null) return {};
  const rate = affRate(), P = m.price * AFF.area, loan = P * (1 - AFF.down / 100);
  const i0 = incOf(m), pay = annuity(loan, rate, AFF.years), inc = i0 != null ? i0 * AFF.earners : null;
  const rentHome = m.rent != null ? m.rent * AFF.area : null;
  return {
    aff_home: P, aff_down: P - loan, aff_pay: pay,
    aff_effort: inc ? pay / inc : null,
    aff_pay_stress: annuity(loan, rate + AFF.shock, AFF.years),
    aff_effort_stress: inc ? annuity(loan, rate + AFF.shock, AFF.years) / inc : null,
    aff_years_salary: inc ? P / (inc * (affBase() === 'irs' ? 12 : 14)) : null,
    aff_inc: inc,
    aff_rent_home: rentHome,
    aff_pay_vs_rent: rentHome ? pay / rentHome - 1 : null,
    aff_rent_effort: rentHome && inc ? rentHome / inc : null,
    // custo de ser dono no 1.º ano (juros sobre o preço todo + IMI/manutenção) menos a renda poupada, em % do preço
    aff_breakeven: rentHome ? rate / 100 + OWN_COST - (rentHome * 12) / P : null,
  };
}
function applyAfford() {
  PRUDENT = LIMIT[affBase()];
  try { parishDerive(); } catch (e) { console.error('freguesias:', e); }
  MUNIS.forEach((m) => Object.assign(m, affordOf(m)));
  if (GEO) GEO.features.forEach((f) => {
    const m = BY[f.properties.dico];
    ['ef', 'br', 'rf', 'tg', 'al', 'vac', 'sec'].forEach((k) => { f.properties[k] = m ? METRIC_VAL[k](m) ?? null : null; });
  });
  if (MAP && MAP.getSource('c')) MAP.getSource('c').setData(GEO);
}
const breakevenTxt = (g) => (g == null ? '' : g <= 0
  ? 'comprar sai mais barato do que arrendar mesmo sem a casa valorizar'
  : `comprar só compensa se a casa valorizar mais de ${fmt.pct(g, 1)}/ano`);
// previsão do modelo para 12 meses face ao ponto de equilíbrio (só comparação; não é aconselhamento)
function fcRange(m) {
  const base = m.nowcast_price ?? m.price;
  if (m.fc_growth_12m == null || !base) return null;
  return { mid: m.fc_growth_12m, lo: m.fc_lo80 != null ? m.fc_lo80 / base - 1 : null, hi: m.fc_hi80 != null ? m.fc_hi80 / base - 1 : null };
}
function fcBeShort(m) {
  const r = fcRange(m);
  return r && m.aff_breakeven != null ? ` · previsão 12m ${fmt.spct(r.mid)} vs equilíbrio ${fmt.spct(m.aff_breakeven)}` : '';
}
function fcBeTxt(m) {
  const r = fcRange(m), be = m.aff_breakeven;
  if (!r || be == null) return '';
  const where = r.lo != null && r.lo > be ? 'mesmo o limite de baixo do intervalo fica acima do ponto de equilíbrio'
    : r.hi != null && r.hi < be ? 'mesmo o limite de cima do intervalo fica abaixo do ponto de equilíbrio'
      : 'o ponto de equilíbrio cai dentro do intervalo, por isso a previsão não decide';
  return ` Previsão do modelo para o preço em 12 meses: ${fmt.spct(r.mid)}${r.lo != null ? ` (80%: ${fmt.spct(r.lo)} a ${fmt.spct(r.hi)})` : ''}, face a um ponto de equilíbrio de ${fmt.spct(be)}/ano — ${where}. Uma previsão a 12 meses não diz nada sobre os anos seguintes e não é aconselhamento.`;
}
function affReadTxt(m) {
  const e = m.aff_effort, who = AFF.earners > 1 ? 'de ' + incTxt().many(AFF.earners) : 'do ' + incTxt().one;
  let t = `Comprar ${AFF.area} m² ao preço mediano custa ${fmt.eur(m.aff_home)}; com ${AFF.down}% de entrada (${fmt.eur(m.aff_down)}) e crédito a ${AFF.years} anos a ${fmt.n(affRate(), 2)}%, a prestação é ${fmt.eur(m.aff_pay)}/mês`;
  if (e != null) t += ` — ${fmt.pct(e, 0)} ${who} (${incYear(m) || 'n/d'}: ${fmt.eur(m.aff_inc)}/mês)${e > PRUDENT ? `, acima de ~${fmt.pct(PRUDENT, 0)}, o equivalente aproximado ao limite do Banco de Portugal (prestação até 50% do rendimento líquido)` : ''}`;
  t += '.';
  if (m.aff_rent_home != null) t += ` Arrendar a mesma casa custa cerca de ${fmt.eur(m.aff_rent_home)}/mês (novos contratos): a prestação fica ${fmt.spct(m.aff_pay_vs_rent, 0)} face à renda, e ${breakevenTxt(m.aff_breakeven)} (já contando juros, IMI e manutenção; sem IMT e escritura). A renda leva ${fmt.pct(m.aff_rent_effort, 0)} do mesmo rendimento.${fcBeTxt(m)}`;
  return t;
}
function affLoad() {
  try {
    const v = JSON.parse(localStorage.getItem(AFF_KEY) || 'null');
    if (v && typeof v === 'object') AFF = { ...affDefaults(), ...v };
  } catch { AFF = affDefaults(); }
}
function affSave() { try { localStorage.setItem(AFF_KEY, JSON.stringify(AFF)); } catch { /* sem armazenamento: não faz mal */ } }
function affForm() {
  const f = $('#aff-form');
  f.base.value = affBase(); f.base.closest('label').hidden = !hasIrs();
  f.area.value = AFF.area; f.down.value = AFF.down; f.years.value = AFF.years; f.earners.value = AFF.earners; f.shock.value = AFF.shock;
  f.rate.value = affRate().toFixed(2);
  const R = OL && OL.rates;
  $('#aff-rate-note').innerHTML = R && R.rate_now != null
    ? `Taxa atual: ${fmt.n(R.rate_now, 2)}% = Euribor 12M de ${esc(R.euribor_month)} (${fmt.n(R.euribor_now, 2)}%) + ${fmt.n(R.spread, 2)} p.p.${R.spread_source && R.spread_source !== 'assumed' ? ` (diferença observada nos novos créditos à habitação, ${esc(R.spread_source)}${R.mortgage_rate_now != null ? `, quando a taxa média foi ${fmt.n(R.mortgage_rate_now, 2)}%` : ''})` : ' (margem assumida)'}.`
    : `Sem taxa atual nesta build: usa-se ${fmt.n(AFF_FALLBACK_RATE, 1)}%.`;
}
function affReadForm() {
  const f = $('#aff-form'), num = (el, lo, hi, d) => { const v = parseFloat(String(el.value).replace(',', '.')); return Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : d; };
  const def = affDefaults();
  AFF.area = Math.round(num(f.area, 20, 400, def.area));
  AFF.down = num(f.down, 0, 90, def.down);
  AFF.years = Math.round(num(f.years, 5, 40, def.years));
  AFF.earners = f.earners.value === '2' ? 2 : 1;
  AFF.base = f.base.value === 'irs' ? 'irs' : 'wage';
  AFF.shock = num(f.shock, 0, 5, def.shock);
  const r = num(f.rate, 0, 15, affRateNow());
  AFF.rate = Math.abs(r - affRateNow()) < 0.005 ? null : r;      // igual à atual: segue a taxa das próximas builds
}
function renderAfford() {
  const body = $('#aff-body');
  const ok = MUNIS.filter((m) => m.aff_effort != null);
  if (!ok.length) { body.innerHTML = '<p class="muted">Sem preços e rendimentos suficientes nesta build.</p>'; return; }
  const P = median(col((x) => x.price)), payTyp = annuity(P * AFF.area * (1 - AFF.down / 100), affRate(), AFF.years);
  const eMed = median(ok.map((m) => m.aff_effort)), over = ok.filter((m) => m.aff_effort > PRUDENT).length;
  const overS = ok.filter((m) => m.aff_effort_stress > PRUDENT).length, payS = annuity(P * AFF.area * (1 - AFF.down / 100), affRate() + AFF.shock, AFF.years);
  const wr = MUNIS.filter((m) => m.aff_pay_vs_rent != null), cheaper = wr.filter((m) => m.aff_pay_vs_rent < 0).length;
  const rfOk = MUNIS.filter((m) => m.aff_rent_effort != null), rfMed = median(rfOk.map((m) => m.aff_rent_effort)), rfOver = rfOk.filter((m) => m.aff_rent_effort > 0.4).length;
  const be = median(wr.map((m) => m.aff_breakeven)), beNeg = wr.filter((m) => m.aff_breakeven <= 0).length;
  // listas só com mercado suficiente (como em "O que mudou"): sem dados voláteis e com >= 20 avaliações em 3 meses
  const hasVol = MUNIS.filter((m) => m.val_count != null).length >= 10;
  const stable = (arr) => arr.filter((m) => !m.volatile && (!hasVol || (m.val_count ?? 0) >= 20));
  const top = (arr, k, asc, n = 10) => stable(arr).sort((a, b) => (a[k] - b[k]) * (asc ? 1 : -1)).slice(0, n);
  const itE = (m) => `<li><span>${lnk(m.dico, m.name)}</span><span class="v">${fmt.pct(m.aff_effort, 0)} <span class="muted">${fmt.eur(m.aff_pay)}/mês · ${incTxt().short} ${fmt.eur(m.aff_inc)}</span></span></li>`;
  const itR = (m) => `<li><span>${lnk(m.dico, m.name)}</span><span class="v">${fmt.spct(m.aff_pay_vs_rent, 0)} <span class="muted">${fmt.eur(m.aff_pay)} vs ${fmt.eur(m.aff_rent_home)} · ${m.aff_breakeven <= 0 ? 'compensa sem valorizar' : `precisa de ${fmt.spct(m.aff_breakeven)}/ano`}</span></span></li>`;
  const who = AFF.earners > 1 ? 'de ' + incTxt().many(AFF.earners) : 'do ' + incTxt().one;
  body.innerHTML = `
    <p class="verdict">No concelho típico (${fmt.eur(P)}/m²), ${AFF.area} m² custam <b>${fmt.eur(P * AFF.area)}</b>: com ${fmt.n(AFF.down, 0)}% de entrada e ${AFF.years} anos a ${fmt.n(affRate(), 2)}%, a prestação é <b>${fmt.eur(payTyp)}/mês</b>.
      A prestação leva, a meio dos concelhos, <b>${fmt.pct(eMed, 0)}</b> ${who}; em <b>${over} de ${ok.length}</b> passa de ${fmt.pct(PRUDENT, 0)}, o equivalente aproximado ao limite do Banco de Portugal.
      <b>Teste de juros</b> ${info('stress')}: com a taxa ${fmt.n(AFF.shock, 1)} p.p. acima (${fmt.n(affRate() + AFF.shock, 2)}%), a mesma prestação típica passa para <b>${fmt.eur(payS)}</b> (${fmt.spct(payS / payTyp - 1, 0)}) e ${overS} concelhos ficam acima de ${fmt.pct(PRUDENT, 0)}.
      ${wr.length ? `Nos ${wr.length} concelhos com renda publicada, a prestação é mais baixa do que a renda da mesma casa em <b>${cheaper}</b>; contando juros, IMI e manutenção, ${be <= 0 ? 'no concelho típico comprar sai mais barato do que arrendar mesmo sem a casa valorizar' : `no concelho típico comprar só sai mais barato do que arrendar se a casa valorizar mais de <b>${fmt.pct(be, 1)}/ano</b>`} — em <b>${beNeg} dos ${wr.length}</b> compensa mesmo sem valorizar.` : ''}
      ${rfOk.length ? ` <b>Arrendar</b> ${info('rent_effort')} a mesma casa leva, a meio dos concelhos, <b>${fmt.pct(rfMed, 0)}</b> ${AFF.earners > 1 ? 'dos rendimentos' : 'do ' + incTxt().short}; em ${rfOver} de ${rfOk.length} passa de 40%.` : ''}</p>
    <div class="ol-cols">
      <div><p class="muted"><b>Menor esforço</b> (prestação ÷ ${incTxt().short})</p><ul class="ol-list wrap-list">${top(ok, 'aff_effort', true).map(itE).join('')}</ul></div>
      <div><p class="muted"><b>Maior esforço</b></p><ul class="ol-list wrap-list">${top(ok, 'aff_effort', false).map(itE).join('')}</ul></div>
    </div>
    ${wr.length ? `<div class="ol-cols">
      <div><p class="muted"><b>Prestação mais abaixo da renda</b> ${info('buy_rent')}</p><ul class="ol-list wrap-list">${top(wr, 'aff_pay_vs_rent', true).map(itR).join('')}</ul></div>
      <div><p class="muted"><b>Prestação mais acima da renda</b></p><ul class="ol-list wrap-list">${top(wr, 'aff_pay_vs_rent', false).map(itR).join('')}</ul></div>
    </div>` : ''}
    <p class="aff-map"><button type="button" class="btn" data-m="ef">Ver esforço no mapa</button> <button type="button" class="btn" data-m="br">Ver prestação vs renda no mapa</button></p>
    <ul class="read muted">
      <li>Preço: mediana de todas as vendas do concelho (INE, 12 meses), casas grandes e pequenas, novas e usadas. A casa que procuras pode custar bem mais ou menos por m².</li>
      ${affBase() === 'irs'
        ? `<li>Rendimento: mediana do rendimento bruto declarado no IRS, após imposto, por pessoa que declara, no concelho onde vive (INE/AT, ${esc(String((ok.find((m) => m.irs_year) || {}).irs_year || 'ano n/d'))}), anual ÷ 12. Inclui pensões e outros rendimentos; não desconta a Segurança Social. ${IRS_NOTE} É de há cerca de 2 anos: com os rendimentos a subir, o esforço real é um pouco menor. Corrige o problema dos concelhos-dormitório (conta quem lá vive). Os anos de rendimento usam o valor anual.</li>`
        : `<li>Salário: ganho médio mensal bruto por trabalhador por conta de outrem (INE, ${esc(String((ok.find((m) => m.income_year) || {}).income_year || '').slice(0, 4) || 'ano n/d')}), não o rendimento líquido nem o do agregado. É o salário de quem trabalha no concelho, não de quem lá vive: nos concelhos-dormitório (por exemplo à volta de Lisboa) muitos residentes ganham mais noutro concelho, e o esforço aparece exagerado.${hasIrs() ? ' Escolhe "IRS de quem vive" para ver o rendimento de quem lá mora (mais baixo, por ser mediano e incluir pensionistas).' : ''} Os anos de salário usam 14 meses.</li>`}
      <li>Renda: mediana de novos contratos (€/m²) × a mesma área. A prestação inclui amortização, que é poupança: por isso o ponto de equilíbrio é a medida mais justa. Nos concelhos baratos do interior, muitas casas vendidas são antigas ou precisam de obras, enquanto as arrendadas estão prontas a habitar: aí comprar parece mais vantajoso do que é.</li>
      <li>Fora das contas: IMT, imposto do selo, escritura e comissões (vários milhares de euros, pesam mais em quem fica poucos anos), seguros obrigatórios do crédito, e mudanças de taxa ao longo do empréstimo. As listas só incluem concelhos sem dados voláteis${hasVol ? ' e com pelo menos 20 avaliações bancárias em 3 meses' : ''}.</li>
    </ul>`;
}
function initAfford() {
  affLoad(); affForm(); applyAfford(); renderAfford();
  const update = () => {
    affReadForm(); affSave(); applyAfford(); renderAfford();
    try { renderTable(); } catch (e) { console.error(e); }
    if (['ef', 'br', 'rf'].includes($('#metric').value) || (LEVEL === 'f' && $('#metric-f').value === 'f_ef')) updateMetric();
    renderFollow();
    if (selected) select(selected, false);
    if (compare.length) renderCompare();
  };
  $('#aff-form').addEventListener('change', update);
  $('#aff-form').addEventListener('submit', (e) => { e.preventDefault(); update(); });
  $('#aff-reset').addEventListener('click', () => { AFF = affDefaults(); affForm(); update(); });
  $('#aff-body').addEventListener('click', (e) => {
    const a = e.target.closest('a[data-d]'); if (a) { e.preventDefault(); select(a.dataset.d); return; }
    const b = e.target.closest('[data-m]');
    if (b) { if (LEVEL !== 'c') setLevel('c'); $('#metric').value = b.dataset.m; updateMetric(); $('#mapsec').scrollIntoView({ behavior: 'smooth', block: 'start' }); }
  });
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
  const first = Math.min(...MUNIS.map((x) => (x.rent_first != null ? x.rent_first : Infinity)));
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
    <p>${F.effects.some((e) => e.feature === 'log_irs') ? 'Salário, rendimento de quem vive' : 'Rendimento'}, densidade, envelhecimento, migração, litoral, distância a Lisboa/Porto${F.effects.some((e) => e.feature === 'secondary_share') ? ', 2.ª habitação' : ''} e região explicam <b>${fmt.pct(F.r2_cv, 0)}</b> das diferenças de preço entre ${F.n} concelhos (validação cruzada: medido em concelhos que o modelo não viu). ${Math.round(F.share_within_20pct * 100)}% dos concelhos estão a menos de 20% do seu valor justo. Mantendo o resto igual: ${eff.join('; ')}.</p>
    <div class="ol-cols">
      <div><p class="muted"><b>Mais acima do valor justo</b> (preço vs valor justo, €/m²)</p><ul class="ol-list">${F.top_above.map(item).join('')}</ul></div>
      <div><p class="muted"><b>Mais abaixo do valor justo</b></p><ul class="ol-list">${F.top_below.map(item).join('')}</ul></div>
    </div>
    ${F.candidate_tests && F.candidate_tests.length ? `<p class="muted"><b>Variáveis novas testadas</b> (${esc(F.rule)}): ${F.candidate_tests.map((t) => `${esc(t.label)} ${t.passes ? '<b>entrou</b>' : 'ficou de fora'} (R² ${fmt.n(t.r2_base, 3)} → ${fmt.n(t.r2_with, 3)})`).join('; ')}.${F.candidate_tests.some((t) => t.passes && t.feature === 'log_irs') ? ' Concelhos sem IRS publicado ficam sem valor justo.' : ''} Atenção: o rendimento e a 2.ª habitação também são consequência dos preços (quem pode pagar mais vive onde é caro), por isso estes efeitos descrevem, não provam causa.</p>` : ''}
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
const CYCLE_SHORT = { up_up: 'preço a subir, mais compras', up_down: 'preço a subir, menos compras', down_down: 'preço a descer, menos compras', down_up: 'preço a descer, mais compras' };
function olSignals(G) {
  const name = (r) => esc(r.label || r.signal);
  const row = (r) => `<tr><td>${name(r)}</td><td>${r.gain_fc == null ? '—' : fmt.spct(r.gain_fc, 1)}</td><td>${r.gain_h1 == null ? '—' : fmt.spct(r.gain_h1, 1)}</td><td>${r.passes ? '<b>passa</b>' : esc(r.status)}</td></tr>`;
  const lab = Object.fromEntries(G.rows.map((r) => [r.signal, r.label]));
  const ex = G.exploratory || {};
  const exTxt = Object.entries(ex).map(([k, e]) => `${k === 'apt' ? 'apartamentos' : 'moradias'} (${e.n_origins} origens desde ${qpt(e.first_origin)}): ${e.rows.map((r) => `${esc(lab[r.signal] ? lab[r.signal].split(' (')[0] : r.signal)} ${fmt.spct(r.gain_fc, 1)}`).join(', ')}`).join('; ');
  const pass = G.rows.filter((r) => r.passes);
  return `<h3>Que sinais ajudam a prever o preço? ${info('signals')}</h3>
    <p>${pass.length ? `${pass.length} ${pass.length === 1 ? 'sinal passa' : 'sinais passam'} a regra: ${pass.map(name).join(', ')}.` : '<b>Nenhum dos sinais novos melhora a previsão</b> das vendas do INE pela regra fixada: ficam como contexto, não entram no modelo.'} Ganho = redução do erro médio face à previsão base (positivo = melhor), a ${G.h_fc} trimestres e a 1 trimestre, em ${qpt(G.first_origin)}–${qpt(G.last_origin)}.</p>
    <div class="table-wrap"><table class="ol-table"><thead><tr><th>Sinal</th><th>Ganho a ${G.h_fc} trim.</th><th>Ganho a 1 trim.</th><th>Regra</th></tr></thead><tbody>${G.rows.map(row).join('')}</tbody></table></div>
    ${exTxt ? `<p class="muted">Exploratório, com a avaliação bancária (não decide): ${exTxt}. Resultados de sinal trocado entre apartamentos e moradias indicam ruído, não um efeito real. As vendas do INE só existem desde 2019: a amostra é curta e o teste tem pouca potência.</p>` : ''}`;
}
function olCredit(C) {
  return `<h3>Crédito à habitação novo ${info('credit')}</h3>
    <p>Nos 12 meses até ${esc(C.until)} os bancos concederam <b>${fmt.n(C.last12 / 1000, 1)} mil M€</b> em novos créditos à habitação${C.change != null ? ` (${fmt.spct(C.change, 0)} face aos 12 meses anteriores)` : ''}; ${C.peak.period === C.until ? 'é o valor mais alto da série (nominal, desde 2003)' : `o máximo da série foi ${fmt.n(C.peak.value / 1000, 1)} mil M€ (12 meses até ${esc(C.peak.period)})`}.${C.reneg_share != null ? ` Cerca de ${fmt.pct(C.reneg_share, 0)} foram renegociações de créditos antigos; o crédito novo "puro" somou ${fmt.n(C.pure12 / 1000, 1)} mil M€.` : ''}</p>
    <div class="chart-cap"><span>Novos créditos à habitação, soma de 12 meses (M€, nominal)</span></div><div id="ol-credit" class="chart"></div>`;
}
function olCycle(C) {
  const c = C.counts, late = C.late.slice(0, 10).map((x) => `<li><span>${lnk(x.dico, x.name)}</span><span class="v">compras ${fmt.spct(x.v, 0)} <span class="muted">preço ${fmt.spct(x.g)} · ${fmt.n(x.n, 0)} aval.</span></span></li>`).join('');
  const nat = C.national && C.national.length ? C.national[C.national.length - 1] : null;
  return `<h3>Ciclo preço–volume ${info('cycle')}</h3>
    <p>Nos ${C.n} concelhos com mercado suficiente (≥ ${C.min_volume} avaliações em 3 meses): <b>${c.up_up}</b> com preço a subir e mais compras com crédito, <b>${c.up_down}</b> com preço a subir mas <b>menos</b> compras, ${c.down_down} com preço a descer e menos compras, ${c.down_up} com preço a descer e mais compras.
      No concelho típico, o preço subiu ${fmt.spct(C.median_price_growth)} e as compras com crédito ${fmt.spct(C.median_volume_growth, 0)} num ano.${nat ? ` No país, no trimestre ${qpt(nat[0])}: avaliação ${fmt.spct(nat[1])} e número de avaliações ${fmt.spct(nat[2], 0)} face a um ano antes.` : ''}</p>
    <div class="chart-cap"><span>Cada ponto é um concelho: preço a 12 meses (vertical) contra compras com crédito num ano (horizontal). Clica num ponto para o detalhe.</span></div>
    <div id="ol-cycle" class="chart tall"></div>
    ${C.national ? '<div class="chart-cap"><span>País, por trimestre: variação num ano da avaliação bancária (€/m²) e do número de avaliações</span></div><div id="ol-cycle-nat" class="chart"></div>' : ''}
    <p class="muted"><b>Preço a subir, compras a cair mais</b> (fase típica de fim de ciclo)</p><ul class="ol-list wrap-list">${late}</ul>
    <p class="muted">A queda do volume costuma vir antes do abrandamento dos preços, mas o desfasamento varia muito e nem toda a queda de volume acaba em descida de preços (pode ser falta de casas à venda). O volume só conta compras com crédito.</p>`;
}
function cycleChart(id, C) {
  const txt = css('--muted'), line = css('--line');
  const late = C.points.filter((p) => p.phase === 'up_down'), other = C.points.filter((p) => p.phase !== 'up_down');
  const pts = (arr) => arr.map((p) => ({ value: [p.v * 100, p.g * 100], name: p.name, dico: p.dico, n: p.n }));
  const lim = (k) => { const v = C.points.map((p) => Math.abs(p[k])).sort((a, b) => a - b); return Math.ceil(quantile(v, 0.97) * 100 / 10) * 10 || 10; };
  const lx = lim('v'), ly = lim('g');
  const ch = freshChart(id);
  ch.setOption({
    animation: false,
    grid: { left: 8, right: 16, top: 34, bottom: 28, containLabel: true },
    legend: { top: 0, right: 0, textStyle: { color: txt } },
    tooltip: { trigger: 'item', confine: true, formatter: (p) => `<b>${esc(p.data.name)}</b><br>Preço: ${fmt.spct(p.data.value[1] / 100)}<br>Compras com crédito: ${fmt.spct(p.data.value[0] / 100, 0)}<br>${fmt.n(p.data.n, 0)} avaliações em 3 meses<br><span style="color:#888">clica para o detalhe</span>` },
    xAxis: { type: 'value', min: -lx, max: lx, name: 'Compras com crédito, variação num ano (%)', nameLocation: 'middle', nameGap: 22, nameTextStyle: { color: txt, fontSize: 11 }, axisLabel: { color: txt, formatter: (v) => v + '%' }, splitLine: { lineStyle: { color: line } } },
    yAxis: { type: 'value', min: -Math.min(ly, 20), max: ly, axisLabel: { color: txt, formatter: (v) => v + '%' }, splitLine: { lineStyle: { color: line } } },
    series: [
      { name: 'Preço a subir, menos compras', type: 'scatter', symbolSize: 9, itemStyle: { color: css('--s2'), borderColor: css('--card'), borderWidth: 1 }, data: pts(late),
        markLine: { silent: true, symbol: 'none', lineStyle: { color: txt, type: 'solid', width: 1 }, label: { show: false }, data: [{ xAxis: 0 }, { yAxis: 0 }] } },
      { name: 'Restantes', type: 'scatter', symbolSize: 9, itemStyle: { color: css('--s1'), borderColor: css('--card'), borderWidth: 1 }, data: pts(other) },
    ],
  }, true);
  ch.on('click', (e) => e.data && e.data.dico && select(e.data.dico));
}
function olValGap(V) {
  const it = (x) => `<li><span>${lnk(x.dico, x.name)}</span><span class="v">${x.value >= 0 ? '+' : '−'}${fmt.n(Math.abs(x.value) * 100, 0)} p.p. <span class="muted">agora ${fmt.spct(x.gap, 0)}</span></span></li>`;
  const last = V.series.length ? V.series[V.series.length - 1] : null, first = V.series.length ? V.series[0] : null;
  return `<h3>Avaliação bancária vs preço pago ${info('val_gap')}</h3>
    <p>No concelho típico, a avaliação bancária média dos 12 meses até ${qpt(V.period)} está <b>${fmt.spct(V.median_gap, 0)}</b> face ao preço mediano de venda${V.median_change != null ? `, ${V.median_change >= 0 ? 'mais' : 'menos'} ${fmt.n(Math.abs(V.median_change) * 100, 1)} p.p. do que um ano antes (a diferença ${V.median_change < 0 ? 'alargou-se: as avaliações ficaram para trás dos preços' : 'estreitou-se'} em ${Math.round((V.median_change < 0 ? 1 - V.share_widening : V.share_widening) * 100)}% dos ${V.n_change} concelhos)` : ''}.${last && first ? ` No país: ${fmt.spct(first[1], 1)} em ${qpt(first[0])}, ${fmt.spct(last[1], 1)} em ${qpt(last[0])}.` : ''}</p>
    ${V.series.length > 3 ? '<div id="ol-valgap" class="chart"></div>' : ''}
    <div class="ol-cols">
      <div><p class="muted"><b>Avaliação a ficar para trás do preço</b> (variação num ano)</p><ul class="ol-list wrap-list">${V.lagging.map(it).join('')}</ul></div>
      <div><p class="muted"><b>Avaliação a avançar mais do que o preço</b></p><ul class="ol-list wrap-list">${V.leading.map(it).join('')}</ul></div>
    </div>
    <p class="muted">O nível da diferença reflete sobretudo casas diferentes (a avaliação só cobre compras com crédito). ${V.min_volume ? `As listas só incluem concelhos com pelo menos ${V.min_volume} avaliações em 3 meses.` : ''} Concelhos com avaliação publicada em pelo menos 9 dos 12 meses.</p>`;
}
function olCosts(K) {
  const row = (label, x) => (x ? `<tr><td>${label}</td><td>${fmt.spct(x.yoy)}</td><td>${fmt.spct(x.since_2021, 0)}</td></tr>` : '');
  const pn = K.prices.new, pe = K.prices.existing;
  return `<h3>Custo de construção vs preço ${info('costs')}</h3>
    <p>O custo de construir habitação nova subiu ${fmt.spct(K.yoy)} no último ano e ${fmt.spct(K.since_2021, 0)} desde 2021 (até ${esc(K.until)})${pn ? `; o preço das casas novas subiu ${fmt.spct(pn.since_2021, 0)} no mesmo período${pe ? ` e o das usadas ${fmt.spct(pe.since_2021, 0)}` : ''}` : ''}.${pn && pn.since_2021 > K.since_2021 * 1.3 ? ' Os preços subiram bem mais do que o custo da obra: a diferença vem de outros fatores (terreno, procura, margens), não do custo de construir.' : ''}</p>
    <div class="table-wrap"><table class="ol-table"><thead><tr><th></th><th>Último ano</th><th>Desde 2021</th></tr></thead><tbody>
      ${row('Custo de construção (total)', K)}${row('— materiais', K.parts.materials)}${row('— mão de obra', K.parts.labour)}
      ${row(`Preço das casas novas (${pn ? qpt(pn.until) : ''})`, pn)}${row('Preço das casas usadas', pe)}</tbody></table></div>`;
}
function olSupply(S) {
  const L = S.series.licensed || [], C = S.series.completed || [];
  const ll = L[L.length - 1], lc = C[C.length - 1];
  const peak = (arr) => arr.reduce((a, b) => (b[1] > a[1] ? b : a), arr[0]);
  const low = (arr) => arr.reduce((a, b) => (b[1] < a[1] ? b : a), arr[0]);
  const rl = S.recent.licensed, rc = S.recent.completed;
  return `<h3>Construção nova ${info('supply_new')}</h3>
    <p>${ll ? `Em ${ll[0]} licenciaram-se <b>${fmt.n(ll[1], 0)}</b> fogos novos${ll[2] != null ? ` (${fmt.n(ll[2], 1)} por 1000 alojamentos)` : ''}, contra ${fmt.n(low(L)[1], 0)} no mínimo de ${low(L)[0]} e ${fmt.n(peak(L)[1], 0)} em ${peak(L)[0]}.` : ''}
      ${lc ? ` Concluíram-se ${fmt.n(lc[1], 0)} em ${lc[0]}${lc[2] != null ? ` (${fmt.n(lc[2], 1)} por 1000)` : ''}, longe dos ${fmt.n(peak(C)[1], 0)} de ${peak(C)[0]}.` : ''}
      ${rl && rl.change != null ? ` Nos 12 meses até ${esc(rl.until)}: ${fmt.n(rl.last12, 0)} licenciados (${fmt.spct(rl.change, 0)} face aos 12 meses anteriores)` : ''}${rc && rc.change != null ? `; nos 4 trimestres até ${qpt(rc.until)}: ${fmt.n(rc.last12, 0)} concluídos (${fmt.spct(rc.change, 0)})` : ''}.</p>
    <div class="chart-cap"><span>País: fogos novos por ano (anos completos)</span></div><div id="ol-supply" class="chart"></div>
    ${S.mix ? `<p class="muted" style="margin-top:10px"><b>Que casas se licenciam</b> — peso de cada tipologia nos fogos licenciados, face à subida do preço de venda dessa tipologia no país</p>
    <div class="table-wrap"><table class="ol-table"><thead><tr><th>Tipologia</th><th>% das licenças ${S.mix.year_before}</th><th>% das licenças ${S.mix.year}</th><th>Preço, 12 meses (país)</th></tr></thead><tbody>
    ${S.mix.rows.map((r) => `<tr><td>${esc(r.label)}</td><td>${fmt.pct(r.share_before, 0)}</td><td>${fmt.pct(r.share_now, 0)}</td><td>${fmt.spct(r.price_growth_1y)}</td></tr>`).join('')}</tbody></table></div>` : ''}
    <p class="muted">O INE só publica licenças e conclusões até às regiões, não por concelho. Licenças são oferta futura (2 a 3 anos até à conclusão) e nem todas são construídas. Só contexto: não entra no score.</p>`;
}
function olEffortMuni(E) {
  const last = E.median[E.median.length - 1], first = E.median.find((r) => r[1] != null);
  const it = (r) => `<li><span>${lnk(r.dico, r.name)}</span><span class="v">${fmt.pct(r.from, 0)} → ${fmt.pct(r.to, 0)}</span></li>`;
  return `<p><b>Por concelho</b> ${info('effort_hist_muni')}: a meio dos concelhos, a prestação de 90 m² ao preço local passou de ${fmt.pct(first[1], 0)} para <b>${fmt.pct(last[1], 0)}</b> do rendimento mediano do IRS entre ${qpt(first[0])} e ${qpt(last[0])}${E.n_doubled != null ? `; em <b>${E.n_doubled} de ${E.n_compared}</b> concelhos o esforço pelo menos duplicou` : ''}. O gráfico de cada concelho está no detalhe.</p>
    ${E.risers ? `<p class="muted"><b>Onde o esforço mais subiu</b> (IRS, concelhos com 20+ avaliações em 3 meses)</p><ul class="ol-list wrap-list">${E.risers.map(it).join('')}</ul>` : ''}`;
}
function olAffHist(A) {
  const s = A.series, last = A.last, first = A.first;
  const pre = s.find((r) => r.period === '2019Q4') || s.find((r) => r.period.startsWith('2019'));
  const eff = (r) => (r.effort_irs != null ? r.effort_irs : r.effort_wage);
  const lbl = last.effort_irs != null ? 'do rendimento mediano (IRS, após imposto)' : 'do salário médio bruto';
  const key = last.effort_irs != null ? 'effort_irs' : 'effort_wage';
  return `<h3>Esforço de compra ao longo do tempo ${info('afford_hist')}</h3>
    <p>Para uma casa de ${A.area} m² à avaliação bancária mediana do país, com ${Math.round(A.ltv * 100)}% de crédito a ${A.years} anos à taxa média dos novos créditos, a prestação era de ${fmt.eur(first.payment)}/mês em ${qpt(first.period)}${pre ? `, ${fmt.eur(pre.payment)} no fim de 2019` : ''} e é de <b>${fmt.eur(last.payment)}/mês</b> em ${qpt(last.period)} (taxa ${fmt.n(last.rate, 2)}%, avaliação ${fmt.eur(last.price)}/m²).
      ${eff(last) != null ? `Isto é <b>${fmt.pct(eff(last), 0)}</b> ${lbl} do país${pre && eff(pre) != null ? `, contra ${fmt.pct(eff(pre), 0)} no fim de 2019` : ''}.` : ''}
      ${A[key + '_max'] ? ` Desde ${qpt(s.find((r) => r[key] != null).period)}: máximo de ${fmt.pct(A[key + '_max'].value, 0)} em ${qpt(A[key + '_max'].period)} e mínimo de ${fmt.pct(A[key + '_min'].value, 0)} em ${qpt(A[key + '_min'].period)}.` : ''}
      A prestação mais baixa da série foi ${fmt.eur(A.payment_min.value)} em ${qpt(A.payment_min.period)}, quando os juros estavam no mínimo.</p>
    <div class="chart-cap"><span>Prestação mensal da mesma casa (€)</span></div><div id="ol-ah-pay" class="chart"></div>
    ${s.some((r) => eff(r) != null) ? '<div class="chart-cap"><span>Prestação em % do rendimento do país</span></div><div id="ol-ah-eff" class="chart"></div>' : ''}
    <p class="muted">A avaliação bancária só cobre casas compradas com crédito. Rendimentos nacionais: ${s.some((r) => r.irs_year) ? 'mediana do IRS após imposto (÷ 12)' : ''}${s.some((r) => r.irs_year) && s.some((r) => r.wage_year) ? ' e ' : ''}${s.some((r) => r.wage_year) ? 'salário médio bruto' : ''}; depois do último ano publicado repete-se esse ano (no máximo 2 anos), o que exagera um pouco o esforço recente.${s.some((r) => r.irs_year) ? ' A linha do IRS fica acima da do salário porque a mediana de quem declara IRS (incluindo pensionistas e tempo parcial, depois do imposto) é mais baixa do que o salário médio bruto.' : ''}</p>`;
}
function olEurope(E) {
  const pt = E.pt;
  return `<h3>Portugal face à Europa ${info('europe')}</h3>
    <p>Até ${qpt(E.period)}, os preços da habitação em Portugal subiram <b>${fmt.spct(pt.real_2015, 0)}</b> acima da inflação desde 2015 (${fmt.spct(pt.nominal_2015, 0)} sem descontar a inflação) — <b>${E.rank}.º</b> de ${E.n} países da UE com dados; a mediana dos países foi ${fmt.spct(E.median_real_2015, 0)}.
      No último ano: ${fmt.spct(pt.real_1y)} acima da inflação${E.rank_1y ? ` (${E.rank_1y}.º de ${E.n_1y}; mediana ${fmt.spct(E.median_real_1y)})` : ''}.${pt.from_peak < -0.005 ? ` Está ${fmt.spct(pt.from_peak, 0)} abaixo do máximo real.` : ' Está no máximo da série, em termos reais.'}</p>
    <div class="chart-cap"><span>Subida real desde 2015 por país (HPI ÷ IHPC)</span></div><div id="ol-eu-bars" class="chart" style="height:${Math.max(320, E.countries.length * 18 + 40)}px"></div>
    <div class="chart-cap"><span>Preço real, 2015 = 100: Portugal e a mediana dos países da UE</span></div><div id="ol-eu-line" class="chart"></div>
    <p class="muted">Compara ritmos de subida, não níveis de preço. A subida forte em Portugal partiu de preços muito baixos depois da crise de 2011–2013. Fonte: Eurostat (prc_hpi_q, prc_hicp_midx).</p>`;
}
function euBars(id, E) {
  const txt = css('--muted'), line = css('--line');
  const rows = E.countries.slice().reverse();
  freshChart(id).setOption({
    animation: false,
    grid: { left: 8, right: 40, top: 8, bottom: 8, containLabel: true },
    tooltip: { trigger: 'item', confine: true, formatter: (p) => { const r = rows[p.dataIndex]; return `<b>${esc(r.name)}</b><br>Real desde 2015: ${fmt.spct(r.real_2015, 0)}<br>Nominal: ${fmt.spct(r.nominal_2015, 0)}<br>Real no último ano: ${fmt.spct(r.real_1y)}`; } },
    xAxis: { type: 'value', axisLabel: { color: txt, formatter: (v) => v + '%' }, splitLine: { lineStyle: { color: line } } },
    yAxis: { type: 'category', data: rows.map((r) => r.name), axisLabel: { color: txt, fontSize: 11 }, axisLine: { lineStyle: { color: line } } },
    series: [{ type: 'bar', barMaxWidth: 12, label: { show: true, position: 'right', color: txt, fontSize: 10, formatter: (p) => fmt.spct(p.value / 100, 0) },
      data: rows.map((r) => ({ value: +(r.real_2015 * 100).toFixed(1), itemStyle: { color: r.geo === 'PT' ? css('--s2') : css('--s1'), borderRadius: r.real_2015 < 0 ? [4, 0, 0, 4] : [0, 4, 4, 0] } })) }],
  }, true);
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
  if (OL.europe) add('europa', () => olEurope(OL.europe));
  if (OL.afford_hist) add('esforço no tempo', () => olAffHist(OL.afford_hist) + (OL.effort_muni ? olEffortMuni(OL.effort_muni) : ''));
  if (OL.supply) add('oferta', () => olSupply(OL.supply));
  if (OL.costs) add('custos', () => olCosts(OL.costs));
  if (OL.credit) add('crédito', () => olCredit(OL.credit));
  if (OL.signals) add('sinais', () => olSignals(OL.signals));
  if (OL.cycle) add('ciclo', () => olCycle(OL.cycle));
  if (OL.val_gap) add('avaliação', () => olValGap(OL.val_gap));
  parts.push(`<h3>Limites</h3><ul class="read">${(OL.limits || []).map((l) => `<li>${esc(l)}</li>`).join('')}</ul>`);
  body.innerHTML = parts.join('');
  const todo = [];
  const chart = (name, fn) => todo.push([name, fn]);
  const runCharts = () => todo.splice(0).forEach(([name, fn]) => { try { fn(); } catch (e) { console.error(`Falha no gráfico ${name}:`, e); } });
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { io.disconnect(); runCharts(); } }, { rootMargin: '600px 0px' });
    io.observe($('#outlook'));
    window.addEventListener('beforeprint', runCharts);
  } else setTimeout(runCharts, 0);
  if ($('#ol-regimes')) chart('regimes', () => regimesChart('ol-regimes', OL.regimes));
  if ($('#ol-cycle')) chart('ciclo', () => cycleChart('ol-cycle', OL.cycle));
  if ($('#ol-credit')) chart('crédito', () => lineChart('ol-credit', 'Crédito', [
    { name: 'Novas operações', data: OL.credit.series, fmt: (v) => fmt.n(v, 0) + ' M€' },
    ...(OL.credit.series_pure ? [{ name: 'Crédito novo puro', data: OL.credit.series_pure, fmt: (v) => fmt.n(v, 0) + ' M€' }] : []),
  ], { names: ['M€ em 12 meses'], notitle: true }));
  if ($('#ol-eu-bars')) chart('europa barras', () => euBars('ol-eu-bars', OL.europe));
  if ($('#ol-eu-line')) chart('europa linha', () => lineChart('ol-eu-line', 'Preço real', [
    { name: 'Portugal', data: OL.europe.series.PT.map((r) => [qpt(r[0]), r[1]]), fmt: (v) => fmt.n(v, 0) },
    { name: 'Mediana UE', data: OL.europe.series.median.map((r) => [qpt(r[0]), r[1]]), fmt: (v) => fmt.n(v, 0) },
  ], { names: ['2015 = 100'], refs: [{ y: 100, label: '2015' }], notitle: true }));
  if ($('#ol-supply')) chart('oferta', () => lineChart('ol-supply', 'Fogos novos', [
    ...(OL.supply.series.licensed ? [{ name: 'Licenciados', data: OL.supply.series.licensed.map((r) => [r[0], r[1]]), fmt: (v) => fmt.n(v, 0) }] : []),
    ...(OL.supply.series.completed ? [{ name: 'Concluídos', data: OL.supply.series.completed.map((r) => [r[0], r[1]]), fmt: (v) => fmt.n(v, 0) }] : []),
  ], { names: ['Fogos por ano'], notitle: true }));
  if ($('#ol-ah-pay')) chart('esforço €', () => lineChart('ol-ah-pay', 'Prestação', [
    { name: 'Prestação', data: OL.afford_hist.series.map((r) => [qpt(r.period), Math.round(r.payment)]), fmt: (v) => fmt.eur(v) + '/mês' },
  ], { notitle: true }));
  if ($('#ol-ah-eff')) chart('esforço %', () => lineChart('ol-ah-eff', 'Esforço', [
    ...(OL.afford_hist.series.some((r) => r.effort_irs != null) ? [{ name: 'Rendimento IRS após imposto', data: OL.afford_hist.series.filter((r) => r.effort_irs != null).map((r) => [qpt(r.period), +(r.effort_irs * 100).toFixed(1)]), fmt: (v) => fmt.n(v, 0) + '%' }] : []),
    ...(OL.afford_hist.series.some((r) => r.effort_wage != null) ? [{ name: 'Salário médio bruto', data: OL.afford_hist.series.filter((r) => r.effort_wage != null).map((r) => [qpt(r.period), +(r.effort_wage * 100).toFixed(1)]), fmt: (v) => fmt.n(v, 0) + '%' }] : []),
  ], { names: ['% do rendimento mensal'], notitle: true }));
  if ($('#ol-cycle-nat')) chart('ciclo nacional', () => lineChart('ol-cycle-nat', 'País: variação num ano', [
    { name: 'Avaliação bancária (€/m²)', data: OL.cycle.national.map((r) => [qpt(r[0]), +(r[1] * 100).toFixed(1)]), fmt: (v) => fmt.spct(v / 100) },
    { name: 'Número de avaliações', data: OL.cycle.national.map((r) => [qpt(r[0]), +(r[2] * 100).toFixed(1)]), fmt: (v) => fmt.spct(v / 100, 0) },
  ], { names: ['Variação num ano (%)'], refs: [{ y: 0, label: '0' }], notitle: true }));
  if ($('#ol-valgap')) chart('avaliação', () => lineChart('ol-valgap', 'País', [
    { name: 'Avaliação face ao preço pago', data: OL.val_gap.series.map((r) => [qpt(r[0]), +(r[1] * 100).toFixed(1)]), fmt: (v) => fmt.spct(v / 100) },
  ], { names: ['Avaliação vs preço (%), país'], refs: [{ y: 0, label: '0' }], notitle: true }));
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
  rent_to_income: 'r2i', migration_balance: 'migration', aff_effort: 'effort', aff_pay_vs_rent: 'buy_rent', aff_rent_effort: 'rent_effort', fc_growth_12m: 'fc12', score_overall: 'score_overall', band: 'band' };
const COLS = [
  ['name', 'Concelho', (m) => esc(m.name) + (m.volatile ? ' <span title="Preços muito voláteis (poucas transações): score atenuado">⚠</span>' : '')], ['price', '€/m²', (m) => fmt.eur(m.price)],
  ['price_growth_1y', 'Var. 12m', (m) => fmt.pct(m.price_growth_1y)], ['rent', 'Renda €/m²', (m) => (m.rent == null ? '—' : fmt.eur2(m.rent))],
  ['gross_yield', 'Rendib.', (m) => fmt.pct(m.gross_yield, 2)],
  ['price_to_income_months', 'Preço/rend. (m)', (m) => fmt.n(m.price_to_income_months, 1)],
  ['rent_to_income', 'Renda/rend.', (m) => (m.rent_to_income == null ? '—' : fmt.pct(m.rent_to_income, 1))],
  ['aff_effort', 'Esforço', (m) => fmt.pct(m.aff_effort, 0)],
  ['aff_pay_vs_rent', 'Prest./renda', (m) => fmt.spct(m.aff_pay_vs_rent, 0)],
  ['aff_rent_effort', 'Esforço arrend.', (m) => fmt.pct(m.aff_rent_effort, 0)],
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

// ---------- O meu imóvel (análise não vinculativa, tudo calculado no browser)
const IM_KEY = 'imopt.imovel.v1';
let histP = null, HIST = null;
function ensureHist() {
  if (!histP) histP = j('data/history.json').then((d) => { HIST = d; }).catch(() => { HIST = { parish: {}, val: {}, hicp: [] }; });
  return histP;
}
const qOfMonth = (ym) => {
  const mt = /^(\d{4})-(\d{2})$/.exec(String(ym || ''));
  if (!mt) return null;
  const y = +mt[1], m = +mt[2];
  return y >= 2000 && m >= 1 && m <= 12 ? `${y}Q${Math.floor((m - 1) / 3) + 1}` : null;
};
const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
const monthTxt = (ym) => { const [y, m] = String(ym).split('-').map(Number); return MESES[m - 1] ? `${MESES[m - 1]} de ${y}` : String(ym); };
function serVal(ser, q) { const r = (ser || []).find((x) => x[0] === q); return r ? r[1] : null; }
function serGrowth(ser, q0) {
  if (!ser || !ser.length) return null;
  const first = ser[0][0], last = ser[ser.length - 1];
  if (q0 < first) return null;
  if (q0 >= last[0]) return { g: 0, from: q0, to: last[0], recent: true };
  const v0 = serVal(ser, q0);
  return v0 ? { g: last[1] / v0 - 1, from: q0, to: last[0], v0 } : null;
}
function imRead() {
  const f = $('#im-form'), num = (k) => { const v = parseFloat(String(f[k].value).replace(/\s/g, '').replace(',', '.')); return Number.isFinite(v) ? v : null; };
  const name = f.conc.value.trim().toLowerCase();
  const m = MUNIS.find((x) => x.name.toLowerCase() === name);
  return { conc: f.conc.value.trim(), dico: m ? m.dico : null, par: f.par.value || '', date: f.year.value && f.month.value ? `${f.year.value}-${f.month.value}` : '', price: num('price'), area: num('area'), kind: f.kind.value,
    loan: num('loan'), rate: num('rate'), years: num('years'), income: num('income'), rent: num('rent'),
    imi: num('imi'), condo: num('condo'), ins: num('ins'), vac: num('vac'), maint: num('maint'), tax: num('tax') };
}
function imSave(v) { try { localStorage.setItem(IM_KEY, JSON.stringify(v)); } catch { /* sem armazenamento */ } }
function imLoad() {
  let v = null;
  try { v = JSON.parse(localStorage.getItem(IM_KEY) || 'null'); } catch { v = null; }
  if (!v) return;
  const f = $('#im-form');
  ['conc', 'price', 'area', 'kind', 'loan', 'rate', 'years', 'income', 'rent', 'imi', 'condo', 'ins', 'vac', 'maint', 'tax']
    .forEach((k) => { if (v[k] != null && f[k]) f[k].value = v[k]; });
  // datas antigas guardadas noutro formato (ex.: "4" de um browser sem seletor de mês) são ignoradas
  if (qOfMonth(v.date)) { const [y, m] = v.date.split('-'); f.year.value = y; f.month.value = m; }
  imParishes(v.par);
}
let imParDico = null;
async function imParishes(sel) {
  const f = $('#im-form'), m = MUNIS.find((x) => x.name.toLowerCase() === f.conc.value.trim().toLowerCase());
  if (m && m.dico === imParDico && !sel) return;          // o mesmo concelho: mantém a freguesia escolhida
  imParDico = m ? m.dico : null;
  f.par.innerHTML = '<option value="">— (usar o concelho)</option>';
  if (!m) return;
  await ensurePar();
  const rows = PAR ? PAR.rows.filter((r) => r.dico === m.dico).sort((a, b) => String(a.name).localeCompare(String(b.name), 'pt')) : [];
  f.par.innerHTML += rows.map((r) => `<option value="${esc(r.code)}">${esc(r.name)}${r.price == null ? ' (sem preço publicado)' : ''}</option>`).join('');
  if (sel) f.par.value = sel;
}
async function imAnalyse() {
  const v = imRead(), out = $('#im-out');
  const err = [];
  if (!v.dico) err.push('escolhe um concelho da lista');
  if (!qOfMonth(v.date)) err.push('escolhe o mês e o ano da compra');
  else if (v.date > new Date().toISOString().slice(0, 7)) err.push('a data da compra não pode ser no futuro');
  if (!v.price || v.price <= 0) err.push('indica o preço pago');
  if (!v.area || v.area <= 0) err.push('indica a área em m²');
  if (err.length) { out.innerHTML = `<p class="banner">Falta: ${esc(err.join('; '))}.</p>`; return; }
  imSave(v);
  out.innerHTML = '<p class="muted">A calcular…</p>';
  await Promise.all([ensureSeries(), ensurePar(), ensureHist()]);
  const m = BY[v.dico], pr = v.par && PARBY[v.par] ? PARBY[v.par] : null;
  const q0 = qOfMonth(v.date), ppm = v.price / v.area;
  const kindKey = v.kind === 'apt' ? 'apt' : v.kind === 'house' ? 'house' : null;
  // índices disponíveis, por ordem de preferência
  const idx = [];
  if (kindKey && HIST.val[kindKey] && HIST.val[kindKey][v.dico]) idx.push(['type', `avaliação bancária de ${kindKey === 'apt' ? 'apartamentos' : 'moradias'} em ${m.name}`, HIST.val[kindKey][v.dico]]);
  if (HIST.val.all && HIST.val.all[v.dico]) idx.push(['all', `avaliação bancária (todas as casas) em ${m.name}`, HIST.val.all[v.dico]]);
  if (m.series && m.series.price && m.series.price.length) idx.push(['ine', `preço mediano de venda em ${m.name} (INE)`, m.series.price]);
  if (pr && HIST.parish[v.par]) idx.push(['par', `preço mediano de venda na freguesia ${pr.name} (INE)`, HIST.parish[v.par]]);
  if (NAT && NAT.series && NAT.series.hpi) idx.push(['nat', 'índice nacional de preços da habitação', NAT.series.hpi]);
  const res = idx.map(([k, label, ser]) => ({ k, label, ...(serGrowth(ser, q0) || {}) })).filter((r) => r.g != null);
  // o índice nacional só serve quando não há nenhum local que cubra a data da compra
  const local = res.filter((r) => r.k !== 'nat');
  const use = local.length ? local : res;
  const main = use.find((r) => r.k !== 'par') || use[0];
  const tiles = [], li = [];
  const tile = (label, val, ctx = '') => `<div class="stat"><span class="muted">${esc(label)}</span><b>${val}</b>${ctx ? `<span class="ctx">${ctx}</span>` : ''}</div>`;
  // 1) preço pago face ao mercado da altura
  const cmp = [];
  const at = (ser) => { if (!ser || !ser.length) return null; const last = ser[ser.length - 1]; return q0 > last[0] ? [last[1], last[0]] : (serVal(ser, q0) ? [serVal(ser, q0), q0] : null); };
  const addCmp = (label, ser) => { const r = at(ser); if (r) cmp.push([r[1] === q0 ? label : `${label} (último publicado, ${qpt(r[1])})`, r[0]]); };
  addCmp('mediana de venda do concelho', m.series.price);
  if (pr) addCmp(`mediana da freguesia ${pr.name}`, HIST.parish[v.par]);
  if (kindKey && HIST.val[kindKey]) addCmp(`avaliação bancária de ${kindKey === 'apt' ? 'apartamentos' : 'moradias'}`, HIST.val[kindKey][v.dico]);
  tiles.push(tile('Preço pago', `${fmt.eur(ppm)}/m²`, `${fmt.eur(v.price)} por ${fmt.n(v.area, v.area % 1 ? 1 : 0)} m², ${qpt(q0)}`));
  if (cmp.length) li.push(`Na altura da compra (${qpt(q0)}), pagaste ${cmp.map(([l, x]) => `${rel(ppm / x - 1)} da ${l} (${fmt.eur(x)}/m²)`).join('; ')}. Uma diferença grande pode ser só a casa (estado, área, vista, piso) e não um bom ou mau negócio.`);
  else li.push(`Não há medianas publicadas para ${m.name} em ${qpt(q0)} para comparar o preço pago (o INE só publica o preço por concelho desde 2019 e a avaliação bancária onde há avaliações suficientes).`);
  // 2) valor hoje
  if (main) {
    const val = v.price * (1 + main.g);
    const vals = use.map((r) => v.price * (1 + r.g));
    const lo = Math.min(...vals), hi = Math.max(...vals);
    // IHPC com média dos últimos 4 trimestres: o índice tem sazonalidade forte (saldos), comparar trimestres soltos distorce
    const H = HIST.hicp || [], avg4 = (q) => { const i = H.findIndex((x) => x[0] === q); return i >= 3 ? H.slice(i - 3, i + 1).reduce((a, x) => a + x[1], 0) / 4 : null; };
    const hl = H.length ? H[H.length - 1] : null, h0 = avg4(q0), h1 = hl ? avg4(hl[0]) : null;
    const infl = h0 && h1 && q0 <= hl[0] ? h1 / h0 - 1 : null;
    const multi = use.length > 1 && !main.recent;
    tiles.push(tile(main.recent ? 'Valor estimado' : `Valor estimado (${qpt(main.to)})`, fmt.eur(val), main.recent ? 'compra recente: ainda sem variação medida' : `${fmt.spct(main.g, 0)} desde a compra${multi ? ` · ${fmt.eur(lo)} a ${fmt.eur(hi)} conforme o índice` : ''}`));
    li.push(main.recent ? `A compra é tão recente como os últimos dados publicados (${qpt(main.to)}): ainda não há valorização medida, por isso o valor estimado é o preço pago.`
      : `Aplicando ao preço pago a variação da ${main.label} entre ${qpt(main.from)} e ${qpt(main.to)} (${fmt.spct(main.g, 0)}), o valor estimado é ${fmt.eur(val)}${multi ? `; com os outros índices locais fica entre ${fmt.eur(lo)} e ${fmt.eur(hi)} (${use.filter((r) => r !== main).map((r) => `${r.label}, até ${qpt(r.to)}: ${fmt.spct(r.g, 0)}`).join('; ')})` : ''}.${main.k === 'nat' ? ' Não há índice local que cubra a data da compra: usou-se o índice nacional, que pode estar longe do teu concelho.' : ''}${infl != null ? ` Descontada a inflação até ${qpt(hl[0])} (${fmt.spct(infl, 0)}), a valorização real é de ${fmt.spct((1 + main.g) / (1 + infl) - 1, 0)}${hl[0] < main.to ? ` (o índice de preços no consumidor publicado só vai até ${qpt(hl[0])}, por isso este valor real fica um pouco acima do verdadeiro)` : ''}.` : ''}`);
    const fcg = kindKey && m[`${kindKey}_fc_growth_12m`] != null ? [m[`${kindKey}_fc_growth_12m`], m[`${kindKey}_fc_lo80`], m[`${kindKey}_fc_hi80`], kindKey === 'apt' ? 'a avaliação bancária de apartamentos' : 'a avaliação bancária de moradias', m[kindKey === 'apt' ? 'val_apt' : 'val_house']]
      : m.fc_growth_12m != null ? [m.fc_growth_12m, m.fc_lo80, m.fc_hi80, 'o preço mediano de venda', m.nowcast_price ?? m.price] : null;
    if (fcg) {
      const [g, lo80, hi80, what, base] = fcg;
      tiles.push(tile('Previsão 12 meses (concelho)', fmt.spct(g), lo80 != null && base ? `80%: ${fmt.spct(lo80 / base - 1)} a ${fmt.spct(hi80 / base - 1)} · ${esc(what.replace(/^(a|o) /, ''))}` : esc(what)));
      li.push(`Para os próximos 12 meses, o modelo prevê ${fmt.spct(g)} para ${what} em ${m.name}${lo80 != null && base ? ` (intervalo de 80%: ${fmt.spct(lo80 / base - 1)} a ${fmt.spct(hi80 / base - 1)})` : ''} — é uma previsão para o concelho, não para a tua casa, e erra (ver "Perspetivas").`);
    }
    // 3) crédito e esforço
    const rate = v.rate != null ? v.rate : affRate();
    let pay = null;
    if (v.loan && v.loan > 0 && v.years) {
      pay = annuity(v.loan, rate, v.years);
      const payS = annuity(v.loan, rate + 2, v.years);
      tiles.push(tile('Prestação', `${fmt.eur(pay)}/mês`, `${fmt.n(rate, 2)}% · ${fmt.n(v.years, 0)} anos · com +2 p.p.: ${fmt.eur(payS)}`));
      if (v.income) {
        const e = pay / v.income, eS = payS / v.income;
        tiles.push(tile('Taxa de esforço', fmt.pct(e, 0), `do rendimento líquido · com +2 p.p.: ${fmt.pct(eS, 0)}`));
        li.push(`A prestação de ${fmt.eur(pay)}/mês leva ${fmt.pct(e, 0)} do rendimento líquido que indicaste${e > 0.5 ? ' — acima dos 50% que o Banco de Portugal usa como limite na concessão de crédito' : e > 0.35 ? ' — abaixo do limite de 50% do Banco de Portugal, mas pesada' : ''}. Com a taxa 2 p.p. acima, seriam ${fmt.eur(payS)} (${fmt.pct(eS, 0)}).${v.rate == null ? ` Taxa usada: a média atual dos novos créditos (${fmt.n(rate, 2)}%), porque não indicaste a tua.` : ''}`);
      }
      li.push(`Valor estimado face ao crédito em dívida: ${fmt.pct(v.loan / val, 0)} (quanto do valor da casa ainda é do banco).`);
    }
    // 4) arrendamento
    const rm2 = pr && pr.rent != null ? pr.rent : m.rent;
    if (rm2 != null) {
      const rentHome = rm2 * v.area, rLo = m.rent_q1 != null ? m.rent_q1 * v.area : null, rHi = m.rent_q3 != null ? m.rent_q3 * v.area : null;
      const rent = v.rent || rentHome;
      const months = 12 - (v.vac ?? 1);
      const gross = rent * months;
      const costs = (v.imi ?? v.price * 0.003) + (v.condo ?? (v.kind === 'house' ? 0 : 25)) * 12 + (v.ins ?? 150) + (v.maint ?? 5) / 100 * rent * 12;
      const taxR = (v.tax ?? 25) / 100, tax = Math.max(0, gross - costs) * taxR, net = gross - costs - tax;
      tiles.push(tile('Renda de mercado (estimada)', `${fmt.eur(rentHome)}/mês`, `${pr && pr.rent != null ? `freguesia ${esc(pr.name)}` : `concelho`}, novos contratos${rLo ? ` · 25%–75% do concelho: ${fmt.eur(rLo)}–${fmt.eur(rHi)}` : ''}`));
      tiles.push(tile('Rendibilidade', `${fmt.pct(gross / val, 1)} bruta`, `${fmt.pct(net / val, 1)} líquida de custos e IRS · ${fmt.pct(net / v.price, 1)} sobre o preço pago`));
      li.push(`${v.rent ? `A renda que indicaste (${fmt.eur(v.rent)}/mês) está ${rel(v.rent / rentHome - 1)} da renda mediana de novos contratos para ${fmt.n(v.area, v.area % 1 ? 1 : 0)} m² (${fmt.eur(rentHome)}).` : `Arrendada, a casa renderia cerca de ${fmt.eur(rentHome)}/mês (renda mediana de novos contratos${pr && pr.rent != null ? ' da freguesia' : ' do concelho'} × área${rLo ? `; no concelho, 25% dos novos contratos ficam abaixo de ${fmt.eur(rLo)} e 25% acima de ${fmt.eur(rHi)} para esta área` : ''}).`} Com ${fmt.n(v.vac ?? 1, 0)} ${(v.vac ?? 1) === 1 ? 'mês' : 'meses'} vazio por ano, custos de ${fmt.eur(costs)}/ano (IMI, condomínio, seguro, manutenção) e IRS de ${fmt.n(v.tax ?? 25, 0)}% sobre o rendimento depois de custos, ficam ${fmt.eur(net)}/ano líquidos (${fmt.pct(net / val, 1)} do valor estimado).${pay ? ` Face à prestação, o saldo mensal seria de ${net / 12 - pay < 0 ? '−' : '+'}${fmt.eur(Math.abs(net / 12 - pay))} (${net / 12 - pay >= 0 ? 'a renda paga a prestação' : 'a renda não chega para a prestação'}).` : ''} A taxa do IRS sobre rendas depende do contrato e das opções fiscais: confirma com as Finanças ou um contabilista.`);
      const be = (rate / 100 + 0.013) - (rentHome * 12) / val;
      li.push(`Comprar vs arrendar hoje, para esta casa: com juros de ${fmt.n(rate, 2)}% e ~1,3%/ano de IMI e manutenção, ser dono só sai mais barato do que arrendar a mesma casa se ela valorizar mais de ${fmt.spct(be)}/ano.`);
    } else li.push(`Não há renda publicada para ${m.name}: sem estimativa de arrendamento.`);
  } else li.push(`Não há índices de preços para ${m.name} que cubram ${qpt(q0)}: sem estimativa de valor.`);
  const inputs = [`${esc(m.name)}${pr ? `, ${esc(pr.name)}` : ''}`, `compra em ${esc(monthTxt(v.date))}`, `${fmt.eur(v.price)}`, `${fmt.n(v.area, v.area % 1 ? 1 : 0)} m²`,
    v.kind === 'apt' ? 'apartamento' : v.kind === 'house' ? 'moradia' : null].filter(Boolean).join(' · ');
  out.innerHTML = `<p class="muted">Dados: ${inputs}. Calculado em ${new Date().toISOString().slice(0, 10)} com os dados do painel de ${META.built_at.slice(0, 10)}.</p>
    <div class="stats">${tiles.join('')}</div>
    <ul class="read">${li.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>
    <div class="disclaimer">${IM_DISCLAIMER}</div>
    <p class="noprint"><button type="button" class="btn" id="im-print">Imprimir análise</button></p>`;
}
const IM_DISCLAIMER = '⚠ <b>Estimativa estatística, não vinculativa.</b> Isto não é uma avaliação imobiliária nem aconselhamento financeiro, fiscal ou jurídico. Os números aplicam medianas e índices oficiais (INE, BCE, Eurostat) ao preço que indicaste: não conhecem o estado, a localização exata, a vista, o piso, as obras nem o mercado da tua rua, que podem afastar o valor real muito destes valores. Para decisões (vender, pedir ou renegociar crédito, partilhas, impostos) consulta um perito avaliador registado na CMVM, o teu banco ou um contabilista. Os dados que introduzes ficam só neste browser: nada é enviado.';
function initImovel() {
  $('#im-disclaimer').innerHTML = IM_DISCLAIMER;
  $('#im-conc').innerHTML = MUNIS.map((m) => `<option value="${esc(m.name)}"></option>`).join('');
  const f = $('#im-form');
  const yNow = new Date().getFullYear();
  f.year.innerHTML = '<option value="">ano</option>' + Array.from({ length: yNow - 2007 }, (_, i) => yNow - i).map((y) => `<option>${y}</option>`).join('');
  f.month.innerHTML = '<option value="">mês</option>' + MESES.map((n, i) => `<option value="${String(i + 1).padStart(2, '0')}">${n}</option>`).join('');
  f.conc.addEventListener('change', () => imParishes(''));
  f.addEventListener('submit', (e) => { e.preventDefault(); imAnalyse().catch((x) => { console.error(x); $('#im-out').innerHTML = '<p class="banner">Não foi possível calcular a análise.</p>'; }); });
  $('#im-clear').addEventListener('click', () => { f.reset(); $('#im-out').innerHTML = ''; try { localStorage.removeItem(IM_KEY); } catch { /* */ } imParishes(''); });
  $('#im-out').addEventListener('click', (e) => {
    if (e.target.id === 'im-print') { document.body.classList.add('print-imovel'); window.print(); setTimeout(() => document.body.classList.remove('print-imovel'), 500); }
  });
  imLoad();
}
function renderSummary() {
  const t = [], n = NAT && NAT.series && NAT.series.hpi_real;
  if (n && n.length > 4) {
    const a = n[n.length - 1], b = n[n.length - 5];
    t.push(['Preço real (país)', fmt.spct(a[1] / b[1] - 1), `num ano até ${qpt(a[0])}, já sem inflação`, '#national']);
  }
  const A = OL && OL.afford_hist;
  if (A && A.last) t.push(['Esforço de compra', fmt.pct(A.last.effort_wage ?? A.last.effort_irs, 0), `90 m² no país, do ${A.last.effort_wage != null ? 'salário médio' : 'rendimento IRS'} (${qpt(A.last.period)})`, '#outlook']);
  if (OL && OL.credit) t.push(['Crédito novo', `${fmt.n(OL.credit.last12 / 1000, 1)} mil M€`, `12 meses até ${OL.credit.until}${OL.credit.change != null ? `, ${fmt.spct(OL.credit.change, 0)}` : ''}`, '#outlook']);
  if (OL && OL.cycle) { const c = OL.cycle; t.push(['Fim de ciclo?', `${c.counts.up_down} de ${c.n}`, 'concelhos com preço a subir e compras a cair', '#outlook']); }
  if (OL && OL.sales) t.push(['Previsão 12 meses', fmt.spct(OL.sales.median_growth_12m), `concelho típico, até ${qpt(OL.sales.target_period)}`, '#outlook']);
  if (OL && OL.europe) t.push(['Portugal na UE', `${OL.europe.rank}.º de ${OL.europe.n}`, `subida real desde 2015 (${fmt.spct(OL.europe.pt.real_2015, 0)})`, '#outlook']);
  if (!t.length) return;
  $('#summary').hidden = false;
  $('#summary-tiles').innerHTML = t.map(([l, v, c, h]) => `<a class="stat sum-tile" href="${h}"><span class="muted">${esc(l)}</span><b>${esc(v)}</b><span class="ctx">${esc(c)}</span></a>`).join('');
}
function renderSources() {
  const S = META.sources || {}, ine = S.ine || {}, mac = S.macro || {}, sum = META.ine_summary;
  const ent = (o) => Object.entries(o).filter(([k]) => k !== 'geo');
  const all = [...ent(ine).map(([k, v]) => ['INE', k, String(v)]), ...ent(mac).map(([k, v]) => ['BCE/Eurostat/BIS', k, String(v)]),
    ...(ine.geo ? [['Fronteiras', 'concelhos', String(ine.geo)]] : [])].filter((r) => !r[2].startsWith('sem código'));
  if (!all.length) { $('#sources').hidden = true; return; }
  const bad = all.filter((r) => /^(CACHE|ERRO|AVISO)/.test(r[2]));
  const cache = bad.filter((r) => r[0] === 'INE' && r[2].startsWith('CACHE'));
  const day = META.built_at.slice(0, 10);
  let head;
  if (cache.length) head = `⚠ O INE não respondeu neste build (${day}): ${cache.length} ${cache.length === 1 ? 'indicador usa' : 'indicadores usam'} os dados do último build que chegou ao INE${sum && sum.last_live ? ` (${sum.last_live})` : ''}. Nova tentativa automática mais tarde.`;
  else if (bad.length) head = `Fontes atualizadas em ${day}; ${bad.length} ${bad.length === 1 ? 'indicador opcional' : 'indicadores opcionais'} com erro (fora do painel).`;
  else head = `✓ Todas as fontes atualizadas em ${day}.`;
  $('#sources').hidden = false;
  $('#sources').classList.toggle('warn', cache.length > 0);
  $('#sources-sum').innerHTML = `${esc(head)} ${info('sources')}`;
  const ok = all.length - bad.length;
  $('#sources-body').innerHTML = `<p class="muted">${ok} de ${all.length} fontes descarregadas neste build.</p>` + (bad.length
    ? `<div class="table-wrap"><table class="ol-table"><thead><tr><th>Fonte</th><th>Indicador</th><th>Estado</th></tr></thead><tbody>${bad.map((r) =>
      `<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td><td style="text-align:left">${esc(r[2].slice(0, 140))}</td></tr>`).join('')}</tbody></table></div>` : '');
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
  // em paralelo; séries por concelho e freguesias só são descarregadas quando são precisas (ver ensureSeries/ensurePar)
  const opt = (path) => j(path).catch(() => null);
  [GEO, BT, OL] = await Promise.all([opt('data/concelhos.geojson'), opt('data/backtest.json'), opt('data/outlook.json')]);
  CH = OL && OL.changes ? OL.changes : null;
  MUNIS.forEach((m) => (BY[m.dico] = m));
  $('#stamp').textContent = `Atualizado ${META.built_at.slice(0, 10)} · último período de preços: ${META.latest_price_period} · ${META.n_municipalities} concelhos`;
  $('#demo-banner').hidden = !META.demo;
  $('#disclaimer').textContent = META.disclaimer;
  try { renderSources(); } catch (e) { console.error('fontes:', e); }
  $('#metric').addEventListener('change', updateMetric);
  $('#metric-f').addEventListener('change', updateMetric);
  $('#lvlnav').addEventListener('click', (e) => { const b = e.target.closest('[data-lvl]'); if (b) setLevel(b.dataset.lvl); });
  $('#par-list').addEventListener('click', (e) => { const a = e.target.closest('a[data-d]'); if (a) { e.preventDefault(); select(a.dataset.d); } });
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
  safe('resumo', renderSummary);
  safe('o meu imóvel', initImovel);
  safe('comprar casa', initAfford);
  // indicadores do mapa sem nenhum valor nesta build (ex.: fonte que falhou) não aparecem na lista
  safe('métricas vazias', () => {
    [...$('#metric').options].forEach((o) => {
      const g = METRIC_VAL[o.value];
      if (g && !MUNIS.some((m) => g(m) != null)) o.remove();
    });
  });
  safe('seguidos', renderFollow);
  $('#d-follow').addEventListener('click', () => selected && toggleFollow(selected));
  $('#d-print').addEventListener('click', () => window.print());
  window.addEventListener('beforeprint', () => { document.body.classList.add('printing'); Object.values(charts).forEach((c) => c.resize()); });
  window.addEventListener('afterprint', () => { document.body.classList.remove('printing'); Object.values(charts).forEach((c) => c.resize()); });
  $('#follow-body').addEventListener('click', (e) => {
    const u = e.target.closest('[data-unfollow]'); if (u) { toggleFollow(u.dataset.unfollow); return; }
    const a = e.target.closest('a[data-d]'); if (a) { e.preventDefault(); select(a.dataset.d); }
  });
  safe('ranking', () => { renderTable(); renderRankingSummary(); });
  safe('backtest', renderBacktest);
  safe('perspetivas', renderOutlook);
  safe('o que mudou', renderChanges);
  $('#changes-body').addEventListener('click', (e) => { const a = e.target.closest('a[data-d]'); if (a) { e.preventDefault(); select(a.dataset.d); } });
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
  // as séries por concelho descarregam-se em segundo plano, depois de o resto aparecer
  setTimeout(ensureSeries, 1200);
}
main();
})();
