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
python -m imopt search vendas domicilio                   # procura no catálogo de indicadores principais
python -m imopt search vendas --range 0012220-0012260     # varre códigos (um pedido por código)
python -m imopt search vagos --file catalogo.xml          # procura num catálogo XML já descarregado
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
| Preço pago por compradores com domicílio no estrangeiro vs em Portugal | INE 0012246, `dim_3` 2/1 (confirmado com `imopt inspect`) | Prémio pago por estrangeiros: detalhe, mapa, lista em "Perspetivas" |
| Preço pago por famílias vs empresas e outras entidades | INE 0012236, `dim_3` S1400000/S3000000 (confirmado) | Prémio pago por empresas: detalhe, comparação, lista em "Perspetivas" |
| Preço por tipologia (T0/T1, T2, T3, T4+) e de apartamentos | INE 0012241 `dim_3` 1–4 e 0012235 (confirmados) | Detalhe e comparação |
| Avaliações bancárias (N.º, últimos 3 meses) | INE 0012247, `dim_3` T, 1 e 2 — total, apartamentos e moradias (confirmado) | Volume de compras com crédito — substituto do número de vendas, que o INE não publica por concelho; o volume costuma cair antes dos preços |
| Taxa dos novos créditos à habitação em PT | BCE MIR `M.PT.B.A2C.A.R.A.2250.EUR.N` | Spread real nos cenários de juros (em vez de 1 p.p. assumido) |

Os códigos do INE vêm do catálogo do INE; para 0012601, 0009183 e 0013048 as dimensões não foram
confirmadas ao vivo, e a chave do BCE também não (se não existir ou devolver valores fora do
plausível, os cenários usam o spread de 1 p.p.). O pedido ao INE é feito uma só vez por indicador,
mesmo quando é usado com várias categorias.

**Não incluídos**: número de vendas por concelho (o 0012786 é em € e só por NUTS II; usa-se o
número de avaliações bancárias em vez disso) e Censos 2021 (casas vagas/segunda habitação, sem
código encontrado). Quando houver um código confirmado com `imopt inspect`, entram como os
de cima. Para os procurar: `python -m imopt search …` (ver "Primeiros passos"). O catálogo
descarregável do INE (`opc=3`) só tem os ~260 indicadores principais — estes três não estão lá; o
`--range` consulta a ficha de cada código, e indicadores da mesma operação estatística costumam ter
códigos próximos (os preços locais da habitação andam pelos 0012230–0012260; as rendas da
Metodologia 2026 pelos 0014700).

### Preços reais, o que mudou e volume nas previsões

- **Preços reais**: variação a 12 meses, 3 e 5 anos descontada a inflação (IHPC do Eurostat, último
  trimestre publicado — sai depois do preço da habitação) e, no gráfico de cada concelho, o preço em €
  do último trimestre com IHPC. Também no mapa ("Variação 12 meses descontada a inflação").
- **O que mudou** (`imopt/changes.py`): trimestre mais recente vs anterior — variação do preço e do score,
  mudanças de faixa de risco. O score anterior é recalculado com o mesmo método e os dados cortados
  nesse trimestre (a renda é a mesma nos dois, por isso as mudanças vêm dos preços). As listas de
  maiores movimentos só incluem concelhos com ≥ 20 avaliações bancárias em 3 meses e sem dados voláteis.
- **Volume como sinal de previsão**: a variação anual do número de avaliações bancárias foi testada nos
  dois modelos, com a regra fixada antes (entra se melhorar a 12 meses sem piorar o presente). Na
  previsão das **vendas do INE** (histórico desde 2019) não melhorou (12 meses: 43,3% → 42,9% menos erro
  que a regra ingénua) e **ficou de fora**. Nas previsões de **apartamentos e moradias** (avaliação
  bancária desde 2011) melhorou em todos os horizontes (12 meses: 18,5% → 22,1% e 37,4% → 39,4%), sem
  piorar a cobertura dos intervalos, e **entrou**.

### Comprar casa: esforço e comprar ou arrendar

Calculadora no site (secção "Comprar casa"), feita no browser: área, entrada, prazo, taxa e número de
salários são escolhidos pelo utilizador (por omissão 90 m², 10% de entrada, 30 anos, 1 salário) e
ficam guardados só nesse browser. A taxa por omissão é a mesma dos cenários de juros: Euribor 12M do
último mês + a diferença observada entre a taxa média dos novos créditos à habitação (BCE) e a Euribor.
Por concelho:

