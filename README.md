# Painel de Risco Imobiliário — Portugal

Pipeline Python (INE, BCE, Eurostat, BIS → Parquet/DuckDB → scores) + site estático (mapa por concelho, séries, ranking, comparador). Sem backend: corre no GitHub Actions e publica no GitHub Pages.

## Estado atual (v0.1)

| Fase | Estado |
|---|---|
| 1. MVP concelho: preços, rendas, yield, score de valorização, mapa, séries | Implementado |
| 2. Macro: Euribor 12M, HPI (Eurostat), desvio crédito/PIB (BIS), score nacional | Implementado |
| 3a. Licenças/fogos concluídos por concelho | Ligado ao pipeline; **falta preencher os `varcd`** em `config/sources.yml` |
| 3b. Censos 2021 / RNAL por freguesia | Não implementado |
| 3c. Anúncios (opcional, desligado) | Esqueleto com robots.txt + API oficial Idealista (`listings.py`) |
| 3d. Rendimento por concelho (preço/rendimento) | Implementado (`varcd 0012653`, INE/MTSSS, `dim_3=T` confirmado) |
| 3e. Contexto demográfico (densidade, envelhecimento, saldo migratório) | Ligado ao pipeline (`varcd`s 0013189/0012909/0013179); `dims` não confirmado ao vivo, mas os títulos do catálogo do INE não sugerem dimensão extra além da geográfica |
| 4. Backtest do score nacional | Implementado, multi-país (ver secção "Backtest do score nacional" abaixo). Cenários/alertas: não implementado. |
| 5. Perspetivas: previsões e padrões | Implementado (ver secção "Perspetivas" abaixo): nowcast e previsão do preço de venda por concelho, renda a 1 ano, regimes, tipologias, propagação, valor justo, cenários de juros. Corre no build semanal; não altera nenhum score. |

## O que NÃO foi verificado

- As chamadas reais ao INE/BCE/Eurostat/BIS **não puderam ser testadas** no ambiente onde isto foi escrito (sem acesso de rede a essas fontes). O parser foi testado com respostas simuladas e o site com dados sintéticos (`--demo`).
- Os códigos INE em `config/sources.yml` vêm de projetos públicos; o `dims` de cada indicador (quartis, categorias) pode precisar de ajuste. Se houver ambiguidade, o pipeline **falha alto** com as opções disponíveis, em vez de misturar categorias.
- O URL do BIS e a ligação das geometrias (DICO vs nome) são os pontos mais prováveis de precisar de ajuste. Os erros aparecem em `site/data/meta.json` (`sources`, `geo_unmatched`).

## Primeiros passos

```bash
pip install -e ".[dev]"
pytest -q

python -m imopt build --demo          # dados SINTÉTICOS, offline
python -m http.server -d site 8000    # http://localhost:8000

python -m imopt inspect 0012234       # ver dimensões reais de um indicador INE
python -m imopt build                 # dados reais

python -m imopt backtest --demo       # backtest com dados SINTÉTICOS, offline
python -m imopt backtest              # backtest real (Eurostat, BIS; ver secção abaixo)
```

## Publicar no GitHub

1. Cria o repositório e faz push para `main`.
2. Settings → Pages → Source: **GitHub Actions**.
3. Actions → `build-and-deploy` → Run workflow. Depois corre à segunda de manhã.
4. Snapshots (Parquet) ficam no branch `data`, para não inchar o `main`.

**Primeira execução:** vê o log e o `meta.json` publicado; se algum indicador vier com `ERRO`, ajusta `config/sources.yml`.

## Se o INE não responde ao GitHub (timeouts de ligação)

O INE pode não aceitar ligações dos runners do GitHub. O workflow corre com `IMOPT_INE_MODE=auto`: tenta o INE uma vez e, se falhar, usa o snapshot mais recente entre `data/clean` de `main` (commit manual) e `data/clean` do branch `data` (último run que alterou dados), marcado como `CACHE` no `meta.json`. Para alimentar essa cache, corre o build **no teu computador** (IP normal) e faz commit dos dados limpos:

```bash
python -m imopt build
git add data/clean && git commit -m "Atualiza dados INE" && git push
```

Modos: `IMOPT_INE_MODE=live` (defeito, 5 tentativas), `auto` (1 tentativa, depois cache), `cache` (nunca usa a rede).
Alternativa: um runner self-hosted (por exemplo no Raspberry Pi) executa o mesmo workflow a partir de um IP residencial.

