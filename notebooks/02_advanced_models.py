# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # 02 — Advanced models, each with a business question and a baseline
#
# The computation lives in `src/p2p/analysis/` and runs with `p2p analyse`. This notebook reads the
# results and explains them. Every model is judged on later data it never saw, against something
# simple a team could use today.

# %%
import json

import duckdb
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd
import seaborn as sns

from p2p import config

con = duckdb.connect(str(config.DB_PATH), read_only=True)
q = lambda sql: con.execute(sql).df()  # noqa: E731
m = json.loads((config.REPORTS / "metrics.json").read_text())

COBALT, AMBER, TEAL, GREY = "#5A6CF0", "#E39B2D", "#2BB39E", "#8A93A3"
sns.set_theme(style="whitegrid", font_scale=0.95)
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlesize": 12})


def save(fig, name):
    fig.savefig(config.FIGURES / f"{name}.png", bbox_inches="tight", dpi=150)


# %% [markdown]
# ## 1. Survival analysis: how long does payment really take?
#
# Averaging paid items ignores everything still unpaid, and those are the slow ones. Survival models
# treat an unpaid item as "at least this long". Deleted items are censored at deletion.

# %%
km = q("select * from analytics.km_curves where day <= 240")
fig, ax = plt.subplots(figsize=(8, 3.8))
for (flow, g), c in zip(km.groupby("flow"), [COBALT, AMBER, TEAL], strict=False):
    ax.plot(g["day"], g["share_unpaid"], color=c, lw=2, label=flow)
ax.yaxis.set_major_formatter(mtick.PercentFormatter(1))
ax.set_xlabel("days since order")
ax.set_title("Share of items still unpaid")
ax.legend(frameon=False)
save(fig, "model_km")

# %%
q("select * from analytics.survival_scores")

# %%
q("select * from analytics.time_ratios where p < 0.01 order by time_ratio desc")

# %% [markdown]
# A time ratio of 1.3 means payment takes 30% longer. These are associations, not causes. Vendor
# history stands out: each extra month in a vendor's past payment time adds about 20%, which fits
# payment terms the log doesn't record. A vendor's history largely stands in for its contract.
#
# ### Cash-out forecast
# Summing each open item's chance of being paid soon gives a cash forecast from the open book.
# Backtest: stand at an earlier date, fit on only what was known then, forecast 30 days.

# %%
q("select as_of, forecast_eur, actual_eur, naive_last_period_eur, open_items from analytics.cash_backtest order by as_of")

# %% [markdown]
# The forecast covers lines already on the book. Lines both ordered and paid inside the window aren't
# in it, and the "actual" column excludes them for the same reason. The naive column is total payments
# in the previous 30 days, so it's a fair baseline but not an identical measure.
#
# ## 2. Causal inference: does rework cause delay?
#
# Changed orders are paid later. Does the change cause that? Three traps need handling:
#
# * **Confounding**: changed orders differ in vendor, value and spend area. Double machine learning
#   adjusts with flexible models, cross-fitted to avoid overfitting bias.
# * **Immortal-time bias**: slow orders have longer to be changed. So the cohort is orders still
#   unpaid at day 14, and treatment means a change inside those 14 days.
# * **Censoring**: the outcome is unpaid days in the next 180, and every order has that follow-up.

# %%
e = q("select * from analytics.causal_effects")
e[["treatment", "n", "treated", "naive_diff_days", "dml_effect_days", "ci_low", "ci_high", "p_value", "placebo_effect_days", "share_trimmed"]]

# %%
q("select segment, n, treated, naive_diff_days, dml_effect_days, ci_low, ci_high from analytics.causal_segments")

# %% [markdown]
# The apparent five-day penalty disappears. The effect of any change is indistinguishable from zero,
# and the interval rules out more than a couple of days, so "stop changing orders" wouldn't speed up
# payment. Packaging is the possible exception, with a small positive effect. Segment results are
# noisier and were not pre-specified, so treat that as a lead. The causal reading still assumes no
# major hidden confounder, as any observational study does.
#
# ## 3. Hierarchical Bayes: which vendors are really a problem?

# %%
pd.DataFrame(m["bayes"]["validation"])

# %%
b = m["bayes"]["meta"]
print(f"max R-hat {b['rhat_max']:.3f}, min ESS {b['ess_min']:.0f}")
print(f"Median lines in the raw top 20: {b['median_items_raw_top20']:.0f}; in the Bayesian top 20: {b['median_items_bayes_top20']:.0f}")
print(f"Vendors shared by both top 20s: {b['top20_overlap_with_raw']}")
q("select vendor_id, n_items, n_problems, raw_rate, odds_multiple, ci_low, ci_high, p_problem_vendor from analytics.vendor_posterior limit 10")

# %% [markdown]
# A raw league table is topped by one-line vendors. Partial pooling predicts each vendor's second half
# better than either raw rates or a single overall rate, and it names vendors with enough volume for a
# conversation to be worthwhile.
#
# ## 4. Conformal prediction: ranges that keep their promise

# %%
pd.DataFrame(m["conformal"]["results"])

# %% [markdown]
# The raw 90% model only covers about 79% of outcomes. Conformal calibration brings it to about 92%
# overall. It isn't perfect: coverage on the small GR-based flow stays near 88%, and a 105-day range
# is honest rather than impressive. The method assumes the future resembles the calibration window,
# and time drift weakens that guarantee, so a deployed version would recalibrate on a rolling window.
#
# ## 5. Sequence model: predicting from events as they happen

# %%
pd.DataFrame(m["sequence"]["results"])

# %% [markdown]
# A two-headed GRU reads the events so far. It beats a second-order Markov chain on the next step and
# the median-by-position baseline on remaining time. The gain is largest mid-process, once the path
# has shown its hand, and small straight after creation, when little is known.
#
# ## 6. From score to decision

# %%
pd.DataFrame([m["alerts"]["metrics"]]).T

# %%
curve = q("select * from analytics.alert_cost_curve")
fig, ax = plt.subplots(figsize=(8, 3.4))
ax.plot(curve["share_reviewed"], curve["net_saving_eur"], color=COBALT, lw=2.2)
ax.axhline(0, color=GREY, lw=1)
ax.xaxis.set_major_formatter(mtick.PercentFormatter(1))
ax.set_xlabel("share of invoices reviewed")
ax.set_title("Net saving of reviewing the top-scored invoices (costs are assumptions)")
save(fig, "model_cost_curve")
m["alerts"]["assumptions"], m["alerts"]["best"]

# %% [markdown]
# A good AUC doesn't mean a model is worth deploying. Reviewing pays only where the chance of catching
# a correction beats review cost ÷ (correction cost × share prevented). With a €10 check the sensible
# review share is a small slice of invoices; at €25 no share pays. Those costs are assumptions, which
# is why the dashboard lets the reader change them.
#
# ### Anomaly detection
# An Isolation Forest never sees the control rules, so its agreement with them is independent
# evidence that it's finding something real.

# %%
pd.DataFrame([m["alerts"]["anomaly"]]).T

# %%
con.close()
