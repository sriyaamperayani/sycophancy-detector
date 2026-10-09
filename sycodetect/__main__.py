"""CLI entry point.

    python -m sycodetect run --config configs/mock.yaml --out runs/mock
    python -m sycodetect report --run runs/mock
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import yaml

from .analysis import build_report
from .runner import Runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sycodetect", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run an experiment, then build the report")
    run_p.add_argument("--config", required=True)
    run_p.add_argument("--out", required=True, help="Output directory (re-use it to resume)")
    run_p.add_argument("--limit", type=int, help="Only use the first N questions (smoke test)")

    rep_p = sub.add_parser("report", help="Rebuild the report from an existing run")
    rep_p.add_argument("--run", required=True)

    args = parser.parse_args(argv)
    if args.cmd == "run":
        with open(args.config) as f:
            cfg = yaml.safe_load(f)
        if args.limit:
            cfg["limit"] = args.limit
        asyncio.run(Runner(cfg, args.out).run())
        report = build_report(args.out, cfg.get("styles"))
    else:
        report = build_report(args.run)
    print(f"Report written to {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
