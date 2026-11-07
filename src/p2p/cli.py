"""Command-line entry point.

    p2p build        # download -> bronze parquet -> dbt build (models and tests)
    p2p analyse      # process mining, compliance and all models
    p2p export       # write dashboard-facing tables to dashboard/data
    p2p all          # build + analyse + export
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys

from p2p import config, export, extract


def build(force: bool = False) -> None:
    extract.run(force=force)
    # dbt stops on failing tests, so a broken warehouse never reaches the models.
    result = subprocess.run([sys.executable, "-m", "dbt.cli.main", "build", "--profiles-dir", "."], cwd=config.DBT_DIR)
    if result.returncode:
        sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(prog="p2p")
    parser.add_argument("command", choices=["build", "analyse", "export", "all"])
    parser.add_argument("--force", action="store_true", help="re-download and rebuild bronze")
    parser.add_argument("--skip-slow", action="store_true", help="skip conformance replay and the sequence model")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(name)s | %(message)s")
    logging.getLogger("jax").setLevel(logging.WARNING)
    config.ensure_dirs()
    if args.command in ("build", "all"):
        build(force=args.force)
    if args.command in ("analyse", "all"):
        from p2p.analysis import run_all

        run_all.run(skip_slow=args.skip_slow)
    if args.command in ("export", "all"):
        export.run()


if __name__ == "__main__":
    main()
