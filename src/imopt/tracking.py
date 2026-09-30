"""Arquivo de previsões e avaliação contra os valores reais publicados depois (ver README, "Perspetivas").

Ao contrário do backtest (que usa as séries já revistas), isto compara o que o site disse na altura com
o que o INE veio a publicar: é a medida mais honesta da qualidade das previsões.

- Cada conjunto de dados novo ("vintage": último trimestre de vendas + último mês de avaliação bancária,
  ou último ano de rendas) é guardado uma única vez, na primeira build que o vê. Builds semanais sem
  dados novos não duplicam previsões.
- Quando o valor real de um trimestre/ano previsto é publicado, mede-se o erro (em log, ~%), se caiu nos
  intervalos de 50% e 80%, e o erro da regra ingénua «fica igual» (último valor publicado na altura).
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("imopt")

COLS = ["kind", "vintage", "issued", "origin", "dico", "target", "h", "mid", "lo50", "hi50", "lo80", "hi80", "last_actual"]
NUM = ["h", "mid", "lo50", "hi50", "lo80", "hi80", "last_actual"]


def _numeric(df: pd.DataFrame) -> pd.DataFrame:
    for c in NUM:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df


def load(path: Path | None) -> pd.DataFrame:
    if path is not None and Path(path).exists():
        try:
            return pd.read_parquet(path)
        except Exception as e:  # noqa: BLE001
            log.warning("arquivo de previsões ilegível (%s): começa vazio", e)
    return pd.DataFrame(columns=COLS)


def save(df: pd.DataFrame, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def record(archive: pd.DataFrame, outlook: dict, per: dict[str, dict], feats: pd.DataFrame,
           today: dt.date | None = None) -> pd.DataFrame:
    """Acrescenta as previsões deste build, se forem de um conjunto de dados ainda não arquivado."""
    today = today or dt.date.today()
    seen = set(archive["vintage"]) if len(archive) else set()
    price = dict(zip(feats["dico"].astype(str), feats["price"]))
    rent = dict(zip(feats["dico"].astype(str), feats["rent"])) if "rent" in feats else {}
    rows = []
    s = outlook.get("sales")
    if s and s.get("origin"):
        vint = f"sales:{s['origin']}:{s.get('last_valuation') or '-'}"
        if vint not in seen:
            for d, v in per.items():
                f = v.get("fc")
                if not f or price.get(d) is None or pd.isna(price.get(d)):
                    continue
                for i, p in enumerate(f["periods"]):
                    rows.append({"kind": "sales", "vintage": vint, "issued": today.isoformat(), "origin": s["origin"],
                                 "dico": d, "target": p, "h": i + 1, "mid": f["mid"][i],
                                 "lo50": f["lo50"][i], "hi50": f["hi50"][i], "lo80": f["lo80"][i], "hi80": f["hi80"][i],
                                 "last_actual": float(price[d])})
    r = outlook.get("rent")
    if r and r.get("origin_year"):
        vint = f"rent:{r['origin_year']}:{s.get('last_valuation') if s else '-'}"
        if vint not in seen:
            for d, v in per.items():
                if v.get("rent_fc") is None or rent.get(d) is None or pd.isna(rent.get(d)):
                    continue
                rows.append({"kind": "rent", "vintage": vint, "issued": today.isoformat(), "origin": r["origin_year"],
                             "dico": d, "target": v["rent_fc_year"], "h": 1, "mid": v["rent_fc"], "lo50": None, "hi50": None,
                             "lo80": v["rent_fc_lo80"], "hi80": v["rent_fc_hi80"], "last_actual": float(rent[d])})
    if not rows:
        return archive
    new = _numeric(pd.DataFrame(rows, columns=COLS))
    return new if archive.empty else pd.concat([_numeric(archive.copy()), new], ignore_index=True)


def _actuals(df: pd.DataFrame | None) -> dict[tuple[str, str], float]:
    if df is None or df.empty:
        return {}
    d = df.dropna(subset=["dico", "value"])
    return {(str(a), str(p)): float(v) for a, p, v in zip(d["dico"], d["period"], d["value"])}


def evaluate(archive: pd.DataFrame, sales: pd.DataFrame | None, rent: pd.DataFrame | None) -> tuple[dict, dict]:
    """Resumo para o outlook.json e, por concelho, as previsões passadas já confrontadas com a realidade."""
    out: dict = {"n_archived": int(len(archive)), "n_vintages": int(archive["vintage"].nunique()) if len(archive) else 0,
                 "first_issued": str(archive["issued"].min()) if len(archive) else None, "sales": [], "rent": None}
    if archive.empty:
        return out, {}
    act = {"sales": _actuals(sales), "rent": _actuals(rent)}
    a = _numeric(archive.copy())
    a["actual"] = [act[k].get((str(d), str(t))) for k, d, t in zip(a["kind"], a["dico"], a["target"])]
    pending = a[a["actual"].isna()]
    out["n_pending"] = int(len(pending))
    out["next_targets"] = sorted(pending.loc[pending["kind"] == "sales", "target"].unique().tolist())[:2]
    ev = a.dropna(subset=["actual", "mid", "last_actual"]).copy()
    out["n_evaluated"] = int(len(ev))
    if ev.empty:
        return out, {}
    ev["err"] = np.log(ev["actual"] / ev["mid"])
    ev["err_naive"] = np.log(ev["actual"] / ev["last_actual"])
    ev["in80"] = (ev["actual"] >= ev["lo80"]) & (ev["actual"] <= ev["hi80"])
    ev["in50"] = (ev["actual"] >= ev["lo50"]) & (ev["actual"] <= ev["hi50"])

    def summ(g: pd.DataFrame) -> dict:
        mae, mae_n = float(g["err"].abs().mean()), float(g["err_naive"].abs().mean())
        has50 = g["lo50"].notna()
        return {"n": int(len(g)), "n_vintages": int(g["vintage"].nunique()), "n_concelhos": int(g["dico"].nunique()),
                "targets": sorted(g["target"].astype(str).unique().tolist()),
                "mae_model": mae, "mae_naive": mae_n, "skill": 1 - mae / mae_n if mae_n > 0 else None,
                "bias": float(-g["err"].mean()),        # positivo = previsões acima do real
                "coverage80": float(g["in80"].mean()),
                "coverage50": float(g.loc[has50, "in50"].mean()) if has50.any() else None}

    sales_ev = ev[ev["kind"] == "sales"]
    out["sales"] = [{"h": int(h), **summ(g)} for h, g in sales_ev.groupby("h")]
    rent_ev = ev[ev["kind"] == "rent"]
    out["rent"] = summ(rent_ev) if len(rent_ev) else None
    per: dict[str, dict] = {}
    # por concelho: para cada trimestre já publicado, a previsão feita com mais antecedência
    first = sales_ev.sort_values(["issued", "h"], ascending=[True, False]).drop_duplicates(["dico", "target"])
    for d, g in first.groupby("dico"):
        per[str(d)] = {"fc_past": [{"target": t, "issued": i, "h": int(h), "mid": float(m), "lo80": _f(lo), "hi80": _f(hi),
                                    "actual": float(ac)} for t, i, h, m, lo, hi, ac in
                                   zip(g["target"], g["issued"], g["h"], g["mid"], g["lo80"], g["hi80"], g["actual"])]}
    return out, per


def _f(v) -> float | None:
    return None if v is None or pd.isna(v) else float(v)
