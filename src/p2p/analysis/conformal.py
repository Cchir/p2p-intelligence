"""Payment date ranges that keep their promise: conformalized quantile regression.

Quantile models give a range, but nothing guarantees a "90% range" holds 90% of the time on new
data. Conformalized quantile regression (Romano, Patterson & Candes, 2019) measures the miss on
held-back calibration data and widens or narrows the range to match. Calibrating per flow
(Mondrian) keeps the promise within each flow too, not just on average.

Split by time to mimic deployment, and only on items with enough follow-up to have an outcome.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from p2p.analysis.common import encode, item_features

log = logging.getLogger(__name__)
ALPHA = 0.10
CAP = 240  # days; every item in the study has at least this much follow-up
TRAIN_END, CAL_END, TEST_END = "2018-04-15", "2018-05-01", "2018-05-22"


def _frame() -> pd.DataFrame:
    df = item_features()
    df = df[df["flow"].isin(["three_way_before_gr", "three_way_after_gr"]) & (df["order_value_eur"] > 0)
            & (df["status"] != "deleted") & (df["created_ts"] < TEST_END)].copy()
    df["y"] = df["days_create_to_clear"].clip(upper=CAP).fillna(CAP)
    return df


def _coverage(y, lo, hi) -> float:
    return float(np.mean((y >= lo) & (y <= hi)))


def cqr_correction(y, lo, hi, alpha: float = ALPHA) -> float:
    """The conformal quantile of the nonconformity scores, with the finite-sample correction."""
    scores = np.maximum(lo - y, y - hi)
    n = len(scores)
    level = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
    return float(np.quantile(scores, level, method="higher"))


def run():
    df = _frame()
    X = encode(df).to_numpy(float)
    y = df["y"].to_numpy()
    tr = (df["created_ts"] < TRAIN_END).to_numpy()
    cal = ((df["created_ts"] >= TRAIN_END) & (df["created_ts"] < CAL_END)).to_numpy()
    te = (df["created_ts"] >= CAL_END).to_numpy()

    params = dict(max_iter=250, learning_rate=0.08, max_leaf_nodes=31, random_state=42)
    lo_m = HistGradientBoostingRegressor(loss="quantile", quantile=ALPHA / 2, **params).fit(X[tr], y[tr])
    hi_m = HistGradientBoostingRegressor(loss="quantile", quantile=1 - ALPHA / 2, **params).fit(X[tr], y[tr])
    lo, hi = lo_m.predict(X), hi_m.predict(X)

    q_all = cqr_correction(y[cal], lo[cal], hi[cal])
    flows = df["flow"].to_numpy()
    q_flow = {f: cqr_correction(y[cal & (flows == f)], lo[cal & (flows == f)], hi[cal & (flows == f)]) for f in np.unique(flows)}
    q_vec = np.array([q_flow[f] for f in flows])

    rows = []
    for name, low, high in [("Raw quantile model", lo, hi), ("Conformal (global)", lo - q_all, hi + q_all),
                       ("Conformal (per flow)", lo - q_vec, hi + q_vec)]:
        row = {"method": name, "coverage": _coverage(y[te], low[te], high[te]), "avg_width_days": float((high[te] - low[te]).mean())}
        for f in np.unique(flows):
            m = te & (flows == f)
            row[f"coverage_{f}"] = _coverage(y[m], low[m], high[m])
        rows.append(row)
    results = pd.DataFrame(rows)
    log.info("conformal\n%s", results.T)

    sample = df[te].assign(lower=(lo - q_vec)[te], upper=(hi + q_vec)[te]).sample(400, random_state=1)
    sample = sample[["item_id", "flow", "y", "lower", "upper"]].sort_values("y")
    meta = {"target_coverage": 1 - ALPHA, "n_train": int(tr.sum()), "n_calibration": int(cal.sum()), "n_test": int(te.sum()),
            "correction_days": {k: float(v) for k, v in q_flow.items()}}
    return results, sample, meta, (lo_m, hi_m, q_flow)
