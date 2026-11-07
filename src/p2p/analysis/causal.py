"""Does rework cause late payment, or does it only travel with it?

Double machine learning (Chernozhukov et al., 2018) on a landmark design:

* Landmark: items still unpaid and not deleted 14 days after creation. Treatment is a price or
  quantity change inside those 14 days. Without a landmark, slow items have longer to pick up a
  change, which manufactures an effect (immortal-time bias).
* Outcome: unpaid days in the 180 days after the landmark, a restricted mean, so every item in the
  cohort has full follow-up and censoring plays no part.
* Adjustment: flexible models of outcome and treatment given creation-time features, cross-fitted
  by purchasing document so lines of one order never sit on both sides of a fold.

Checks: a placebo with shuffled treatment, overlap trimming, and the Cinelli-Hazlett robustness
value (how strong a hidden confounder would need to be to erase the result).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold

from p2p.analysis.common import encode, item_features, query

log = logging.getLogger(__name__)
LANDMARK = 14
HORIZON = 180
FOLLOW_UP_END = pd.Timestamp("2019-01-18")


def cohort() -> pd.DataFrame:
    df = item_features()
    df = df[df["flow"].isin(["three_way_before_gr", "three_way_after_gr"]) & (df["order_value_eur"] > 0)].copy()
    cutoff = FOLLOW_UP_END - pd.Timedelta(days=LANDMARK + HORIZON)
    df = df[df["created_ts"] <= cutoff]
    land = df["created_ts"] + pd.Timedelta(days=LANDMARK)
    still_in = (df["first_clear_ts"].isna() | (df["first_clear_ts"] > land)) & (df["deleted_ts"].isna() | (df["deleted_ts"] > land))
    df = df[still_in].copy()
    land = df["created_ts"] + pd.Timedelta(days=LANDMARK)

    changes = query(
        f"""
        select e.item_id,
               max((e.activity = 'Change Price')::int) as price_change,
               max((e.activity = 'Change Quantity')::int) as quantity_change
        from fct_item_events e join fct_po_items i using (item_id)
        where e.activity in ('Change Price', 'Change Quantity')
          and e.event_ts <= i.created_ts + interval {LANDMARK} day
        group by e.item_id
        """
    )
    df = df.merge(changes, on="item_id", how="left")
    df[["price_change", "quantity_change"]] = df[["price_change", "quantity_change"]].fillna(0).astype(int)
    df["any_change"] = ((df["price_change"] + df["quantity_change"]) > 0).astype(int)

    days_to_pay = (df["first_clear_ts"] - (df["created_ts"] + pd.Timedelta(days=LANDMARK))).dt.total_seconds() / 86400
    df["unpaid_days"] = days_to_pay.clip(upper=HORIZON).fillna(HORIZON)
    df["deleted_later"] = df["deleted_ts"].notna().astype(int)
    for c in ("vendor_prior_days", "vendor_prior_rework"):
        df[c] = df[c].fillna(df[c].median())
    return df


def dml(df: pd.DataFrame, treatment: str, n_splits: int = 5, seed: int = 42) -> dict:
    X = encode(df).to_numpy(float)
    y = df["unpaid_days"].to_numpy(float)
    t = df[treatment].to_numpy(float)
    groups = df["document_id"].to_numpy()
    y_hat, t_hat = np.zeros(len(df)), np.zeros(len(df))
    for tr, te in GroupKFold(n_splits).split(X, y, groups):
        y_hat[te] = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.08, random_state=seed).fit(X[tr], y[tr]).predict(X[te])
        t_hat[te] = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, random_state=seed).fit(X[tr], t[tr]).predict_proba(X[te])[:, 1]

    keep = (t_hat > 0.01) & (t_hat < 0.99)  # overlap trimming
    ry, rt = (y - y_hat)[keep], (t - t_hat)[keep]
    theta = float((rt * ry).sum() / (rt * rt).sum())

    # Standard error clustered by purchasing document.
    psi = pd.DataFrame({"g": groups[keep], "s": rt * (ry - theta * rt)}).groupby("g")["s"].sum().to_numpy()
    se = float(np.sqrt((psi**2).sum()) / (rt * rt).sum())

    dof = keep.sum() - 2
    t_stat = theta / se
    r2 = t_stat**2 / (t_stat**2 + dof)                       # partial R2 of treatment with the outcome
    f = abs(t_stat) / np.sqrt(dof)
    rv = 0.5 * (np.sqrt(f**4 + 4 * f**2) - f**2)             # Cinelli & Hazlett (2020) robustness value

    rng = np.random.default_rng(seed)
    rp = rng.permutation(rt)
    placebo = float((rp * ry).sum() / (rp * rp).sum())

    return {
        "treatment": treatment, "n": int(keep.sum()), "treated": int(t[keep].sum()),
        "naive_diff_days": float(y[t == 1].mean() - y[t == 0].mean()),
        "dml_effect_days": theta, "se": se, "ci_low": theta - 1.96 * se, "ci_high": theta + 1.96 * se,
        "p_value": float(2 * stats.norm.sf(abs(t_stat))), "partial_r2": float(r2), "robustness_value": float(rv),
        "placebo_effect_days": placebo, "share_trimmed": float(1 - keep.mean()),
        "outcome_model_r2": float(1 - ((y - y_hat) ** 2).sum() / ((y - y.mean()) ** 2).sum()),
    }


def by_segment(df: pd.DataFrame, column: str, min_treated: int = 300) -> pd.DataFrame:
    rows = []
    for level, g in df.groupby(column):
        if g["any_change"].sum() < min_treated or (1 - g["any_change"]).sum() < min_treated:
            continue
        rows.append({"segment": level, **dml(g, "any_change", n_splits=3)})
    return pd.DataFrame(rows)


def run():
    df = cohort()
    log.info("causal cohort %s items, change rate %.3f", f"{len(df):,}", df["any_change"].mean())
    results = pd.DataFrame([dml(df, t) for t in ("any_change", "price_change", "quantity_change")])
    robust = dml(df[df["deleted_later"] == 0], "any_change")
    robust["treatment"] = "any_change, excluding later deletions"
    results = pd.concat([results, pd.DataFrame([robust])], ignore_index=True)
    return results, by_segment(df, "spend_area")