## Dados e IA

- `data/raw/` snapshots imutáveis com data; `data/clean/` tabelas limpas em Parquet.
- Consulta com DuckDB: `duckdb -c "SELECT * FROM 'data/clean/ine_sales_price_12m.parquet' LIMIT 5"`.
- Um MCP com DuckDB sobre `data/clean/` permite ao Claude analisar os dados localmente.

## Método (resumo)

- **Score municipal (0–100)**: percentis *entre concelhos* de crescimento a 12m e 3 anos e de rendibilidade bruta baixa. É **relativo**: diz quem está mais esticado, não quando corrige.
- **Dados voláteis (⚠)**: concelhos no decil mais volátil de variações trimestrais do preço (poucas transações) têm o score atenuado a meio caminho do neutro (50).
- **Score nacional**: z-scores históricos do crescimento do HPI, desvio face à tendência, variação da Euribor e desvio crédito/PIB, convertidos por função logística.
- **HPI real**: HPI nominal ÷ IHPC (Eurostat, base 2015), recentrado a 2015 = 100; termina no último trimestre completo com IHPC. Só é usado para leitura, não entra no score.
- **Score municipal**: continua sem validação por backtest. **Score nacional**: tem agora um backtest multi-país (ver secção seguinte) — os pesos e a lógica em produção não foram alterados por causa dele. Nada disto é aconselhamento financeiro.
- **Previsões** (secção "Perspetivas"): modelo linear regularizado comum a todos os concelhos, validado sem look-ahead contra regras ingénuas; intervalos calibrados no backtest. Só leitura.

## Backtest do score nacional

O score nacional nunca tinha sido validado: sabíamos que subia em alturas "quentes" e descia
em alturas "calmas", mas não se isso acontecia a tempo de servir de aviso. `imopt/backtest.py`
testa isso correndo o mesmo cálculo (`scoring.national_scores`, sem alterações) trimestre a
trimestre, só com os dados que existiam nessa altura, em vários países — Portugal sozinho só
tem um episódio de queda independente (2008–2013), amostra pequena demais para tirar conclusões.

### Método (regras fixadas antes de ver os resultados)

- **Países**: 8 com boom-bust conhecido (Portugal, Espanha, Irlanda, Grécia, Chipre, Estónia,
  Letónia, Lituânia) + 5 de controlo sem crise grande (Alemanha, Áustria, Bélgica, França,
  Polónia). A Polónia nunca adotou o euro — serve de caso onde a componente da Euribor é
  sempre excluída.
- **Dados**: HPI e IHPC do Eurostat (`prc_hpi_q`, `prc_hicp_midx`, uma chamada por país) e
  desvio crédito/PIB do BIS (`WS_CREDIT_GAP`). A Euribor (BCE) é uma série única, partilhada
  por todos os países do euro, e só entra no score de um país a partir do ano em que adotou o
  euro; antes disso (ou para países fora da área do euro) a componente de juros é omitida —
  não é um sinal desses países nesses períodos.
- **Sem look-ahead**: para cada trimestre `t`, o score usa só dados até `t` (janela expansiva,
  mínimo de 40 trimestres de histórico, também testado com 32 e 60). Como `national_scores` já
  só olha para o último ponto das séries que recebe, isto foi feito truncando as séries antes
  de a chamar — sem duplicar nem alterar a lógica de scoring.py (ver
  `test_backtest.py::test_no_lookahead_*`).
- **Alvos**: variação nominal e real do HPI a 4, 8 e 12 trimestres; evento binário de queda
  real ≥10% nos 12 trimestres seguintes.
- **Métricas**: correlação de Spearman entre o score e o retorno futuro; AUC do score para o
  evento de queda; taxa de acerto e de falso alarme com o limiar 70 do painel (e outros: 50,
  60, 80). Sempre comparado com duas regras simples («baselines»): só o crescimento anual do
  HPI, só o desvio crédito/PIB — extraídas das mesmas chamadas ao score, para serem
  diretamente comparáveis. Avaliado por país e agregado ("pooled"), com leave-one-out por país
  e sensibilidade ao histórico mínimo.

### Limites (ler antes de confiar nos números)

- HPI e IHPC são séries **revistas** pelo Eurostat — não temos os valores tal como publicados
  na altura, o que favorece ligeiramente os resultados face a um uso em tempo real.
