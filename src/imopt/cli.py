"""CLI: python -m imopt build | build --demo | inspect <varcd>"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import backtest, demo, geo, ine, pipeline


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="imopt")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="descarrega, calcula e escreve site/data")
    b.add_argument("--demo", action="store_true", help="dados sintéticos (offline)")
    b.add_argument("--skip-geo", action="store_true")
    b.add_argument("--out", default=None)
    i = sub.add_parser("inspect", help="mostra dimensões e primeiras linhas de um indicador INE")
    i.add_argument("varcd")
    t = sub.add_parser("backtest", help="backtest multi-país do score nacional (ver README)")
    t.add_argument("--countries", default=None, help="códigos ISO2 separados por vírgula (default: todos)")
    t.add_argument("--out", default=None, help="default: site/data/backtest.json")
    t.add_argument("--demo", action="store_true", help="dados sintéticos (offline)")
    t.add_argument("--min-history", type=int, default=backtest.DEFAULT_MIN_HISTORY)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.cmd == "inspect":
        payload = ine.fetch(pipeline.load_config()["ine"]["base_url"], args.varcd)
        df = ine.parse_response(payload, args.varcd)
        dims = [c for c in df.columns if c.startswith("dim_")]
        print(f"{len(df)} linhas; períodos {df['period'].min()}..{df['period'].max()}")
        for c in dims:
            print(c, sorted(df[c].dropna().astype(str).unique())[:15])
        print(df.head(10).to_string())
        return 0

    if args.cmd == "backtest":
        codes = [c.strip() for c in args.countries.split(",")] if args.countries else None
        out = Path(args.out) if args.out else pipeline.ROOT / "site" / "data" / "backtest.json"
        results = backtest.run(countries=codes, demo=args.demo, min_history=args.min_history)
        out.parent.mkdir(parents=True, exist_ok=True)
        geo.dump(results, str(out))
        print(json.dumps({"generated_at": results["generated_at"], "demo": results["demo"],
                          "countries": len(results["countries"])}, ensure_ascii=False))
        return 0

    out = Path(args.out) if args.out else pipeline.ROOT / "site" / "data"
    if args.demo:
        frames, macro_frames = demo.demo_frames()
        meta = pipeline.build_outputs(frames, macro_frames, {"demo": "sintético"}, {"demo": "sintético"},
                                      out, demo.demo_geojson(), demo=True)
    else:
        meta = pipeline.run(out_dir=out, skip_geo=args.skip_geo)
    print(json.dumps({k: meta[k] for k in ("built_at", "demo", "latest_price_period", "n_municipalities")}, ensure_ascii=False))
    bad = [k for k, v in {**meta["sources"]["ine"], **meta["sources"]["macro"]}.items() if str(v).startswith(("ERRO", "CACHE"))]
    if bad:
        print("AVISO: fontes com erro:", ", ".join(bad), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
