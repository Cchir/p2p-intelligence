"""From scores to decisions: invoice-correction alerts, anomaly detection and the work queue.

Alert model: when an invoice is first booked, predict whether it will later need correcting
(a cancelled invoice or a price change). Reviewing it first is worth it only if the expected loss
avoided beats the cost of the review, so the threshold comes from a cost model rather than 0.5.
Every cost is a stated assumption and can be changed on the dashboard.

Anomaly detection: an Isolation Forest on each item's behaviour, checked against the rule breaks it
never saw, gives a second, independent signal.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, roc_auc_score

from p2p.analysis.common import encode, item_features, query

log = logging.getLogger(__name__)
TRAIN_END, CAL_END, TEST_END = "2018-08-01", "2018-09-01", "2018-11-15"
COSTS = {"review_cost_eur": 10.0, "correction_cost_eur": 180.0, "share_preventable": 0.5}


def invoice_frame() -> pd.DataFrame:
    """One row per item at its first booked invoice, with only what was known at that moment."""
    state = query(
        """
        with state as (
            select i.item_id, i.first_invoice_ts as invoice_ts,
                   count(*) filter (e.activity = 'Record Goods Receipt' and e.event_ts < i.first_invoice_ts) as gr_so_far,
                   count(*) filter (e.activity in ('Change Quantity', 'Change Price') and e.event_ts < i.first_invoice_ts) as changes_so_far,
                   count(*) filter (e.event_ts < i.first_invoice_ts) as events_so_far,
                   date_diff('hour', i.created_ts, i.first_invoice_ts) / 24.0 as days_since_created,
                   date_diff('hour', i.vendor_invoice_ts, i.first_invoice_ts) / 24.0 as vendor_invoice_lag
            from fct_po_items i join fct_item_events e using (item_id)
            where i.first_invoice_ts is not null
            group by all
        ),
        later as (
            select e.item_id,
                   max((e.activity in ('Cancel Invoice Receipt', 'Change Price'))::int) as corrected
            from fct_item_events e join fct_po_items i using (item_id)
            where e.event_ts > i.first_invoice_ts
            group by e.item_id
        )
        select s.*, coalesce(l.corrected, 0) as corrected
        from state s left join later l using (item_id)
        """
    )
    return item_features().merge(state, on="item_id")


def fit_alerts():
    df = invoice_frame()
    df = df[df["flow"].isin(["three_way_before_gr", "three_way_after_gr"]) & (df["invoice_ts"] < TEST_END)]
    base = encode(df).reset_index(drop=True)
    state = df[["gr_so_far", "changes_so_far", "events_so_far", "days_since_created", "vendor_invoice_lag"]].reset_index(drop=True)
    X = pd.concat([base, state], axis=1).to_numpy(float)
    y = df["corrected"].to_numpy()
    ts = df["invoice_ts"]
    tr, cal, te = (ts < TRAIN_END).to_numpy(), ((ts >= TRAIN_END) & (ts < CAL_END)).to_numpy(), (ts >= CAL_END).to_numpy()

    gb = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=31, l2_regularization=1.0, random_state=42)
    gb.fit(X[tr], y[tr])
    iso = IsotonicRegression(out_of_bounds="clip").fit(gb.predict_proba(X[cal])[:, 1], y[cal])
    p = iso.predict(gb.predict_proba(X[te])[:, 1])

    yt = y[te]
    order = np.argsort(-p)
    top = order[: max(1, len(p) // 10)]
    value_top = np.argsort(-df.loc[te, "order_value_eur"].to_numpy())[: len(top)]
    metrics = {
        "n_test": int(te.sum()), "base_rate": float(yt.mean()), "roc_auc": float(roc_auc_score(yt, p)),
        "pr_auc": float(average_precision_score(yt, p)), "lift_top10pct": float(yt[top].mean() / yt.mean()),
        "precision_top10pct": float(yt[top].mean()), "recall_top10pct": float(yt[top].sum() / yt.sum()),
        "value_rule_precision_top10pct": float(yt[value_top].mean()), "brier": float(np.mean((p - yt) ** 2)),
        "mean_predicted": float(p.mean()),
    }
    log.info("alert metrics %s", metrics)
    scored = pd.DataFrame({"item_id": df.loc[te, "item_id"].values, "p_correction": p, "corrected": yt,
                           "order_value_eur": df.loc[te, "order_value_eur"].values})
    return metrics, scored, cost_curve(scored, **COSTS)


def cost_curve(scored: pd.DataFrame, review_cost_eur: float, correction_cost_eur: float, share_preventable: float) -> pd.DataFrame:
    """Net saving of reviewing everything above each score, against reviewing nothing.

    Isotonic calibration gives many invoices the same score. They can't be told apart, so the
    curve moves one score level at a time rather than splitting a tied group arbitrarily.
    """
    levels = (scored.groupby("p_correction", as_index=False).agg(n=("corrected", "size"), hits=("corrected", "sum"))
              .sort_values("p_correction", ascending=False))
    reviewed, caught = levels["n"].cumsum(), levels["hits"].cumsum()
    return pd.DataFrame({
        "reviewed": reviewed.astype(int), "share_reviewed": reviewed / len(scored), "threshold": levels["p_correction"],
        "corrections_caught": caught.astype(int),
        "net_saving_eur": caught * correction_cost_eur * share_preventable - reviewed * review_cost_eur,
    }).reset_index(drop=True)


def anomalies() -> tuple[pd.DataFrame, dict]:
    df = query(
        """
        select i.item_id, i.flow, i.status, i.vendor_id, i.order_value_eur, c.n_rules_broken,
               i.n_events, i.n_goods_receipts, i.n_invoices, i.n_clears, i.n_rework_events,
               coalesce(i.days_create_to_clear, -1) as days_to_clear,
               coalesce(i.days_create_to_gr, -1) as days_to_gr,
               coalesce(i.days_invoice_to_clear, -1) as days_invoice_to_clear,
               v.n_items as path_frequency
        from fct_po_items i
        join mart_compliance c using (item_id)
        join mart_variants v on v.flow = i.flow and v.variant = i.trace
        where i.flow <> 'consignment'
        order by i.item_id
        """
    )
    # Rule columns are deliberately excluded, so agreement with the rules is real evidence.
    feats = ["n_events", "n_goods_receipts", "n_invoices", "n_clears", "n_rework_events", "days_to_clear", "days_to_gr",
             "days_invoice_to_clear"]
    X = np.column_stack([np.log1p(df[feats].clip(lower=0)), np.log1p(df["order_value_eur"].clip(lower=0)), np.log(df["path_frequency"])])
    iso = IsolationForest(n_estimators=200, max_samples=4096, random_state=42, n_jobs=-1).fit(X)
    df["anomaly_score"] = -iso.score_samples(X)
    flagged = (df["n_rules_broken"] > 0).to_numpy()
    order = np.argsort(-df["anomaly_score"].to_numpy())
    meta = {"base_rate_rules": float(flagged.mean())}
    for k in (500, 2500, 10000):
        meta[f"precision_at_{k}"] = float(flagged[order[:k]].mean())
    log.info("anomaly %s", meta)
    return df[["item_id", "anomaly_score", "n_rules_broken"]], meta


def work_queue(open_items: pd.DataFrame, anomaly: pd.DataFrame, vendors: pd.DataFrame, top: int = 1000) -> pd.DataFrame:
    """Open items a controller should look at first: exposure weighted by independent risk signals."""
    rules = query("select * from mart_compliance")
    rule_cols = [c for c in rules.columns if c[:1] == "r" and c[1:3].isdigit()]
    q = open_items.merge(rules[["item_id", "n_rules_broken", *rule_cols]], on="item_id", how="left")
    q = q.merge(anomaly[["item_id", "anomaly_score"]], on="item_id", how="left")
    q = q.merge(vendors[["vendor_id", "p_problem_vendor"]], on="vendor_id", how="left").fillna({"p_problem_vendor": 0})
    q["anomaly_pct"] = q["anomaly_score"].rank(pct=True).fillna(0.5)
    q["overdue_flag"] = q["age_days"] > 120
    # A simple, explainable score: each signal adds risk; exposure sets the order inside a risk level.
    q["risk"] = (q["n_rules_broken"].clip(upper=3) * 0.5 + q["p_problem_vendor"] * 0.5
                 + (q["anomaly_pct"] > 0.95) * 0.5 + q["overdue_flag"] * 0.5)
    q["priority"] = q["risk"] * np.log1p(q["order_value_eur"])

    def why(r) -> str:
        out = [c[4:].replace("_", " ") for c in rule_cols if r[c]]
        if r["p_problem_vendor"] > 0.8:
            out.append("problem vendor")
        if r["anomaly_pct"] > 0.95:
            out.append("unusual path")
        if r["overdue_flag"]:
            out.append("over 120 days")
        return "; ".join(out)

    q = q[q["risk"] > 0].nlargest(top, "priority").copy()
    q["reasons"] = q.apply(why, axis=1)
    return q[["item_id", "vendor_id", "flow", "spend_area", "order_value_eur", "age_days", "risk", "priority", "p_paid_30d", "reasons"]]
