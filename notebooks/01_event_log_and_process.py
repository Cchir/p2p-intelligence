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
# # 01 — The event log, the process and its controls
#
# **Source:** [BPI Challenge 2019](https://doi.org/10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1)
# (van Dongen, 4TU.ResearchData, CC BY 4.0): the purchase-order handling of a multinational coatings
# and paints company, as recorded by its ERP. Vendors and users are anonymised.
#
# **Goal:** learn how the log really behaves before modelling it. Each surprise below changed a
# design decision later on. One of them, the value field, would have produced badly wrong numbers.

# %%
import duckdb
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd
import seaborn as sns

from p2p import config

con = duckdb.connect(str(config.DB_PATH), read_only=True)
q = lambda sql: con.execute(sql).df()  # noqa: E731

COBALT, AMBER, TEAL, GREY = "#5A6CF0", "#E39B2D", "#2BB39E", "#8A93A3"
sns.set_theme(style="whitegrid", font_scale=0.95)
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlesize": 12})
pd.set_option("display.max_colwidth", 90)


def save(fig, name):
    fig.savefig(config.FIGURES / f"{name}.png", bbox_inches="tight", dpi=150)


# %% [markdown]
# ## 1. Shape of the log
# Each purchase order line is a *case*, and each case is a sequence of timestamped ERP events.

# %%
q("""select count(*) lines, count(distinct document_id) documents, count(distinct vendor_id) vendors,
            count(distinct company_id) companies, sum(n_events) events, sum(order_value_eur) order_value_eur
     from fct_po_items""")

# %%
q("""select item_category, flow, count(*) lines, sum(order_value_eur) order_value_eur, avg(n_events) avg_events
     from fct_po_items group by 1, 2 order by lines desc""")

# %% [markdown]
# Four matching flows, each with its own rules, so one conformance model can't describe all of
# them. One company holds nearly every line, so "company" is not a useful feature.

# %%
d = q("""select process_stage, sum(n_events) events from dim_activity group by 1 order by 2""")
fig, ax = plt.subplots(figsize=(8, 3))
ax.barh(d["process_stage"], d["events"], color=COBALT)
ax.set_title("Events by process stage")
ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v/1e3:,.0f}k"))
save(fig, "eda_events_by_stage")

# %% [markdown]
# ## 2. Surprises, and what each one changed
#
# **Timestamps.** A few events are dated as far back as 1948, and activity stops abruptly on
# 18 January 2019. Implausible dates are flagged rather than deleted, and 18 January becomes the
# censoring date: items open then have an unknown end, not a missing one.

# %%
q("""select strftime(event_ts, '%Y-%m') as year_month, count(*) events, avg(is_valid_ts::int) valid_share
     from fct_item_events where event_ts >= date '2018-11-01' group by 1 order by 1""")

# %% [markdown]
# **"Duplicates" that aren't.** 132,748 events look like exact duplicates, but nine in ten are
# service entry sheets posted in bulk within the same minute. Deleting them would remove real work,
# so they stay.
#
# **The value field is not what its name suggests.** This is the finding that mattered most.
# `Cumulative net worth (EUR)` is the line's running value, repeated on every event.

# %%
q("""select activity, event_ts, net_value_eur from fct_item_events
     where item_id = (select item_id from fct_po_items
                      where n_clears = 3 and n_goods_receipts = 3 and item_type = 'Standard' and order_value_eur > 0
                      order by item_id limit 1)
     order by event_no""")

# %% [markdown]
# Three receipts and three payments, all carrying the same figure, so these are not document
# amounts. A first version summed them and reported about €5.7B of goods and invoices against a
# €997M order book. **Value-based three-way matching is therefore not possible on this data.** The
# rules test document *counts* instead, and exposure is always the order value.

# %% [markdown]
# ## 3. How orderly is the process?

# %%
q("select * from analytics.variant_summary")

# %%
q("select * from analytics.straight_through")

# %% [markdown]
# There are about 12,000 distinct paths. The main flow is fairly disciplined: its ten commonest paths
# cover 62% of lines. The GR-based flow is far looser, which also shows in conformance below.

# %%
q("select * from analytics.conformance")

# %% [markdown]
# Process models were discovered with the inductive miner from frequent paths, then replayed on a
# sample. **Fitness** asks whether the model can reproduce what happened, and **precision** whether it
# avoids allowing things that never happen. The GR-based flow scores markedly lower on both.

# %%
b = q("select * from analytics.bottlenecks order by item_days desc limit 8")
b["step"] = b["source_activity"] + " → " + b["target_activity"]
fig, ax = plt.subplots(figsize=(9, 3.8))
ax.barh(b["step"][::-1], b["item_days"][::-1] / 1e6, color=AMBER)
ax.set_xlabel("million item-days")
ax.set_title("Where the waiting happens in the main flow")
save(fig, "process_bottlenecks")

# %% [markdown]
# Waiting concentrates after the invoice is booked: *Record Invoice Receipt → Clear Invoice* alone
# carries over three times the item-days of any other step. Much of this may simply be payment terms,
# which the log doesn't contain, so it's a question to take to the business rather than a verdict.

# %% [markdown]
# ## 4. Control testing

# %%
r = q("select label, definition, n_items, rate, value_at_risk_eur, n_open, n_vendors from analytics.rule_summary order by value_at_risk_eur desc nulls last")
r

# %%
s = r[r["n_items"] > 0].iloc[::-1]
fig, ax = plt.subplots(figsize=(9, 3.6))
ax.barh(s["label"], s["value_at_risk_eur"] / 1e6, color=AMBER)
ax.set_xlabel("order value behind the exception (EUR million)")
ax.set_title("Control exceptions by exposure")
save(fig, "compliance_exposure")

# %% [markdown]
# * **Three controls recorded no exceptions**, including the GR-based block on invoices before
#   receipt. That looks system-enforced, which is worth saying as plainly as the failures.
# * **Goods receivers and payers are fully separate**: no user appears in both roles at all.
#   So segregation of duties is tested on two other conflicts, ordering and receiving, and booking
#   and paying.
# * An exception is an indicator to review, not evidence of wrongdoing. Service items, for example,
#   legitimately post many entries, which is why they're excluded from the receipt-count test.

# %%
con.close()
