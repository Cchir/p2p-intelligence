"""Serving layer: export dashboard-facing tables to parquet, plus a dbt test summary.

The warehouse is rebuilt from a 730 MB source. The dashboard needs only aggregates and model
outputs, which are committed so the app deploys without running the pipeline.
"""

from __future__ import annotations

import json
import logging
import shutil

from p2p import config
from p2p.analysis.common import connect

log = logging.getLogger(__name__)

MARTS = ["mart_monthly_kpis", "mart_vendor_kpis", "dim_activity"]


def dbt_summary() -> dict:
    results = json.loads((config.DBT_DIR / "target" / "run_results.json").read_text())["results"]
    tests = [r for r in results if r["unique_id"].startswith(("test.", "unit_test."))]
    return {"models": sum(r["unique_id"].startswith("model.") for r in results), "tests": len(tests),
            "tests_passed": sum(r["status"] == "pass" for r in tests),
            "singular": [r["unique_id"].split(".")[-1] for r in tests if "reconcile" in r["unique_id"] or "gapless" in r["unique_id"]]}


def run() -> None:
    if config.SERVING.exists():
        shutil.rmtree(config.SERVING)
    config.SERVING.mkdir(parents=True)
    with connect() as con:
        analytics = [r[0] for r in con.execute(
            "select table_name from information_schema.tables where table_schema = 'analytics'").fetchall()]
        for t in MARTS + [f"analytics.{a}" for a in analytics]:
            out = config.SERVING / f"{t.removeprefix('analytics.')}.parquet"
            con.execute(f"copy (select * from {t}) to '{out.as_posix()}' (format parquet, compression zstd)")
        kpis = con.execute(
            """
            select count(*) as n_items, count(distinct document_id) as n_documents, count(distinct vendor_id) as n_vendors,
                   sum(order_value_eur) as order_value_eur, sum(n_events) as n_events,
                   count(*) filter (status = 'paid') as n_paid, count(*) filter (status = 'open') as n_open,
                   count(*) filter (status = 'deleted') as n_deleted, median(days_create_to_clear) as median_days_paid_only
            from fct_po_items
            """
        ).df().iloc[0].to_dict()
    (config.SERVING / "kpis.json").write_text(json.dumps({k: float(v) for k, v in kpis.items()}, indent=2))
    (config.SERVING / "dbt_summary.json").write_text(json.dumps(dbt_summary(), indent=2))
    shutil.copy(config.REPORTS / "metrics.json", config.SERVING / "metrics.json")
    size = sum(p.stat().st_size for p in config.SERVING.iterdir()) / 1e6
    log.info("exported %d files (%.1f MB)", len(list(config.SERVING.iterdir())), size)