- Os episódios **não são independentes**: a crise financeira global de 2008 atinge vários
  países ao mesmo tempo, por isso as métricas agregadas valem menos do que o número de países
  sugere.
- Poucos episódios de queda grande no total: risco de ajuste excessivo, mesmo com as regras
  fixadas antes de ver os resultados.
- O desvio crédito/PIB tende a ser mais informativo em países com grande alavancagem bancária
  (Irlanda, Chipre) do que noutros.
- Um resultado fraco ou negativo é reportado tal como é — ver a secção "Backtest" no site
  (score vs. HPI real por país, tabela de métricas com baselines, veredicto em linguagem
  simples) depois de correr `python -m imopt build` (ou `--demo`).

### Como correr

```bash
python -m imopt backtest --demo                       # sintético, offline, todos os países
python -m imopt backtest                               # real, todos os países (ver config em imopt/backtest.py)
python -m imopt backtest --countries PT,ES,IE --out x.json
```

Escreve `site/data/backtest.json` (séries de score e HPI real por país, métricas, parâmetros e
data de geração), lido pelo site na secção "Backtest do score nacional". Os dados intermédios
ficam em cache em `data/clean/backtest_*.parquet`, no mesmo estilo dos outros indicadores: se o
Eurostat/BIS falhar para um país, usa o último snapshot em cache e só esse país fica marcado
como tal (falha não-fatal, como o resto do pipeline macro).

**Decisão: comando separado, não faz parte do build semanal automático.** Um backtest completo
faz dezenas de pedidos extra ao Eurostat/BIS (HPI, IHPC e crédito/PIB × 13 países); correr isso
todas as semanas tornaria o workflow mais lento e mais frágil sem benefício — os dados
históricos de que depende mudam pouco de semana para semana. Em vez disso, o
`.github/workflows/build.yml` ganhou uma entrada manual opcional
(`workflow_dispatch` → "Também correr o backtest"): só quando alguém a liga é que o passo
`python -m imopt backtest` corre, sempre com `continue-on-error` (não bloqueia o deploy do
resto do site). As execuções automáticas (agendada e por push) não correm o backtest.

**`site/data/` nunca é commitado — cada deploy parte do zero.** Para a secção "Backtest" não
desaparecer do site sempre que houver um deploy normal (ex.: um push a `main` sem pedir o
backtest), o `backtest.json` gerado é também copiado para `data/clean/backtest.json`, que entra
no mesmo snapshot do branch `data` que os outros indicadores (`data/clean/*.parquet`). Todo
deploy — mesmo sem a flag `backtest` — restaura essa cópia para `site/data/backtest.json` antes
de publicar, servindo o **último resultado real conhecido** até alguém voltar a ligar a flag e
gerar um novo. Antes da primeira vez que alguém corre o backtest, não há cache: a secção mostra
"ainda não gerado" (não é um erro).

## Perspetivas: previsões e padrões

Código em `imopt/forecast.py` (previsões) e `imopt/outlook.py` (padrões e orquestração). Corre dentro
do `python -m imopt build` (uns 10 s, sem pedidos extra à rede: usa o que o pipeline já descarrega,
incluindo a avaliação bancária mensal `0012248`, que antes não era usada no site). Escreve
`site/data/outlook.json` e acrescenta campos por concelho a `municipalities.json` (`fc`,
`nowcast_price`, `fc_growth_12m`, `rent_fc`, `fv_gap`, `typology_name`, …). Cada parte é não-fatal.
Não usa bibliotecas novas (numpy/pandas/shapely).

### Preço de venda: estimativa para hoje ("nowcast") e 12 meses

- **Alvo**: o preço mediano de venda do INE por concelho (mediana móvel de 12 meses, trimestral,
  desde 2019T4), h = 1…6 trimestres depois do último publicado. Com dados até 2026T1 e hoje em
  2026T3, h = 1–2 são estimativas do presente e h = 6 é "daqui a 12 meses".
- **Modelo**: previsão direta por horizonte; ridge com mínimos quadrados ponderados pela volatilidade
  de cada concelho, comum a todos ("pooled"). Sinais: inércia (último trimestre e último ano),
  avaliação bancária do concelho e do país desde o fim da janela das vendas (sai ~5 meses antes do
  preço de venda — é o que dá o nowcast), média dos concelhos vizinhos, nível face à mediana,
  variação da Euribor. Nenhuma variável é extrapolada para fora do intervalo visto no treino.