- **Esforço de compra** = prestação (crédito a prestação constante sobre preço mediano × área × (1 − entrada))
  ÷ ganho médio mensal bruto do concelho (INE 0012653). Também em anos de salário bruto (14 meses).
  Referência: o Banco de Portugal limita a prestação a 50% do rendimento **líquido**, cerca de 40% do
  bruto para um salário médio.
- **Comprar ou arrendar**: prestação vs renda da mesma casa (renda mediana de novos contratos × área) e o
  **ponto de equilíbrio** = (taxa + ~1,3% de IMI, manutenção e seguros − renda anual ÷ preço): a
  valorização anual a partir da qual comprar sai mais barato do que arrendar. A prestação inclui
  amortização (poupança), por isso o ponto de equilíbrio é a comparação mais justa; assume que a entrada
  renderia a mesma taxa.
- Mapa ("Esforço de compra", "Prestação face à renda"), colunas do ranking, detalhe, leitura e comparação.
  Não entra em nenhum score.

Limites: o preço é a mediana de todas as vendas (casas muito diferentes); o salário é de quem **trabalha**
no concelho, não de quem lá vive (exagera o esforço nos concelhos-dormitório, como Odivelas ou Cascais),
é individual, bruto e de um ano antes do preço; nos concelhos baratos do interior muitas casas vendidas
precisam de obras e as arrendadas não, o que favorece artificialmente a compra; ficam de fora IMT, imposto
do selo, escritura, seguros do crédito e mudanças de taxa ao longo do empréstimo.

### Teste de juros, ciclo preço–volume e avaliação vs preço pago

- **Teste de juros** (calculadora "Comprar casa"): prestação e esforço com a taxa N p.p. acima (por omissão
  +2), o mesmo empréstimo; quantos concelhos passam de 40% do salário bruto.
- **Ciclo preço–volume** (`imopt/market.py`): variação do preço a 12 meses contra a variação anual do
  número de avaliações bancárias (compras com crédito), por concelho com ≥ 20 avaliações em 3 meses, em
  quatro fases. "Preço a subir, menos compras" é a fase típica de fim de ciclo — não diz quando, nem se, os
  preços descem. Trajetória nacional desde 2012 (avaliação e número de avaliações, variação num ano).
- **Avaliação bancária vs preço pago**: avaliação média dos mesmos 12 meses que o preço de venda do INE
  cobre (≥ 9 meses publicados), face a esse preço, e a variação dessa diferença num ano. O nível é
  sobretudo composição (a avaliação só cobre compras com crédito); a variação é o sinal (avaliações a
  ficar para trás = bancos mais cautelosos ou mais compras sem crédito). Série nacional desde 2019.

Tudo só contexto: não entra em nenhum score.

### Rendimento de quem vive, Censos, alojamento local, construção nova e esforço no tempo

Indicadores do catálogo de indicadores principais do INE (`imopt/housing.py`), com as dimensões confirmadas
no snapshot bruto do build de 2026-10-01 (ver `config/sources.yml`). Nenhum entra em score.

| Chave | Código | Nível | O que é |
|---|---|---|---|
| `irs_median` | 0012757 | concelho, anual 2018+ | Mediana do rendimento bruto declarado deduzido do IRS liquidado, por sujeito passivo (€/ano) |
| `dwellings_stock` | 0008329 | concelho, anual 2011–2022 | Alojamentos familiares clássicos (parque habitacional) |
| `census_*` | 0012502 | concelho (geocod de 4 dígitos), 2021 | Censos: total, residência secundária, vagos para venda/arrendamento, vagos por outros motivos |
| `tourism_beds`, `tourism_beds_al` | 0013366 | concelho, anual 2023+ | Camas em alojamento turístico: total e alojamento local (10+ camas) |
| `dwellings_licensed` | 0012097 | **só até NUTS III**, mensal | Fogos licenciados em construções novas para habitação familiar (dim_3 T = todas as tipologias) |
| `dwellings_completed` | 0012778 | **só até NUTS II**, trimestral | Fogos concluídos em construções novas para habitação familiar |

- **Calculadora "Comprar casa"**: rendimento à escolha entre o salário médio bruto de quem **trabalha** no
  concelho (por omissão, como antes) e a mediana do IRS após imposto de quem **vive** no concelho (÷ 12;
  limite aproximado de 45%). O IRS corrige os concelhos-dormitório, mas é a mediana de todas as pessoas que
  declaram (inclui pensionistas e tempo parcial), por isso é mais baixo: com IRS e 1 pessoa, o esforço
  típico é 43% (140 de 299 concelhos acima de 45%); com 2 pessoas, 22% (29 concelhos).
