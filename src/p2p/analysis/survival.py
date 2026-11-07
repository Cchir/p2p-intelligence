"""Time-to-payment with survival analysis, and a cash-out forecast for unpaid items.

A plain average of "days to pay" only sees finished items, so it understates slow ones. Survival
models use unfinished items too: an item unpaid after 90 days contributes "at least 90 days".
Deleted items are censored at deletion, so hazards are cause-specific to payment.

An accelerated failure time model gives readable effects ("this makes payment x% slower"). Its
conditional survival curve then gives each open item a payment forecast, summed into a cash-out
forecast that is backtested from an earlier as-of date against what was actually paid.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from lifelines import KaplanMeierFitter, LogLogisticAFTFitter, WeibullAFTFitter
from lifelines.utils import concordance_index

from p2p.analysis.common import SNAPSHOT, encode, item_features

log = logging.getLogger(__name__)
FLOWS = ["three_way_before_gr", "three_way_after_gr", "two_way"]
SPLIT = pd.Timestamp("2018-07-01")
TRAIN_SAMPLE = 40_000
SELECTION_DATE = pd.Timestamp("2018-08-15")


def survival_frame(as_of: pd.Timestamp = SNAPSHOT) -> pd.DataFrame:
    """Duration and event indicator as they would have been known on `as_of`."""
    df = item_features()
    df = df[df["flow"].isin(FLOWS) & (df["created_ts"] <= as_of) & (df["order_value_eur"] > 0)].copy()
    paid = df["first_clear_ts"].notna() & (df["first_clear_ts"] <= as_of)
    deleted = df["deleted_ts"].notna() & (df["deleted_ts"] <= as_of) & ~paid
    end = pd.Series(as_of, index=df.index)
    end = end.mask(deleted, df["deleted_ts"]).mask(paid, df["first_clear_ts"])
    df["duration"] = ((end - df["created_ts"]).dt.total_seconds() / 86400).clip(lower=0.04)
    df["event"] = paid.astype(int)
    df["unpaid_open"] = (~paid & ~deleted).astype(int)
    df["vendor_prior_days"] = df["vendor_prior_days"].fillna(df["vendor_prior_days"].median())
    df["vendor_prior_rework"] = df["vendor_prior_rework"].fillna(df["vendor_prior_rework"].median())
    df["log_prior_items"] = np.log1p(df["vendor_prior_items"])
    return df


def _design(df: pd.DataFrame) -> pd.DataFrame:
    X = encode(df, top=6)
    X = X.drop(columns=["created_month", "created_weekday", "vendor_prior_items"])
    X["log_prior_items"] = df["log_prior_items"].values
    X["vendor_prior_days"] = df["vendor_prior_days"].values / 30  # per extra month of vendor history
    # Reference levels and near-empty dummies out, to keep the design full rank.
    drop = [c for c in X if c in ("flow_three_way_before_gr", "item_type_Standard", "document_type_Standard PO",
                                  "spend_area_Packaging", "spend_class_NPR", "item_type_Limit") or X[c].mean() < 0.002
            or X[c].std() == 0]
    return X.drop(columns=drop)


def km_curves(df: pd.DataFrame) -> pd.DataFrame:
    frames = []
    grid = np.arange(0, 241, 5)
    for flow, g in df.groupby("flow"):
        km = KaplanMeierFitter().fit(g["duration"], g["event"])
        frames.append(pd.DataFrame({"flow": flow, "day": grid, "share_unpaid": km.survival_function_at_times(grid).values,
                                    "median_days": km.median_survival_time_}))
    return pd.concat(frames)


def fit_aft(df: pd.DataFrame, seed: int = 42):
    X = _design(df)
    train = df["created_ts"] < SPLIT
    idx = np.random.default_rng(seed).choice(np.flatnonzero(train), min(TRAIN_SAMPLE, train.sum()), replace=False)
    fit = pd.concat([X.iloc[idx], df[["duration", "event"]].iloc[idx]], axis=1)
    models = {"Weibull AFT": WeibullAFTFitter(penalizer=0.01), "Log-logistic AFT": LogLogisticAFTFitter(penalizer=0.01)}
    rows = []
    test = df[~train]
    Xt = X[~train]
    for name, m in models.items():
        m.fit(fit, "duration", "event")
        # Higher predicted median means longer time, so it is passed directly to the concordance.
        c = concordance_index(test["duration"], m.predict_median(Xt), test["event"])
        rows.append({"model": name, "concordance": c, "aic": m.AIC_})
    # Baseline a team would use today: the flow's historical median.
    flow_med = fit.join(df[["flow"]]).groupby("flow")["duration"].median()
    rows.append({"model": "Flow median (baseline)", "aic": np.nan,
                 "concordance": concordance_index(test["duration"], test["flow"].map(flow_med), test["event"])})
    return models, pd.DataFrame(rows), X


def time_ratios(model) -> pd.DataFrame:
    s = model.summary.reset_index()
    s = s[(s["param"] == s["param"].iloc[0]) & (s["covariate"] != "Intercept")]
    s = s.assign(time_ratio=np.exp(s["coef"]), ci_low=np.exp(s["coef lower 95%"]), ci_high=np.exp(s["coef upper 95%"]))
    return s[["covariate", "time_ratio", "ci_low", "ci_high", "p"]].sort_values("time_ratio", ascending=False)


def _prob_paid_within(model, X: pd.DataFrame, age: np.ndarray, horizon: float) -> np.ndarray:
    """P(paid in the next `horizon` days | still unpaid at this age), from the fitted curve."""
    t0 = model.predict_survival_function(X.iloc[:1], times=[1.0])  # validates the design early
    assert len(t0)
    out = np.zeros(len(X))
    # Survival depends on age, so evaluate in rounded-age buckets rather than one curve per item.
    buckets = np.round(age / 5).astype(int) * 5
    for b in np.unique(buckets):
        mask = buckets == b
        s0 = model.predict_survival_function(X[mask], times=[max(b, 0.5)]).values.ravel()
        s1 = model.predict_survival_function(X[mask], times=[b + horizon]).values.ravel()
        out[mask] = 1 - s1 / np.clip(s0, 1e-9, None)
    return out


def calibration(df: pd.DataFrame, model, X: pd.DataFrame) -> pd.DataFrame:
    """Predicted vs Kaplan-Meier median by predicted-risk decile, on the later half of the year."""
    test = df["created_ts"] >= SPLIT
    d = df[test].assign(pred=model.predict_median(X[test]).values)
    d["decile"] = pd.qcut(d["pred"].rank(method="first"), 10, labels=False) + 1
    rows = []
    for dec, g in d.groupby("decile"):
        km = KaplanMeierFitter().fit(g["duration"], g["event"])
        rows.append({"decile": dec, "predicted_median": g["pred"].median(), "km_median": km.median_survival_time_})
    return pd.DataFrame(rows)


def cash_backtest(as_of: pd.Timestamp, fitter=WeibullAFTFitter, horizon: int = 30) -> dict:
    """Stand at `as_of`, fit only on what was known, forecast the next `horizon` days of payments."""
    df = survival_frame(as_of)
    X = _design(df)
    idx = np.random.default_rng(1).choice(len(df), min(TRAIN_SAMPLE, len(df)), replace=False)
    m = fitter(penalizer=0.01).fit(
        pd.concat([X.iloc[idx], df[["duration", "event"]].iloc[idx]], axis=1), "duration", "event")
    open_mask = df["unpaid_open"] == 1
    p = _prob_paid_within(m, X[open_mask], df.loc[open_mask, "duration"].to_numpy(), horizon)
    forecast = float((p * df.loc[open_mask, "order_value_eur"]).sum())

    full = item_features()
    window = (full["first_clear_ts"] > as_of) & (full["first_clear_ts"] <= as_of + pd.Timedelta(days=horizon))
    prior = (full["first_clear_ts"] > as_of - pd.Timedelta(days=horizon)) & (full["first_clear_ts"] <= as_of)
    # Items created after as_of can also be paid inside the window; a forecast of today's book can't see them.
    book = full[window & (full["created_ts"] <= as_of) & full["flow"].isin(FLOWS)]
    return {"as_of": str(as_of.date()), "horizon_days": horizon, "forecast_eur": forecast,
            "actual_eur": float(book["order_value_eur"].sum()),
            "naive_last_period_eur": float(full.loc[prior & full["flow"].isin(FLOWS), "order_value_eur"].sum()),
            "open_items": int(open_mask.sum())}


def run():
    df = survival_frame()
    km = km_curves(df)
    models, scores, X = fit_aft(df)
    log.info("survival scores %s", scores.to_dict("records"))

    # Ranking and cash totals reward different things, so the cash model is chosen on its own
    # job, at a date kept apart from the three dates reported below.
    fitters = {"Weibull AFT": WeibullAFTFitter, "Log-logistic AFT": LogLogisticAFTFitter}
    selection = {}
    for name, f in fitters.items():
        r = cash_backtest(SELECTION_DATE, f)
        selection[name] = abs(r["forecast_eur"] / r["actual_eur"] - 1)
    chosen = min(selection, key=selection.get)
    log.info("cash model selection on %s: %s -> %s", SELECTION_DATE.date(), selection, chosen)
    model = models[chosen]

    ratios = time_ratios(model)
    calib = calibration(df, model, X)
    backtests = pd.DataFrame([cash_backtest(pd.Timestamp(d), fitters[chosen]) for d in ("2018-09-15", "2018-10-15", "2018-11-15")])
    backtests["model"] = chosen

    open_mask = df["unpaid_open"] == 1
    age = df.loc[open_mask, "duration"].to_numpy()
    open_items = df.loc[open_mask, ["item_id", "vendor_id", "flow", "spend_area", "order_value_eur", "duration"]].copy()
    open_items = open_items.rename(columns={"duration": "age_days"})
    for h in (30, 60, 90):
        open_items[f"p_paid_{h}d"] = _prob_paid_within(model, X[open_mask], age, h)
    cash = pd.DataFrame([{"horizon_days": h, "expected_cash_out_eur": float(
        (open_items[f"p_paid_{h}d"] * open_items["order_value_eur"]).sum())} for h in (30, 60, 90)])
    return km, scores, ratios, calib, backtests, open_items, cash
