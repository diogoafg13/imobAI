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
| 4. Cenários, alertas, backtest | Não implementado |

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
- **Nada disto foi validado por backtest** (2008, 2011–13). Não é aconselhamento financeiro.

## Anúncios (opcional)

Idealista e Imovirtual proíbem scraping nos termos de uso. Por isso `listings.enabled` está a `false`; o módulo respeita `robots.txt`, limita o ritmo e para perante 401/403/429. Para o Idealista, usa a API oficial.