- **Censos 2021**: % de alojamentos vagos (e só os vagos para venda ou arrendamento) e de residência
  secundária, por concelho — mapa, detalhe, comparação.
- **Alojamento turístico**: camas de alojamento local e totais por 100 alojamentos (parque de 2022). O INE
  só conta estabelecimentos com 10+ camas: o alojamento local pequeno, que é a maioria, fica de fora.
- **Construção nova** (só nacional, porque o INE não publica por concelho): fogos licenciados e concluídos
  por ano e por 1000 alojamentos, e os últimos 12 meses face aos anteriores. 2025: 42 066 licenciados
  (7,0 por 1000) e 27 301 concluídos, longe dos ~76 000 concluídos de 2005. Os campos `building_permits` e
  `completed_dwellings`, que alimentariam o sub-score de oferta, continuam vazios: não há dados por concelho.
- **Esforço de compra no tempo**: 90 m² à avaliação bancária mediana do país, 90% a 30 anos à taxa média
  dos novos créditos (BCE) de cada trimestre, desde 2011: em € e em % do salário médio bruto (desde 2021)
  e da mediana do IRS (desde 2018). 2026T2: 742 €/mês, 47% do salário médio (de 2024) e 72% da mediana do
  IRS, contra 36% no fim de 2019.
- **Não feito — compras sem crédito**: precisaria do número de vendas por concelho. O 0012786 é o valor das
  transações em €, e só até NUTS II; 0012748 e 0012742 (rendimento bruto médio, agregados fiscais por
  escalão) também ficaram de fora por não acrescentarem ao que já está.

### Ronda 3: freguesias, arrendar, Europa, explicação do score, turismo e mais

- **Freguesias com rendimento e Censos** (`imopt/parishes.py`): a tabela de freguesias passa a incluir todas as
  freguesias com preço (INE, ~350), rendimento do IRS (0012757, ~790 — o INE não publica as que têm poucos
  declarantes) ou Censos 2021 (~3080: vagos e residência secundária). Mapa com todas as fronteiras (sem dados
  = cinzento) e quatro indicadores novos: rendimento, esforço de compra (preço da freguesia ÷ IRS de quem lá
  vive, com a casa e o crédito da calculadora), vagos e 2.ª habitação.
- **Esforço de arrendar**: renda da mesma casa ÷ rendimento escolhido, na calculadora, no mapa, no ranking,
  no detalhe e na comparação. Com o salário de quem trabalha: 39% no concelho típico; 116 de 247 concelhos
  acima de 40% (referência do Eurostat para sobrecarga com a habitação).
- **Porque é este o score**: no detalhe de cada concelho, as três peças do score de valorização (percentis
  da subida a 12 meses, a 3 anos e da rendibilidade baixa), a média e, nos concelhos voláteis, a atenuação.
  As peças saem do mesmo cálculo (`score_part_*` em `scoring.py`); o score não muda.
- **Portugal face à Europa** (`imopt/europe.py`): HPI do Eurostat ÷ IHPC de cada país (2015 = 100), num
  pedido para os 27 países. Até 2025T4, Portugal subiu +123% acima da inflação desde 2015, 1.º de 26 países
  (empatado com a Hungria; mediana +42%); +16% no último ano (2.º). O IHPC com base 2015 do Eurostat termina
  em 2025T4 (o Eurostat mudou a base), por isso as contas reais param aí.
- **Turismo** (0012089 mensal e 0013288 anual, por concelho): hóspedes nos últimos 12 meses e variação, parte
  em alojamento local, taxa de ocupação-cama. Mapa "Turismo: hóspedes num ano".
- **Licenças por tipologia** (0012097, só nacional): peso de T0/T1, T2, T3 e T4+ nos fogos licenciados (2020
  vs 2025) ao lado da subida do preço de cada tipologia. Em 2025, 50% das licenças foram T0–T2 (36% em 2020).
- **Seguir concelhos**: botão ☆ no detalhe; secção "Os teus concelhos" com o que mudou no trimestre, score,
  previsão, esforço e fase do ciclo. Guardado só no browser.
- **Previsão vs ponto de equilíbrio**: no detalhe, a previsão do preço a 12 meses (e o intervalo de 80%) ao
  lado da valorização a partir da qual comprar compensa face a arrendar, dizendo se o intervalo fica todo
  acima, todo abaixo ou se não decide. Com aviso: uma previsão a 12 meses não diz nada sobre os anos
  seguintes e não é aconselhamento.

