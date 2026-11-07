"""Run every analysis, persist results to the warehouse `analytics` schema and reports/metrics.json."""

from __future__ import annotations

import json
import logging
import time

import numpy as np

from p2p import config
from p2p.analysis import alerts, bayes, causal, compliance, conformal, process, sequence, survival
from p2p.analysis.common import write_table

log = logging.getLogger("p2p.analyse")


def _jsonable(o):
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_jsonable(v) for v in o]
    if isinstance(o, float) and np.isnan(o):
        return None
    return o


def run(skip_slow: bool = False) -> dict:
    t0 = time.perf_counter()
    m: dict = {}

    log.info("compliance")
    rules = compliance.rule_summary()
    write_table("rule_summary", rules)
    write_table("compliance_by_area", compliance.by_spend_area())
    write_table("sod_users", compliance.sod_users())
    m["compliance"] = {"overall": compliance.overall(), "rules": rules.drop(columns="definition").to_dict(orient="records")}

    log.info("process mining")
    for name, fn in [("variant_summary", process.variant_summary), ("top_variants", process.top_variants),
                     ("straight_through", process.straight_through), ("automation", process.automation),
                     ("bottlenecks", process.bottlenecks), ("process_edges", process.edges),
                     ("stage_times", process.monthly_stage_times)]:
        write_table(name, fn())
    if not skip_slow:
        conf = process.conformance()
        write_table("conformance", conf)
        m["conformance"] = conf.to_dict(orient="records")

    log.info("survival analysis")
    km, sc, ratios, calib, backtests, open_items, cash = survival.run()
    for name, df in [("km_curves", km), ("survival_scores", sc), ("time_ratios", ratios), ("survival_calibration", calib),
                     ("cash_backtest", backtests), ("cash_forecast", cash)]:
        write_table(name, df)
    m["survival"] = {"scores": sc.to_dict(orient="records"), "backtest": backtests.to_dict(orient="records"),
                     "cash_forecast": cash.to_dict(orient="records"),
                     "median_days": km.groupby("flow")["median_days"].first().to_dict()}

    log.info("causal inference")
    effects, segments = causal.run()
    write_table("causal_effects", effects)
    write_table("causal_segments", segments)
    m["causal"] = {"effects": effects.to_dict(orient="records"), "segments": segments.to_dict(orient="records")}

    log.info("conformal prediction")
    results, sample, meta, _ = conformal.run()
    write_table("conformal_results", results)
    write_table("conformal_sample", sample)
    m["conformal"] = {"results": results.to_dict(orient="records"), "meta": meta}

    log.info("hierarchical vendor model")
    validation, vendors, meta = bayes.run()
    write_table("vendor_validation", validation)
    write_table("vendor_posterior", vendors)
    m["bayes"] = {"validation": validation.to_dict(orient="records"), "meta": meta}

    log.info("alerts and anomalies")
    metrics, scored, curve = alerts.fit_alerts()
    write_table("alert_scored", scored)
    write_table("alert_cost_curve", curve)
    anomaly, ameta = alerts.anomalies()
    write_table("anomaly_scores", anomaly.nlargest(5000, "anomaly_score"))
    best = curve.loc[curve["net_saving_eur"].idxmax()]
    m["alerts"] = {"metrics": metrics, "assumptions": alerts.COSTS, "best": best.to_dict(), "anomaly": ameta}

    queue = alerts.work_queue(open_items, anomaly, vendors)
    write_table("work_queue", queue)
    m["work_queue"] = {"items": len(queue), "exposure_eur": float(queue["order_value_eur"].sum())}

    if not skip_slow:
        log.info("sequence model")
        seq, meta = sequence.run()
        write_table("sequence_results", seq)
        m["sequence"] = {"results": seq.to_dict(orient="records"), "meta": meta}

    existing = {}
    path = config.REPORTS / "metrics.json"
    if skip_slow and path.exists():
        existing = json.loads(path.read_text())
    path.write_text(json.dumps({**existing, **_jsonable(m)}, indent=2, default=str))
    log.info("analysis finished in %.1fs", time.perf_counter() - t0)
    return m