- **Intervalos**: o erro é separado em choque comum a todos os concelhos (a "surpresa nacional"
  de cada trimestre) e erro próprio de cada concelho; os dois combinados dão as faixas de 50% e 80%,
  calibradas com as 8 origens mais recentes do backtest.
- **Backtest sem look-ahead**: para cada trimestre de origem, treino só com pares cujo alvo já era
  conhecido, avaliação bancária cortada com o mesmo avanço que existe hoje
  (`test_forecast.py::test_sales_backtest_has_no_lookahead`). Comparado com «fica igual» e
  «continua o ritmo do último ano».

Resultados com os dados em cache (vendas até 2026T1, avaliação bancária até 2026-08, 302 concelhos):

| h | Origens | Erro médio modelo (p.p.) | «Fica igual» | «Continua o ritmo» | Concelho típico (modelo / ingénua) | Menos erro | Cobertura 80% |
|---|---|---|---|---|---|---|---|
| 1 | 2021T2–2025T4 (19) | 4,6 | 5,5 | 5,8 | 2,6 / 3,8 | 16% | 83% |
| 2 (hoje) | 2021T3–2025T3 (17) | 6,6 | 8,9 | 9,7 | 4,2 / 7,0 | 26% | 83% |
| 4 | 2022T1–2025T1 (13) | 10,2 | 14,9 | 17,4 | 7,1 / 12,7 | 32% | 82% |
| 6 (12 meses) | 2022T3–2024T3 (9) | 12,0 | 19,1 | 22,5 | 9,2 / 17,0 | 37% | 75% |

Previsão mediana entre concelhos para os próximos 12 meses: +12% (metade entre +9% e +14%).

### Indicadores de contexto e previsões por tipo de casa

Todos opcionais (falham de forma não-fatal) e só leitura — nenhum entra nos scores.

| Indicador | Fonte | Uso |
|---|---|---|
| Preço de casas novas vs existentes | INE 0012234, `dim_3` H11/H12 (confirmado no snapshot bruto: 186/305 concelhos) | Detalhe, comparação, "prémio" das novas |
| Avaliação bancária de apartamentos vs moradias | INE 0012248, `dim_3` 1/2 (116/152 concelhos) | Detalhe e **previsão a 12 meses por tipo** (mesmo motor das vendas, 15 anos de histórico mensal: backtest de 30–40 origens desde 2015, 19% menos erro nos apartamentos e 37% nas moradias que a melhor regra ingénua, cobertura de 80% em 78%) |
| 1.º e 3.º quartil da renda | INE 0014711, `dim_3` 1/3 (255 concelhos) | Renda "barata" e dispersão do concelho |
| Novos contratos de arrendamento (N.º) | INE 0012601 | Tamanho do mercado de arrendamento |
| Dormidas em alojamento turístico | INE 0009183 | Pressão turística por habitante; entra no **valor justo** |
| Crédito à habitação por habitante | INE 0013048 | Contexto (não entra no valor justo: acompanha os preços) |
| Taxa dos novos créditos à habitação em PT | BCE MIR `M.PT.B.A2C.A.R.A.2250.EUR.N` | Spread real nos cenários de juros (em vez de 1 p.p. assumido) |

Os códigos do INE vêm do catálogo do INE; para 0012601, 0009183 e 0013048 as dimensões não foram
confirmadas ao vivo, e a chave do BCE também não (se não existir ou devolver valores fora do
plausível, os cenários usam o spread de 1 p.p.). O pedido ao INE é feito uma só vez por indicador,
mesmo quando é usado com várias categorias.

**Não incluídos por falta de código confirmado**: número de vendas por concelho (o 0012786 do
catálogo é em € e só por NUTS II), preço por domicílio fiscal do comprador e Censos 2021 (casas
vagas/segunda habitação). Quando houver um código confirmado com `imopt inspect`, entram como os
de cima.

### Arquivo de previsões e avaliação contra a realidade

`imopt/tracking.py`. Cada build real (não o demo) guarda as previsões publicadas em
`data/clean/forecast_log.parquet`: preço central, intervalos de 50%/80% e o último valor publicado
na altura, por concelho e horizonte, mais a renda prevista. Só uma vez por conjunto de dados novo
(último trimestre de vendas + último mês de avaliação bancária): builds semanais sem dados novos
não criam duplicados. O ficheiro vive no branch `data` (o workflow repõe-no sempre a partir de lá,
e está no `.gitignore` para não ir parar a `main` por um build local).

