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
| 4. Backtest do score nacional | Implementado, multi-país (ver secção "Backtest do score nacional" abaixo). Cenários/alertas: não implementado. |

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

## Anúncios (opcional)

Idealista e Imovirtual proíbem scraping nos termos de uso. Por isso `listings.enabled` está a `false`; o módulo respeita `robots.txt`, limita o ritmo e para perante 401/403/429. Para o Idealista, usa a API oficial.