### Ronda 4: estado das fontes, novas tentativas, esforço no tempo por concelho, rendas, crédito e ficha

- **Estado das fontes** no topo do site: diz se todas as fontes vieram neste build; se o INE não respondeu,
  quantos indicadores usam os dados do último build que chegou ao INE e de que dia (`meta.json`:
  `ine_summary`, a partir de `data/clean/ine_status.json`). A lista dos que falharam abre ao clicar.
- **Novas tentativas automáticas**: além do build semanal (segunda, 06:17 UTC), o workflow corre todos os
  dias às 10:47 e 16:47 UTC, mas só constrói e publica se o último build não chegou ao INE (o passo
  "Decidir se é preciso tentar outra vez" lê `ine_status.json` do branch `data`). Push e execução manual
  constroem sempre.
- **Esforço de compra ao longo do tempo, por concelho** (`housing.effort_history_muni`): por trimestre desde
  2019T4, 90 m² ao preço mediano do concelho, 90% a 30 anos à taxa média dos novos créditos do trimestre, ÷
  rendimento do concelho (IRS de quem vive e salário de quem trabalha; o do ano ou o último até 2 anos antes).
  Gráfico no detalhe; em "Perspetivas", a mediana dos concelhos (IRS: 24% → 41%) e onde mais subiu. Em 93 de
  299 concelhos o esforço pelo menos duplicou.
- **Rendas por freguesia**: variação da renda mediana de novos contratos a 1 e 3 anos e n.º de contratos
  (0012600, 0012601 ao nível da freguesia), na tabela, no mapa de freguesias e numa lista das que mais
  subiram (com pelo menos 50 contratos).
- **Crédito à habitação novo** (BCE MIR, `M.PT.B.A2C.A.B.A.2250.EUR.N` e `...EUR.P`, confirmadas no build):
  soma de 12 meses, variação e parte de renegociações. 12 meses até 2026-08: 32,0 mil M€ (+18%), o valor
  nominal mais alto desde 2003; ~21% renegociações.
- **Custo de construção vs preço** (INE 0011748, mensal, nacional; dim_3 T/1 materiais/2 mão de obra): desde
  2021 o custo de construir subiu +35% (mão de obra +45%), o preço das casas novas +63% e o das usadas +76%.
- **Ficha para imprimir**: botão "Imprimir ficha" no detalhe; a impressão (ou "guardar como PDF") mostra só o
  concelho, com data e fontes.

### O meu imóvel: análise não vinculativa

Secção do site onde a pessoa indica concelho (e, se quiser, freguesia), mês da compra, preço, área e tipo
de casa e, opcionalmente, o crédito, o rendimento líquido do agregado e a renda atual. Tudo é calculado no
browser; os dados ficam só nesse browser (`localStorage`), nada é enviado. Devolve:

- **preço pago face ao mercado da altura**: €/m² pago vs mediana de venda do concelho e da freguesia (INE,
  desde 2019) e vs avaliação bancária do tipo de casa no trimestre da compra;
- **valor estimado hoje**: preço pago × variação de um índice local desde a compra, por ordem de preferência
  avaliação bancária do tipo de casa no concelho (desde 2011), avaliação bancária de todas as casas, preço
  mediano de venda do concelho; com o intervalo dado pelos outros índices locais. O índice nacional só é usado
  se nenhum local cobrir a data. Valorização real (IHPC) e previsão a 12 meses do concelho;
- **crédito**: prestação, taxa de esforço face ao rendimento líquido (limite de 50% do Banco de Portugal),
  com +2 p.p. de juros, e crédito em dívida face ao valor estimado;
- **arrendamento**: renda de mercado (renda mediana de novos contratos da freguesia ou do concelho × área,
  com o 1.º e 3.º quartil do concelho), rendibilidade bruta e líquida com pressupostos editáveis (IMI,
  condomínio, seguro, meses vazio, manutenção, IRS sobre rendas), saldo face à prestação e, se a casa já
  estiver arrendada, renda atual face ao mercado;
- **comprar ou arrendar** para aquela casa (ponto de equilíbrio).

Aviso obrigatório no topo da secção, no resultado e na impressão: estimativa estatística, não vinculativa;
não é avaliação imobiliária nem aconselhamento financeiro, fiscal ou jurídico; para decisões, perito
avaliador registado na CMVM, banco ou contabilista. Os dados vêm de `history.json` (preço por freguesia,
avaliação bancária trimestral por concelho e tipo, IHPC; ~0,4 MB), descarregado só quando a secção é usada.
"Imprimir análise" imprime só a análise e o aviso.