Quando o INE publica um trimestre (ou ano de rendas) que tinha sido previsto, o build mede o erro,
se o valor caiu nos intervalos e o erro de «fica igual», por horizonte. Aparece em "Perspetivas" →
"Previsões anteriores vs realidade" e, por concelho, como pontos no leque da previsão. Ao contrário
do backtest, usa os dados tal como saíram — é a avaliação mais honesta, mas demora: o primeiro
trimestre avaliável é 2026T2 (quando o INE o publicar) e a 12 meses só há resultados um ano depois
do arranque. Com poucos conjuntos de dados, o site avisa que a amostra é pequena.

### Rendas a 1 ano

Mesma abordagem, anual: inércia da renda, variação do preço de venda, rendibilidade face à mediana,
avaliação bancária recente. Só há 6 anos por concelho (2020–2025): backtest com 3 origens
(2022–2024), erro médio 5,8 p.p. contra 8,1 p.p. de «continua o ritmo» (28% menos), cobertura de
80% em 92% dos casos (intervalos conservadores). Confiança baixa — está escrito no site.

### Padrões

- **Regimes** (HPI nacional, regressão por troços, BIC): −6,3%/ano em 2010T2–2012T4, +3,6% em
  2013–2015, +9,5% em 2016–2021, +8,5% em 2022–2023 (+2,6% real) e +17,3%/ano desde 2024T1
  (+14,4% real).
- **Tipologias** (k-means; k = 4 pela silhueta, 0,38): «mais caros, subida a acelerar» (152),
  «mais baratos, arranque tardio» (43: parados até 2022T2, a subir depois), «mais baratos, subida
  estável e fraca» (72), «mais baratos, boom até 2022T2, agora a abrandar» (19).
- **Propagação**: não se deteta atraso mensal face a Lisboa/Porto (desfasamento ótimo de 0–1
  meses em todas as faixas); a ligação enfraquece com a distância e a subida é mais forte perto das
  metrópoles.
- **Valor justo**: os fundamentos explicam 84% das diferenças de preço entre concelhos (validação
  cruzada). +10% de rendimento → +5,0% no preço; litoral → +41%; +10% de envelhecimento → −4,5%.
- **Juros**: +1 p.p. na Euribor sobe a prestação ~12,5% e reduz ~11% o que se pode pedir com a
  mesma prestação (aritmética, crédito a 30 anos, Euribor + 1 p.p.). O efeito histórico nos preços
  (−1,6% por p.p.) não é estatisticamente claro (intervalo de 90% inclui zero), por isso não é
  usado como cenário.

### O que mudou depois de ver os resultados (transparência)

- **Sem extrapolação**: a primeira versão tinha, em 2022, erros comuns de −30% a −43% a 12 meses —
  modelos treinados só com 2020–21 (Euribor parada) extrapolavam o salto de +3 p.p. dos juros. A
  correção (limitar cada variável ao intervalo visto no treino) é uma regra geral, não uma afinação;
  foi ela que tornou o modelo melhor do que «fica igual» a 12 meses.
- **Intervalos**: a primeira versão tratava os erros dos concelhos como independentes e dava
  cobertura de 17–68% nos horizontes longos; agora inclui o choque comum e usa só as 8 origens
  mais recentes para calibrar.
- **Litoral**: sem esta variável, a lista de "mais caros do que os fundamentos" era dominada pela
  costa. Derivada da geometria (fronteira sem concelho vizinho do lado do mar); falha alguns casos
  (ex.: a costa de Alcácer do Sal não aparece nas fronteiras simplificadas).
- **Tipologias**: a proposta inicial era agrupar trajetórias de 15 anos da avaliação bancária, mas
  só ~56 concelhos têm dados desde 2011. Usa-se a série de vendas (286 concelhos); a história longa
  aparece como contexto quando existe.

### Limites

Os mesmos que aparecem no site (`outlook.LIMITS`): pontos de viragem são difíceis de prever; o preço
do INE é uma mediana móvel (parte da inércia é mecânica); a avaliação bancária não é preço de
transação; o backtest cobre poucos anos e um só ciclo de juros; séries revistas (não temos os valores
tal como publicados na altura); valor justo não é prova de bolha.

## Anúncios (opcional)

Idealista e Imovirtual proíbem scraping nos termos de uso. Por isso `listings.enabled` está a `false`; o módulo respeita `robots.txt`, limita o ritmo e para perante 401/403/429. Para o Idealista, usa a API oficial.
