"""Which vendors are genuinely problematic? A hierarchical Bayesian model of document quality.

A vendor with 2 problem items out of 3 tops a raw league table but tells you almost nothing.
Partial pooling lets each vendor's rate lean on the overall pattern in proportion to how little
data it has. Problems are corrected documents: a cancelled invoice or goods receipt, or a price
change. Validated out of time: fit on the first half of 2018, predict each vendor's second half.

    logit(p) = alpha + beta[spend_area] + u[vendor],   u[vendor] ~ Normal(0, sigma)
"""

from __future__ import annotations

import logging

import jax
import jax.numpy as jnp
import numpy as np
import numpyro
import numpyro.distributions as dist
import pandas as pd
from numpyro.infer import MCMC, NUTS

from p2p.analysis.common import query

log = logging.getLogger(__name__)
SPLIT = "2018-07-01"
TOP = 3.0  # "problem vendor" means at least this many times the typical rate


def _items() -> pd.DataFrame:
    return query(
        """
        select vendor_id, spend_area, created_ts,
               (n_invoice_cancels > 0 or n_gr_cancels > 0 or n_price_changes > 0)::int as problem
        from fct_po_items
        where flow in ('three_way_before_gr', 'three_way_after_gr') and order_value_eur > 0
        """
    )


def _aggregate(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby(["vendor_id", "spend_area"], as_index=False).agg(n=("problem", "size"), y=("problem", "sum"))


def model(area, vendor, n_area, n_vendor, n, y=None):
    alpha = numpyro.sample("alpha", dist.Normal(-3, 2))
    tau = numpyro.sample("tau", dist.HalfNormal(1))
    sigma = numpyro.sample("sigma", dist.HalfNormal(1))
    with numpyro.plate("areas", n_area):
        beta = numpyro.sample("beta", dist.Normal(0, 1))
    with numpyro.plate("vendors", n_vendor):
        u = numpyro.sample("u", dist.Normal(0, 1))  # non-centred: far better geometry for small vendors
    numpyro.sample("obs", dist.Binomial(n, logits=alpha + tau * beta[area] + sigma * u[vendor]), obs=y)


def fit(agg: pd.DataFrame, seed: int = 0, warmup: int = 600, samples: int = 600, chains: int = 2):
    areas = {a: i for i, a in enumerate(sorted(agg["spend_area"].unique()))}
    vendors = {v: i for i, v in enumerate(sorted(agg["vendor_id"].unique()))}
    numpyro.set_host_device_count(1)
    mcmc = MCMC(NUTS(model, target_accept_prob=0.85), num_warmup=warmup, num_samples=samples, num_chains=chains,
                chain_method="sequential", progress_bar=False)
    mcmc.run(jax.random.PRNGKey(seed), jnp.array(agg["spend_area"].map(areas)), jnp.array(agg["vendor_id"].map(vendors)),
             len(areas), len(vendors), jnp.array(agg["n"].values), jnp.array(agg["y"].values))
    return mcmc, areas, vendors


def _predict_vendor_rate(post: dict, vendors: dict, area_ix: np.ndarray, vendor_ix: np.ndarray) -> np.ndarray:
    """Posterior draws of the rate for (vendor, area) pairs. Unseen vendors draw a fresh effect."""
    rng = np.random.default_rng(0)
    u = np.asarray(post["u"])
    sigma, tau = np.asarray(post["sigma"]), np.asarray(post["tau"])
    alpha, beta = np.asarray(post["alpha"]), np.asarray(post["beta"])
    fresh = rng.normal(size=(u.shape[0], len(vendor_ix)))
    vendor_u = np.where(vendor_ix >= 0, u[:, np.clip(vendor_ix, 0, None)], fresh)
    return 1 / (1 + np.exp(-(alpha[:, None] + tau[:, None] * beta[:, area_ix] + sigma[:, None] * vendor_u)))


def _log_score(y, n, p) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float((y * np.log(p) + (n - y) * np.log(1 - p)).sum() / n.sum())


def run():
    df = _items()
    h1 = _aggregate(df[df["created_ts"] < SPLIT])
    h2 = _aggregate(df[df["created_ts"] >= SPLIT])

    # Out-of-time validation: three ways of predicting a vendor's second half.
    mcmc, areas, vendors = fit(h1)
    h2 = h2[h2["spend_area"].isin(areas)].copy()
    area_ix = h2["spend_area"].map(areas).to_numpy()
    vendor_ix = h2["vendor_id"].map(vendors).fillna(-1).astype(int).to_numpy()
    bayes_p = _predict_vendor_rate(mcmc.get_samples(), vendors, area_ix, vendor_ix).mean(axis=0)

    overall = h1["y"].sum() / h1["n"].sum()
    raw = h2[["vendor_id", "spend_area"]].merge(h1, how="left", on=["vendor_id", "spend_area"])
    raw_p = (raw["y"] / raw["n"]).fillna(overall).to_numpy()
    y, n = h2["y"].to_numpy(), h2["n"].to_numpy()
    validation = pd.DataFrame([
        {"model": "Hierarchical Bayes", "log_score": _log_score(y, n, bayes_p), "mae_weighted": float(np.average(np.abs(y / n - bayes_p), weights=n))},
        {"model": "Raw vendor rate", "log_score": _log_score(y, n, raw_p), "mae_weighted": float(np.average(np.abs(y / n - raw_p), weights=n))},
        {"model": "Overall rate", "log_score": _log_score(y, n, np.full(len(y), overall)), "mae_weighted": float(np.average(np.abs(y / n - overall), weights=n))},
    ])
    log.info("bayes validation\n%s", validation)

    # Final league table on the full year, with diagnostics.
    agg = _aggregate(df)
    mcmc, areas, vendors = fit(agg, seed=1)
    summary = numpyro.diagnostics.summary(mcmc.get_samples(group_by_chain=True))
    rhat = max(float(np.nanmax(s["r_hat"])) for s in summary.values())
    ess = min(float(np.nanmin(s["n_eff"])) for s in summary.values())
    post = mcmc.get_samples()
    u = np.asarray(post["u"]) * np.asarray(post["sigma"])[:, None]
    typical = float(np.median(1 / (1 + np.exp(-np.asarray(post["alpha"])))))
    # Vendor effect expressed against a vendor of typical quality in the same spend area.
    odds_ratio = np.exp(u)
    inv = {i: v for v, i in vendors.items()}
    totals = df.groupby("vendor_id").agg(n_items=("problem", "size"), n_problems=("problem", "sum")).reset_index()
    table = pd.DataFrame({
        "vendor_id": [inv[i] for i in range(u.shape[1])],
        "odds_multiple": np.median(odds_ratio, axis=0),
        "ci_low": np.quantile(odds_ratio, 0.05, axis=0),
        "ci_high": np.quantile(odds_ratio, 0.95, axis=0),
        "p_problem_vendor": (odds_ratio > TOP).mean(axis=0),
    }).merge(totals, on="vendor_id")
    table["raw_rate"] = table["n_problems"] / table["n_items"]
    table = table.sort_values(["p_problem_vendor", "ci_low"], ascending=False)

    raw_top = set(table.sort_values("raw_rate", ascending=False).head(20)["vendor_id"])
    bayes_top = set(table.head(20)["vendor_id"])
    meta = {"rhat_max": rhat, "ess_min": ess, "typical_rate": typical, "sigma_median": float(np.median(post["sigma"])),
            "n_vendors": int(u.shape[1]), "top20_overlap_with_raw": len(raw_top & bayes_top),
            "median_items_raw_top20": float(table[table["vendor_id"].isin(raw_top)]["n_items"].median()),
            "median_items_bayes_top20": float(table.head(20)["n_items"].median())}
    return validation, table, meta