### Ronda 5: validação, resumo e site mais leve

- **Que sinais ajudam a prever o preço** (`imopt/signals.py`): seis sinais candidatos (crédito novo, custo de
  construção, licenças, avaliação face ao preço, esforço de compra do concelho, dormidas turísticas) são
  acrescentados um a um à previsão de vendas do INE e testados no mesmo backtest sem ver o futuro. Regra
  fixada antes de ver os resultados: entra se reduzir o erro a 12 meses em pelo menos 1% sem piorar o
  trimestre seguinte em mais de 1%. **Resultado (2026-10-01): nenhum passa** (de −0,0% a −4,5%); a previsão não
  muda (`PRODUCTION = ()`). Exploratório com a avaliação bancária de apartamentos e moradias (15 anos): as
  licenças melhoram os apartamentos +1,2% mas pioram as moradias −6,3%, e o esforço faz o inverso (+2,8% e
  −4,5%) — sinais trocados, lido como ruído. O teste é refeito em cada build e mostrado em "Perspetivas"
  (custa cerca de 1 minuto a mais por build).
- **Valor justo com dados novos**: IRS de quem vive, alojamento local, casas vagas e 2.ª habitação testados com
  validação cruzada de 10 partes repetida 5 vezes; entra se o R² subir pelo menos 0,005 em média e em todas
  as repetições (regra aplicada em cada build). Entraram o IRS (0,837 → 0,849) e a 2.ª habitação
  (0,840 → 0,846); R² final 0,849. Concelhos sem IRS publicado (7) ficam sem valor justo. Rendimento e 2.ª
  habitação também são consequência dos preços: os efeitos descrevem, não provam causa.
- **Resumo** no topo: seis números (preço real, esforço, crédito novo, concelhos em fase de fim de ciclo,
  previsão a 12 meses e posição na UE), cada um com ligação para a secção.
- **Site mais leve**: `municipalities.json` passa de 1,4 MB para 0,8 MB — as séries, previsões e esforço por
  concelho vão para `series.json` (0,6 MB), descarregado em segundo plano depois de a página aparecer; as
  freguesias (1 MB + mapa) só quando se abre o mapa de freguesias ou um concelho; os ficheiros iniciais são
  pedidos em paralelo; os gráficos de "Perspetivas" só são desenhados quando a secção se aproxima do ecrã.
  O código do site continua num ficheiro (`app.js`): partir em módulos não o tornava mais rápido — o peso
  estava nos dados.
- **População por concelho**: 0008273 (estimativas anuais 2011–2023, dim_3 = T, dim_4 = T) substitui a
  estimativa densidade × área nos indicadores por habitante (dormidas por habitante, saldo migratório por mil
  habitantes no valor justo). 0004163 só tem país e regiões e 0004350 (subsídio de desemprego) só o total
  nacional: ficaram de fora — não há desemprego por concelho no catálogo principal do INE.

### Freguesias

`imopt/parishes.py`. O preço mediano de venda por freguesia vem do mesmo indicador do INE (0012234,
nível freguesia/união de freguesias; código DICOFRE = últimos 6 dígitos do `geocod`), e a renda por
freguesia do 0012600 (Metodologia 2021, anual; dimensões não confirmadas ao vivo). O INE só publica
~400 das ~3000 freguesias (quase todas urbanas). Para cada uma: preço, variação a 12 meses, preço
face ao concelho e face à mediana das freguesias vizinhas com dados (mínimo 2).

- **Detalhe de cada concelho**: tabela das suas freguesias (funciona mesmo sem fronteiras).
- **Mapa**: botão "Freguesias", com 4 métricas, e lista das mais baratas do que as vizinhas.
  Precisa das fronteiras: `geo.parishes_geojson` em `config/sources.yml` (o "georef" do OpenDataSoft,
  confirmado no site publicado). A primeira que funcionar fica em
  `data/clean/geo_parishes.json` e é reutilizada; também podes pôr lá um GeoJSON teu (ex.: CAOP da
  DGT) com o código DICOFRE numa das propriedades de `geo.parish_props`. Sem fronteiras, o mapa
  avisa e a tabela continua.
- Limites: medianas de poucas vendas (uma freguesia "barata" pode ter vendido casas mais pequenas ou
  a precisar de obras); uniões de freguesias desagregadas depois de 2013 podem não ligar às fronteiras.

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
