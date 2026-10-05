"""Backtest multi-país do score nacional (ver README, secção "Backtest").

Objetivo: saber se o score nacional (scoring.national_scores) teria sinalizado
antes de quedas grandes do preço da habitação, e com quantos falsos alarmes,
usando vários países da UE (não só Portugal, que só tem um episódio de queda
independente: 2008-2013).

Regra central — SEM LOOK-AHEAD: para cada trimestre `t`, o score é recalculado
usando scoring.national_scores() só com dados até `t` (janela expansiva). Como
essa função já só olha para o último ponto das séries que recebe (z-score e
tendência calculados sobre a série inteira que lhe é passada), basta truncar as
séries a `t` antes de a chamar — não foi preciso alterar a lógica de scoring.py
nem o resultado do painel em produção (ver test_backtest.py::test_no_lookahead).

Decisões de método (fixadas antes de olhar para resultados, conforme pedido):
- Países: 8 com boom-bust conhecido (PT, ES, IE, EL, CY, EE, LV, LT) + 5 de
  controlo sem crise grande (DE, AT, BE, FR, PL). PL nunca adotou o euro: serve
  de caso onde a componente da Euribor é sempre excluída (ver abaixo).
- Euribor: só entra no score de um país a partir do ano de adoção do euro
  (EURO_SINCE). Antes disso (ex.: Letónia/Lituânia/Estónia pré-2011/2014/2015)
  ou para países fora da área do euro (Polónia), a componente é omitida — a
  Euribor é uma taxa única da área do euro, não um sinal desses países nesses
  períodos. `scoring.national_scores` já lida bem com euribor=None (componente
  opcional), por isso isto não exige nenhuma alteração ao scoring.
- Janela mínima: 40 trimestres (10 anos) de histórico do HPI antes de o score
  começar a ser avaliado (parâmetro `min_history`, testado também com 32 e 60).
- Alvos: variação nominal e real do HPI a 4/8/12 trimestres; evento binário de
  queda real ≥10% (`drawdown_threshold`) nos 12 trimestres seguintes.
- Baselines: extraídos das MESMAS chamadas a national_scores (os componentes
  "hpi_yoy" e "credit_gap" já vêm com o seu próprio score logístico 0-100),
  para serem diretamente comparáveis ao score composto.

Limites conhecidos (repetidos no export JSON para o site):
- HPI e IHPC são séries revistas pelo Eurostat; não temos os valores tal como
  publicados na altura, o que otimiza ligeiramente os resultados face a um uso
  em tempo real.
- Os episódios não são independentes: a crise financeira global de 2008 atinge
  vários países ao mesmo tempo, por isso as métricas agregadas ("pooled") têm
  menos informação efetiva do que o número de países sugere.
- Poucos episódios de queda grande no total: risco de ajuste excessivo (as
  regras foram fixadas antes de ver os números, mas a amostra continua pequena).
- O desvio crédito/PIB tende a ser mais informativo em países com grande
  alavancagem bancária (ex. Chipre, Irlanda) do que noutros.
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import macro, scoring
from .pipeline import ROOT, _write_parquet, real_index
from .scoring import _shift_key

log = logging.getLogger("imopt")

# ---------------------------------------------------------------- parâmetros
DEFAULT_MIN_HISTORY = 40          # trimestres de HPI antes de começar a avaliar
ALT_MIN_HISTORIES = (32, 60)      # sensibilidade ao mínimo de histórico
HORIZONS = (4, 8, 12)             # trimestres à frente para os retornos
DRAWDOWN_HORIZON = 12
DEFAULT_DRAWDOWN_THRESHOLD = 0.10  # queda real >=10% nos 12 trimestres seguintes
DEFAULT_THRESHOLDS = (50, 60, 70, 80)  # limiares de alarme testados (70 = painel)

COUNTRIES = [
    {"code": "PT", "name": "Portugal", "group": "boom_bust", "euro_since": 1999},
    {"code": "ES", "name": "Espanha", "group": "boom_bust", "euro_since": 1999},
    {"code": "IE", "name": "Irlanda", "group": "boom_bust", "euro_since": 1999},
    {"code": "EL", "name": "Grécia", "group": "boom_bust", "euro_since": 2001},
    {"code": "CY", "name": "Chipre", "group": "boom_bust", "euro_since": 2008},
    {"code": "EE", "name": "Estónia", "group": "boom_bust", "euro_since": 2011},
    {"code": "LV", "name": "Letónia", "group": "boom_bust", "euro_since": 2014},
    {"code": "LT", "name": "Lituânia", "group": "boom_bust", "euro_since": 2015},
    {"code": "DE", "name": "Alemanha", "group": "control", "euro_since": 1999},
    {"code": "AT", "name": "Áustria", "group": "control", "euro_since": 1999},
    {"code": "BE", "name": "Bélgica", "group": "control", "euro_since": 1999},
    {"code": "FR", "name": "França", "group": "control", "euro_since": 1999},
    {"code": "PL", "name": "Polónia", "group": "control", "euro_since": None},
]
COUNTRY_BY_CODE = {c["code"]: c for c in COUNTRIES}

LIMITS_PT = [
    "HPI e IHPC são séries revistas pelo Eurostat: não temos os valores tal como "
    "publicados na altura, o que favorece ligeiramente os resultados face a um uso real.",
    "Os episódios não são independentes — a crise financeira global de 2008 atinge vários "
    "países ao mesmo tempo — por isso as métricas agregadas valem menos do que o número de "
    "países sugere.",
    "Poucos episódios de queda grande no total: risco de ajuste excessivo, mesmo com as regras "
    "fixadas antes de ver os resultados.",
    "O desvio crédito/PIB tende a ser mais informativo em países com grande alavancagem "
    "bancária (ex. Irlanda, Chipre) do que noutros.",
    "A Euribor só entra no score a partir da adoção do euro por cada país; antes disso (ou "
    "para países fora da área do euro) a componente de juros é omitida.",
    "O score nacional em produção nunca foi alterado por este backtest — os pesos e a lógica "
    "são exatamente os do painel.",
]

# ---------------------------------------------------------------- fontes
EUROSTAT_HPI_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hpi_q"
EUROSTAT_HICP_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_minr"  # ECOICOP ver. 2 (o prc_hicp_midx parou em dez/2025)
BIS_CREDIT_GAP_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CREDIT_GAP/1.0/Q.{cc}.P.A.C"
BIS_COUNTRY_CODE = {"EL": "GR"}  # Eurostat usa EL para a Grécia; o BIS usa GR


def _bis_code(cc: str) -> str:
    return BIS_COUNTRY_CODE.get(cc, cc)


def ingest_euribor(cfg: dict, data_dir: Path) -> pd.DataFrame | None:
    """Euribor 12M (BCE): série única, partilhada por todos os países do euro."""
    spec = cfg["macro"]["euribor_12m"]
    cache = data_dir / "clean" / "backtest_euribor_12m.parquet"
    try:
        df = macro.fetch_euribor(spec)
        _write_parquet(df, cache)
        return df
    except Exception as e:  # noqa: BLE001
        if cache.exists():
            log.warning("backtest euribor: falhou (%s), a usar cache", e)
            return pd.read_parquet(cache)
        log.warning("backtest euribor: indisponível (%s); componente de juros omitida", e)
        return None


def ingest_country(cc: str, data_dir: Path) -> dict[str, pd.DataFrame | None]:
    """HPI, IHPC e desvio crédito/PIB de um país, com cache em data/clean (falha não-fatal)."""
    specs = {
        "hpi": (macro.fetch_eurostat_hpi, {
            "url": EUROSTAT_HPI_URL,
            "params": {"geo": cc, "purchase": "TOTAL", "unit": "I15_Q", "format": "JSON", "lang": "EN"},
        }),
        "hicp": (macro.fetch_eurostat_hicp, {
            "url": EUROSTAT_HICP_URL,
            "params": {"geo": cc, "coicop18": "TOTAL", "unit": "I15", "format": "JSON", "lang": "EN"},
        }),
        "credit_gap": (macro.fetch_bis_credit_gap, {
            "url": BIS_CREDIT_GAP_URL.format(cc=_bis_code(cc)), "params": {"format": "csv"},
        }),
    }
    out: dict[str, pd.DataFrame | None] = {}
    for key, (fn, spec) in specs.items():
        cache = data_dir / "clean" / f"backtest_{key}_{cc}.parquet"
        try:
            df = fn(spec)
            if df is None or df.empty:
                raise ValueError("resposta vazia")
            _write_parquet(df, cache)
            out[key] = df
        except Exception as e:  # noqa: BLE001
            if cache.exists():
                log.warning("backtest %s/%s: falhou (%s), a usar cache", key, cc, e)
                out[key] = pd.read_parquet(cache)
            else:
                log.warning("backtest %s/%s: indisponível (%s)", key, cc, e)
                out[key] = None
    return out


# ---------------------------------------------------------------- núcleo (puro, sem I/O)
def _key(period: str) -> int:
    """'2015Q1' -> 201501 (mesma convenção de scoring._shift_key)."""
    y, q = period.split("Q")
    return int(y) * 100 + int(q)


_MONTH_END = {1: "03", 2: "06", 3: "09", 4: "12"}


def _euribor_cutoff(t_key: int) -> str:
    year, q = divmod(t_key, 100)
    return f"{year:04d}-{_MONTH_END[q]}"


def evaluate_country(country_code: str, hpi: pd.DataFrame, hicp: pd.DataFrame | None,
                     credit_gap: pd.DataFrame | None, euribor: pd.DataFrame | None,
                     euro_since: int | None, min_history: int = DEFAULT_MIN_HISTORY,
                     horizons: tuple[int, ...] = HORIZONS, drawdown_horizon: int = DRAWDOWN_HORIZON,
                     drawdown_threshold: float = DEFAULT_DRAWDOWN_THRESHOLD) -> pd.DataFrame:
    """Score em tempo real (sem look-ahead) trimestre a trimestre, com alvos futuros para avaliação.

    Função pura: recebe séries já carregadas e devolve um DataFrame, uma linha por
    trimestre avaliado. Reutiliza scoring.national_scores truncando as séries a cada
    `t` — a mesma lógica do painel em produção, sem duplicação nem alteração de pesos.
    """
    hpi = hpi[["period", "value"]].drop_duplicates("period").sort_values("period").reset_index(drop=True)
    hpi["key"] = hpi["period"].map(_key)
    nom_by_key = dict(zip(hpi["key"], hpi["value"]))

    real = real_index(hpi[["period", "value"]], hicp) if hicp is not None else None
    real_by_key: dict[int, float] = {}
    if real is not None and not real.empty:
        real = real.drop_duplicates("period").sort_values("period")
        real_by_key = dict(zip(real["period"].map(_key), real["value"]))

    cg = None
    if credit_gap is not None and not credit_gap.empty:
        cg = credit_gap[["period", "value"]].drop_duplicates("period").sort_values("period").reset_index(drop=True)
        cg["key"] = cg["period"].map(_key)

    eur = None
    if euribor is not None and not euribor.empty:
        eur = euribor[["period", "value"]].drop_duplicates("period").sort_values("period").reset_index(drop=True)

    rows = []
    for i in range(len(hpi)):
        if i + 1 < min_history:
            continue
        t_key = int(hpi["key"].iloc[i])
        t_period = hpi["period"].iloc[i]
        hpi_trunc = hpi.iloc[: i + 1][["period", "value"]]
        credit_trunc = cg.loc[cg["key"] <= t_key, ["period", "value"]] if cg is not None else None
        if credit_trunc is not None and credit_trunc.empty:
            credit_trunc = None
        eur_trunc = None
        if eur is not None and euro_since is not None and (t_key // 100) >= euro_since:
            cutoff = _euribor_cutoff(t_key)
            e = eur[eur["period"] <= cutoff]
            eur_trunc = e if not e.empty else None

        s = scoring.national_scores(hpi_trunc, eur_trunc, credit_trunc)
        comps = s["components"]
        row = {
            "country": country_code,
            "period": t_period,
            "key": t_key,
            "score": s["overall"],
            "baseline_hpi_yoy": comps.get("hpi_yoy", {}).get("score"),
            "baseline_credit_gap": comps.get("credit_gap", {}).get("score"),
            "hpi_real": real_by_key.get(t_key),
        }
        base_nom = nom_by_key[t_key]
        for h in horizons:
            fk = _shift_key(t_key, "quarter", -h)
            row[f"ret_nom_{h}q"] = (nom_by_key[fk] / base_nom - 1) if fk in nom_by_key else None
            if t_key in real_by_key and fk in real_by_key:
                row[f"ret_real_{h}q"] = real_by_key[fk] / real_by_key[t_key] - 1
            else:
                row[f"ret_real_{h}q"] = None

        row["drawdown_real_12q"] = None
        row["event_drawdown"] = None
        if t_key in real_by_key:
            base_real = real_by_key[t_key]
            future = []
            for s_ in range(1, drawdown_horizon + 1):
                fk = _shift_key(t_key, "quarter", -s_)
                if fk not in real_by_key:
                    future = None
                    break
                future.append(real_by_key[fk])
            if future:
                dd = min(v / base_real - 1 for v in future)
                row["drawdown_real_12q"] = dd
                row["event_drawdown"] = int(dd <= -drawdown_threshold)
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- métricas (puras)
def spearman(x: pd.Series, y: pd.Series) -> float | None:
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(df) < 5 or df["x"].nunique() < 2 or df["y"].nunique() < 2:
        return None
    corr = df["x"].rank().corr(df["y"].rank())
    return None if pd.isna(corr) else float(corr)


def auc_binary(scores: pd.Series, labels: pd.Series) -> float | None:
    df = pd.DataFrame({"s": scores, "y": labels}).dropna()
    if df.empty or df["y"].nunique() < 2:
        return None
    n1 = int((df["y"] == 1).sum())
    n0 = int((df["y"] == 0).sum())
    if n1 == 0 or n0 == 0:
        return None
    ranks = df["s"].rank()
    r1 = ranks[df["y"] == 1].sum()
    return float((r1 - n1 * (n1 + 1) / 2) / (n1 * n0))


def hit_false_alarm(scores: pd.Series, labels: pd.Series, threshold: float) -> dict | None:
    df = pd.DataFrame({"s": scores, "y": labels}).dropna()
    if df.empty or df["y"].nunique() < 2:
        return None
    alarm = df["s"] >= threshold
    tp = int((alarm & (df["y"] == 1)).sum())
    fn = int((~alarm & (df["y"] == 1)).sum())
    fp = int((alarm & (df["y"] == 0)).sum())
    tn = int((~alarm & (df["y"] == 0)).sum())
    return {
        "hit_rate": tp / (tp + fn) if (tp + fn) else None,
        "false_alarm_rate": fp / (fp + tn) if (fp + tn) else None,
        "n_events": tp + fn,
        "n_no_events": fp + tn,
    }


def summarize(df: pd.DataFrame, score_col: str, thresholds=DEFAULT_THRESHOLDS) -> dict | None:
    if df.empty or score_col not in df or df[score_col].notna().sum() == 0:
        return None
    out: dict = {"n": int(df[score_col].notna().sum())}
    for h in HORIZONS:
        out[f"spearman_nom_{h}q"] = spearman(df[score_col], df[f"ret_nom_{h}q"])
        out[f"spearman_real_{h}q"] = spearman(df[score_col], df[f"ret_real_{h}q"])
    out["auc_drawdown"] = auc_binary(df[score_col], df["event_drawdown"])
    out["thresholds"] = {str(t): hit_false_alarm(df[score_col], df["event_drawdown"], t) for t in thresholds}
    return out


def detect_episodes(df_country: pd.DataFrame) -> list[tuple[str, str]]:
    """Períodos contíguos com evento de queda ativo (mesma queda de 12 trimestres a começar em cada t)."""
    d = df_country.sort_values("key").reset_index(drop=True)
    episodes, start = [], None
    for i, ev in enumerate(d["event_drawdown"]):
        if ev == 1 and start is None:
            start = i
        if start is not None and (ev != 1 or i == len(d) - 1):
            end = i - 1 if ev != 1 else i
            episodes.append((d["period"].iloc[start], d["period"].iloc[end]))
            start = None
    return episodes


def episode_hits(per_country_rows: dict[str, pd.DataFrame], threshold: float) -> dict:
    total, hit = 0, 0
    details = []
    for cc, df in per_country_rows.items():
        for start, end in detect_episodes(df):
            total += 1
            window = df[(df["period"] >= start) & (df["period"] <= end)]
            signaled = bool((window["score"] >= threshold).any())
            hit += int(signaled)
            details.append({"country": cc, "start": start, "end": end, "signaled": signaled})
    return {"n_episodes": total, "n_signaled": hit, "episodes": details}


def _clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        v = v.item()
    return round(v, 4) if isinstance(v, float) else v


# ---------------------------------------------------------------- síntese (demo, offline)
def demo_country_data(codes: list[str], n_quarters: int = 104) -> dict[str, dict]:
    """Dados sintéticos multi-país, deterministas, para testar/`--demo` sem rede.

    Países 'boom_bust' sobem forte a meio da série e caem >=25% real a seguir;
    países 'control' sobem de forma estável, sem correção grande.
    """
    out = {}
    quarters = [(1999 + i // 4, i % 4 + 1) for i in range(n_quarters)]
    periods = [f"{y}Q{q}" for y, q in quarters]
    for idx, cc in enumerate(codes):
        meta = COUNTRY_BY_CODE.get(cc)
        if meta is None:  # país fora da lista curada: sem forma conhecida, não é sintetizável
            continue
        rng = np.random.default_rng(1000 + idx)
        boom = meta["group"] == "boom_bust"
        h = 90.0
        vals = []
        for i in range(n_quarters):
            if boom and 32 <= i < 56:
                drift = 0.028
            elif boom and 56 <= i < 76:
                drift = -0.022
            else:
                drift = 0.006
            h *= 1 + drift + rng.normal(0, 0.006)
            vals.append(h)
        hpi = pd.DataFrame({"period": periods, "value": vals})
        hicp = pd.DataFrame({"period": periods, "value": [100 * 1.005 ** (i - 20) for i in range(n_quarters)]})
        cg_base = (np.array(vals) / pd.Series(vals).rolling(20, min_periods=1).mean().values - 1) * 40
        credit_gap = pd.DataFrame({"period": periods, "value": cg_base + rng.normal(0, 3, n_quarters)})
        out[cc] = {"hpi": hpi, "hicp": hicp, "credit_gap": credit_gap}
    return out


def demo_euribor(n_quarters: int = 104) -> pd.DataFrame:
    months = pd.period_range("1999-01", periods=n_quarters * 3, freq="M").astype(str)
    rng = np.random.default_rng(42)
    shape = np.concatenate([np.linspace(1, 4, len(months) // 3), np.linspace(4, 0.5, len(months) // 3),
                            np.linspace(0.5, 3.5, len(months) - 2 * (len(months) // 3))])
    return pd.DataFrame({"period": months, "value": shape + rng.normal(0, 0.1, len(months))})


# ---------------------------------------------------------------- orquestração
def run(countries: list[str] | None = None, data_dir: str | Path | None = None,
        min_history: int = DEFAULT_MIN_HISTORY, drawdown_threshold: float = DEFAULT_DRAWDOWN_THRESHOLD,
        thresholds: tuple[int, ...] = DEFAULT_THRESHOLDS, demo: bool = False) -> dict:
    codes = countries or [c["code"] for c in COUNTRIES]
    codes = [c.upper() for c in codes]

    if demo:
        raw = demo_country_data(codes)
        euribor = demo_euribor()
    else:
        from . import pipeline
        data_dir = Path(data_dir or ROOT / "data")
        cfg = pipeline.load_config()
        euribor = ingest_euribor(cfg, data_dir)
        raw = {cc: ingest_country(cc, data_dir) for cc in codes}

    per_country_rows: dict[str, pd.DataFrame] = {}
    for cc in codes:
        meta = COUNTRY_BY_CODE.get(cc, {"euro_since": None})
        data = raw.get(cc) or {}
        hpi = data.get("hpi")
        if hpi is None or hpi.empty:
            log.warning("backtest %s: sem HPI, país ignorado", cc)
            continue
        df = evaluate_country(cc, hpi, data.get("hicp"), data.get("credit_gap"),
                              euribor if meta.get("euro_since") else None, meta.get("euro_since"),
                              min_history=min_history, drawdown_threshold=drawdown_threshold)
        if not df.empty:
            per_country_rows[cc] = df

    pooled = pd.concat(per_country_rows.values(), ignore_index=True) if per_country_rows else pd.DataFrame()

    models = ("score", "baseline_hpi_yoy", "baseline_credit_gap")
    metrics_pooled = {m: summarize(pooled, m, thresholds) for m in models}
    metrics_per_country = {
        cc: {m: summarize(df, m, thresholds) for m in models} for cc, df in per_country_rows.items()
    }
    leave_one_out = {}
    for cc in per_country_rows:
        rest = pd.concat([d for k, d in per_country_rows.items() if k != cc], ignore_index=True) \
            if len(per_country_rows) > 1 else pd.DataFrame()
        leave_one_out[cc] = {"spearman_real_12q": spearman(rest["score"], rest["ret_real_12q"]) if not rest.empty else None,
                             "auc_drawdown": auc_binary(rest["score"], rest["event_drawdown"]) if not rest.empty else None}

    min_history_sensitivity = {}
    for mh in ALT_MIN_HISTORIES:
        alt_rows = []
        for cc in per_country_rows:
            meta = COUNTRY_BY_CODE.get(cc, {"euro_since": None})
            data = raw.get(cc) or {}
            hpi = data.get("hpi")
            if hpi is None or hpi.empty:
                continue
            df = evaluate_country(cc, hpi, data.get("hicp"), data.get("credit_gap"),
                                  euribor if meta.get("euro_since") else None, meta.get("euro_since"),
                                  min_history=mh, drawdown_threshold=drawdown_threshold)
            if not df.empty:
                alt_rows.append(df)
        alt_pooled = pd.concat(alt_rows, ignore_index=True) if alt_rows else pd.DataFrame()
        min_history_sensitivity[str(mh)] = {
            "spearman_real_12q": spearman(alt_pooled["score"], alt_pooled["ret_real_12q"]) if not alt_pooled.empty else None,
            "auc_drawdown": auc_binary(alt_pooled["score"], alt_pooled["event_drawdown"]) if not alt_pooled.empty else None,
        }

    ep70 = episode_hits(per_country_rows, 70)
    pt_metrics = metrics_per_country.get("PT")

    def _fmt_pct(x):
        return "n/d" if x is None else f"{round(x * 100)}%"

    thr70_pooled = (metrics_pooled.get("score") or {}).get("thresholds", {}).get("70")
    hpi_yoy_auc = (metrics_pooled.get("baseline_hpi_yoy") or {}).get("auc_drawdown")
    credit_gap_auc = (metrics_pooled.get("baseline_credit_gap") or {}).get("auc_drawdown")
    score_auc = (metrics_pooled.get("score") or {}).get("auc_drawdown")
    if score_auc is None or (hpi_yoy_auc is None and credit_gap_auc is None):
        baseline_note = "Dados insuficientes para comparar com as regras simples."
    else:
        beats_hpi = hpi_yoy_auc is None or score_auc > hpi_yoy_auc
        beats_credit = credit_gap_auc is None or score_auc > credit_gap_auc
        if beats_hpi and beats_credit:
            baseline_note = "O score composto teve melhor AUC do que as duas regras simples (só HPI; só crédito/PIB)."
        elif not beats_hpi and not beats_credit:
            baseline_note = "O score composto NÃO bateu nenhuma das duas regras simples (só HPI; só crédito/PIB) — ver métricas."
        else:
            worse_than = "do crescimento do HPI" if not beats_hpi else "do desvio crédito/PIB"
            baseline_note = f"O score composto ficou atrás da regra simples {worse_than} nesta amostra — ver métricas."
    verdict = (
        f"O score sinalizou (limiar 70) {ep70['n_signaled']} de {ep70['n_episodes']} episódios de queda real "
        f"≥{round(drawdown_threshold * 100)}% nos {len(per_country_rows)} países avaliados. "
        f"Taxa de falso alarme por trimestre a esse limiar: {_fmt_pct(thr70_pooled and thr70_pooled['false_alarm_rate'])}. "
        + baseline_note
    )

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "demo": demo,
        "params": {
            "min_history_quarters": min_history,
            "drawdown_threshold": drawdown_threshold,
            "thresholds": list(thresholds),
            "horizons_quarters": list(HORIZONS),
            "drawdown_horizon_quarters": DRAWDOWN_HORIZON,
            "alt_min_history_quarters": list(ALT_MIN_HISTORIES),
        },
        "countries": [
            {**{k: v for k, v in COUNTRY_BY_CODE[cc].items()}, "n_quarters_evaluated": len(per_country_rows[cc])}
            for cc in per_country_rows
        ],
        "series": {
            cc: {
                "period": df["period"].tolist(),
                "score": [_clean(v) for v in df["score"]],
                "hpi_real": [_clean(v) for v in df["hpi_real"]],
                "baseline_hpi_yoy": [_clean(v) for v in df["baseline_hpi_yoy"]],
                "baseline_credit_gap": [_clean(v) for v in df["baseline_credit_gap"]],
                "event_drawdown": [_clean(v) for v in df["event_drawdown"]],
            }
            for cc, df in per_country_rows.items()
        },
        "metrics": {
            "pooled": {m: _clean_metrics(v) for m, v in metrics_pooled.items()},
            "per_country": {cc: {m: _clean_metrics(v) for m, v in ms.items()} for cc, ms in metrics_per_country.items()},
            "leave_one_out": {cc: {k: _clean(v) for k, v in v_.items()} for cc, v_ in leave_one_out.items()},
            "min_history_sensitivity": min_history_sensitivity,
            "episodes_threshold_70": ep70,
            "portugal_only": {m: _clean_metrics(v) for m, v in (pt_metrics or {}).items()} if pt_metrics else None,
        },
        "limits": LIMITS_PT,
        "summary": {"verdict_pt": verdict},
    }


def _clean_metrics(m: dict | None) -> dict | None:
    if m is None:
        return None
    out = {}
    for k, v in m.items():
        if k == "thresholds":
            out[k] = {t: ({kk: _clean(vv) for kk, vv in tv.items()} if tv else None) for t, tv in v.items()}
        else:
            out[k] = _clean(v)
    return out
