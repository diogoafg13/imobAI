"""Séries paradas: avisa quando o último período de uma série é mais antigo do que o atraso normal de publicação.

Motivo: em 2026 o Eurostat mudou o IHPC de conjunto de dados e a série antiga ficou parada em dez/2025 sem dar erro
— os preços reais ficaram três trimestres desatualizados até alguém reparar. Com este aviso, uma fonte que deixa de
ser atualizada (mudança de código, de base, de formato) aparece no site e no resumo do build.

Atraso máximo por omissão, contado desde o FIM do último período publicado: mensal 4 meses, trimestral 9 meses,
anual 30 meses (as estatísticas anuais do INE por concelho saem com 1 a 2 anos de atraso). Cada indicador pode ter
`max_age_months` no config, ou `static: true` (ex.: Censos 2021, que só mudam com o censo seguinte).
"""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd

DEFAULT_MONTHS = {"month": 4, "quarter": 9, "year": 30}


def period_end(p: str) -> tuple[dt.date, str] | None:
    """'2026-08' / '2026Q2' / '2026' (e sort_key AAAAMM do INE) -> (último dia do período, frequência)."""
    p = str(p).strip()
    if m := re.fullmatch(r"(\d{4})-(\d{2})", p):
        y, mo = int(m.group(1)), int(m.group(2))
        kind = "month"
    elif m := re.fullmatch(r"(\d{4})\s*[QT](\d)", p):
        y, mo = int(m.group(1)), int(m.group(2)) * 3
        kind = "quarter"
    elif m := re.fullmatch(r"(\d{4})", p):
        y, mo = int(m.group(1)), 12
        kind = "year"
    else:
        return None
    nxt = dt.date(y + (mo == 12), mo % 12 + 1, 1)
    return nxt - dt.timedelta(days=1), kind


def _last(df: pd.DataFrame) -> tuple[dt.date, str, str] | None:
    if df is None or df.empty or "period" not in df:
        return None
    d = df.dropna(subset=["value"]) if "value" in df else df
    if d.empty:
        return None
    if "sort_key" in d and "period_kind" in d and d["sort_key"].notna().all():
        k = int(d["sort_key"].max())
        kind = str(d["period_kind"].iloc[0])
        y, s = divmod(k, 100)
        label = f"{y}" if kind == "year" else f"{y}Q{s}" if kind == "quarter" else f"{y}-{s:02d}"
    else:
        label = str(max(d["period"].astype(str)))
    pe = period_end(label)
    return (pe[0], pe[1], label) if pe else None


def check(frames: dict, macro_frames: dict, cfg: dict, today: dt.date | None = None) -> list[dict]:
    """Lista de séries paradas: {source, key, last, months, limit}."""
    today = today or dt.date.today()
    out = []
    specs = {("INE", k): s for k, s in (cfg.get("ine", {}).get("indicators") or {}).items()}
    specs.update({("BCE/Eurostat/BIS", k): s for k, s in (cfg.get("macro") or {}).items()})
    for (src, key), spec in specs.items():
        spec = spec or {}
        if spec.get("static"):
            continue
        df = (frames if src == "INE" else macro_frames).get(key)
        last = _last(df)
        if last is None:
            continue
        end, kind, label = last
        months = (today.year - end.year) * 12 + (today.month - end.month)
        limit = int(spec.get("max_age_months") or DEFAULT_MONTHS[kind])
        if months > limit:
            out.append({"source": src, "key": key, "last": label, "months": months, "limit": limit})
    return sorted(out, key=lambda r: -r["months"] / r["limit"])
