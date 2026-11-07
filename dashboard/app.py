"""Procure-to-Pay Intelligence dashboard.

Reads only the serving-layer parquet files in dashboard/data (written by `p2p export`),
so it runs anywhere without the warehouse:  streamlit run dashboard/app.py
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA = Path(__file__).parent / "data"

# Stratum brand palette (matches stratumdata.org): used as data series, not decoration.
COBALT, AMBER, TEAL, GREY, RED = "#8AA0FF", "#F2B65C", "#58D6C2", "#828D9E", "#E0736B"
SURFACE, LINE, TEXT = "#141A24", "#242E3D", "#C5CDDA"
FLOW_NAMES = {"three_way_before_gr": "3-way, invoice before receipt", "three_way_after_gr": "3-way, invoice after receipt",
              "two_way": "2-way match", "consignment": "Consignment"}

st.set_page_config(page_title="Procure-to-Pay Intelligence · Stratum", page_icon="▪", layout="wide")
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600&family=IBM+Plex+Sans:wght@400;500&family=IBM+Plex+Mono:wght@400;500&display=swap');
    html, body, [class*="css"], .stMarkdown, p, li { font-family: 'IBM Plex Sans', sans-serif; }
    h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; letter-spacing: -0.02em; }
    .eyebrow { font-family: 'IBM Plex Mono', monospace; font-size: 12px; letter-spacing: .14em; text-transform: uppercase; color: #8AA0FF; }
    div[data-testid="stMetric"] { background: #141A24; border: 1px solid #1B232F; border-radius: 12px; padding: 14px 16px; }
    [data-testid="stMetricValue"] { font-size: clamp(1.15rem, 1.7vw, 1.65rem); font-family: 'Space Grotesk', sans-serif; }
    /* Streamlit ellipsises metrics in narrow columns; let them shrink and wrap instead. */
    [data-testid="stMetricValue"] div, [data-testid="stMetricLabel"] div, [data-testid="stMetricLabel"] p,
    [data-testid="stMetricLabel"] div.stMarkdownEllipsis, [data-testid="stMetricLabel"] div.stMarkdownEllipsis p {
        overflow: visible !important; text-overflow: clip !important; white-space: normal !important;
        overflow-wrap: normal !important; word-break: normal !important; }
    [data-testid="stMetricLabel"] p { font-size: 13px; color: #828D9E; }
    .finding { background: #141A24; border: 1px solid #1B232F; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; }
    .finding .q { color: #EEF2F8; font-weight: 500; }
    .block-container { padding-top: 3rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for f in DATA.glob("*.parquet"):
        con.execute(f"create view {f.stem} as select * from read_parquet('{f.as_posix()}')")
    return con


@st.cache_data
def q(sql: str) -> pd.DataFrame:
    return db().execute(sql).df()


@st.cache_data
def load_json(name: str) -> dict:
    return json.loads((DATA / name).read_text())


def style(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        template="plotly_dark", height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "IBM Plex Sans", "color": TEXT, "size": 13}, margin={"l": 10, "r": 10, "t": 40, "b": 10},
        legend={"orientation": "h", "y": -0.2}, hoverlabel={"bgcolor": SURFACE, "font_family": "IBM Plex Mono"},
        title={"font": {"family": "Space Grotesk", "size": 16}},
    )
    fig.update_xaxes(gridcolor=LINE, zeroline=False)
    fig.update_yaxes(gridcolor=LINE, zeroline=False)
    return fig


def eur(x: float) -> str:
    return f"€{x/1e6:,.1f}m" if abs(x) >= 1e6 else f"€{x/1e3:,.0f}k" if abs(x) >= 1e4 else f"€{x:,.0f}"


m = load_json("metrics.json")
k = load_json("kpis.json")
dbt = load_json("dbt_summary.json")
comp = m["compliance"]["overall"]
cash = {r["horizon_days"]: r["expected_cash_out_eur"] for r in m["survival"]["cash_forecast"]}
any_change = m["causal"]["effects"][0]
sod_lines = next(r["n_items"] for r in m["compliance"]["rules"] if r["rule"] == "r06_segregation_of_duties")
_bt = pd.DataFrame(m["survival"]["backtest"])
backtest_err = float(((_bt["forecast_eur"] - _bt["actual_eur"]).abs() / _bt["actual_eur"]).mean())

st.markdown('<span class="eyebrow">Stratum · case study</span>', unsafe_allow_html=True)
st.title("Procure-to-Pay Intelligence")
st.caption(f"Real purchase-order event log from a multinational paints and coatings group, 2018 · {k['n_events']:,.0f} ERP events on "
           f"{k['n_items']:,.0f} order lines → process mining → compliance controls → advanced models. Vendors and users are anonymised.")

tabs = st.tabs(["Overview", "Process", "Compliance", "Work queue", "Payment timing", "Vendors", "Does rework matter?", "Alerts", "Data pipeline"])

# ---------------------------------------------------------------- overview
with tabs[0]:
    c = st.columns(5)
    c[0].metric("Order value", eur(k["order_value_eur"]))
    c[1].metric("Order lines", f"{k['n_items']:,.0f}")
    c[2].metric("Vendors", f"{k['n_vendors']:,.0f}")
    km_days = m["survival"]["median_days"]["three_way_before_gr"]
    c[3].metric("Median days to pay", f"{km_days:.0f}", f"{k['median_days_paid_only']:.0f} paid only", delta_color="off")
    c[4].metric("Value with a control exception", eur(comp["value_flagged"]), f"{comp['n_flagged'] / comp['n_items']:.1%} of lines", delta_color="off")

    st.subheader("What the analysis found")
    findings = [
        ("Reworked orders aren't what makes payment slow.",
         f"They look {any_change['naive_diff_days']:.1f} days slower, but once comparable orders are matched the effect is "
         f"{any_change['dml_effect_days']:+.1f} days (95% CI {any_change['ci_low']:+.1f} to {any_change['ci_high']:+.1f}). The queue after the invoice is booked is where the time goes."),
        ("Ignoring unpaid items understates payment time.",
         f"Paid items alone give a median of {k['median_days_paid_only']:.0f} days; counting items still open gives {km_days:.0f} days for the main flow."),
        ("Some controls hold perfectly; others leak.",
         f"No invoice on GR-based items came before its receipt. Yet {sod_lines:,} lines had one person on both sides of a control."),
        ("Near-term cash-out can be forecast from the open book.",
         f"About {eur(cash[30])} is expected to be paid in the next 30 days. Across three backtests the average miss was {backtest_err:.1%}."),
    ]
    for head, body in findings:
        st.markdown(f'<div class="finding"><div class="q">{head}</div><div style="margin-top:6px">{body}</div></div>', unsafe_allow_html=True)

    a, b = st.columns([1.2, 1])
    with a:
        mk = q("select year_month, sum(order_value_eur) value, sum(n_items) items from mart_monthly_kpis where year_month < '2019-01' group by 1 order by 1")
        fig = px.bar(mk, x="year_month", y="value", title="Order value by month", color_discrete_sequence=[COBALT])
        fig.update_yaxes(title=None, tickprefix="€")
        fig.update_xaxes(title=None)
        st.plotly_chart(style(fig), use_container_width=True)
    with b:
        fl = q("select flow, sum(n_items) items from mart_monthly_kpis group by 1 order by 2 desc")
        fl["flow"] = fl["flow"].map(FLOW_NAMES)
        fig = px.bar(fl.iloc[::-1], x="items", y="flow", orientation="h", log_x=True, title="Order lines by matching flow (log scale)",
                     color_discrete_sequence=[TEAL])
        fig.update_xaxes(title=None)
        fig.update_yaxes(title=None)
        st.plotly_chart(style(fig), use_container_width=True)

# ---------------------------------------------------------------- process
with tabs[1]:
    st.subheader("What actually happens")
    flow = st.selectbox("Matching flow", list(FLOW_NAMES), format_func=FLOW_NAMES.get)
    vs = q("select * from variant_summary")
    v = vs[vs["flow"] == flow].iloc[0]
    st_row = q("select * from straight_through")
    sr = st_row[st_row["flow"] == flow]
    conf = pd.DataFrame(m.get("conformance", []))
    cf = conf[conf["flow"] == flow] if len(conf) else conf
    c = st.columns(4)
    c[0].metric("Distinct paths", f"{v['n_variants']:,.0f}")
    c[1].metric("Top 10 paths cover", f"{v['top10_share']:.0%}")
    c[2].metric("Straight-through rate", f"{sr['straight_through_rate'].iloc[0]:.0%}" if len(sr) else "n/a", help="Paid with no rework, one invoice and one payment")
    c[3].metric("Model fitness / precision", f"{cf['fitness'].iloc[0]:.2f} / {cf['precision'].iloc[0]:.2f}" if len(cf) else "n/a", help="Inductive miner on the frequent paths, replayed on a sample of all behaviour")

    edges = q(f"select * from process_edges where flow = '{flow}' order by n_transitions desc limit 22")
    nodes = list(pd.unique(edges[["source_activity", "target_activity"]].values.ravel()))
    ix = {n: i for i, n in enumerate(nodes)}
    # Sankey needs an acyclic picture: backward arcs are dropped from the drawing, not from the numbers.
    order = q("select activity from dim_activity order by n_events desc")["activity"].tolist()
    seen, keep = set(), []
    for _, e in edges.iterrows():
        if (e["target_activity"], e["source_activity"]) not in seen and e["source_activity"] != e["target_activity"]:
            keep.append(e)
            seen.add((e["source_activity"], e["target_activity"]))
    ke = pd.DataFrame(keep)
    fig = go.Figure(go.Sankey(
        node={"label": nodes, "pad": 14, "thickness": 12, "color": COBALT, "line": {"width": 0}},
        link={"source": ke["source_activity"].map(ix), "target": ke["target_activity"].map(ix), "value": ke["n_transitions"],
              "color": "rgba(138,160,255,0.22)", "customdata": ke["median_days"],
              "hovertemplate": "%{source.label} → %{target.label}<br>%{value:,.0f} transitions<br>median %{customdata:.1f} days<extra></extra>"},
    ))
    fig.update_layout(title="Most common steps through this flow")
    st.plotly_chart(style(fig, 460), use_container_width=True)

    a, b = st.columns(2)
    with a:
        bn = q("select * from bottlenecks order by item_days desc limit 8")
        bn["step"] = bn["source_activity"] + " → " + bn["target_activity"]
        fig = px.bar(bn.iloc[::-1], x="item_days", y="step", orientation="h", custom_data=["median_days", "n_transitions"],
                     title="Where the waiting time goes (main flow)", color_discrete_sequence=[AMBER])
        fig.update_traces(hovertemplate="%{y}<br>%{x:,.0f} item-days<br>median %{customdata[0]:.1f} days · %{customdata[1]:,} transitions<extra></extra>")
        fig.update_xaxes(title=None)
        fig.update_yaxes(title=None)
        st.plotly_chart(style(fig, 400), use_container_width=True)
    with b:
        au = q("select * from automation order by n_events desc limit 10")
        long = au.melt(id_vars="activity", value_vars=["human_share", "batch_share", "external_share"], var_name="who", value_name="share")
        long["who"] = long["who"].map({"human_share": "Person", "batch_share": "Batch job", "external_share": "Vendor / external"})
        fig = px.bar(long, x="share", y="activity", color="who", orientation="h", title="Who does the work", barmode="stack",
                     color_discrete_map={"Person": AMBER, "Batch job": TEAL, "Vendor / external": GREY},
                     category_orders={"activity": au["activity"].tolist()})
        fig.update_xaxes(tickformat=".0%", title=None)
        fig.update_yaxes(title=None)
        st.plotly_chart(style(fig, 400), use_container_width=True)

# ---------------------------------------------------------------- compliance
with tabs[2]:
    st.subheader("Control testing across every order line")
    st.caption("An exception is an indicator to review, not proof of wrongdoing. Three-way matching is tested on document counts, "
               "because the source's value field carries the item's cumulative net worth on every event.")
    rules = q("select * from rule_summary order by value_at_risk_eur desc nulls last")
    c = st.columns(4)
    c[0].metric("Lines with an exception", f"{comp['n_flagged']:,.0f}", f"{comp['n_flagged'] / comp['n_items']:.1%}", delta_color="off")
    c[1].metric("Order value behind them", eur(comp["value_flagged"]))
    c[2].metric("Lines with 2+ exceptions", f"{comp['n_multi']:,.0f}")
    c[3].metric("Controls with zero exceptions", f"{(rules['n_items'] == 0).sum()} of {len(rules)}")
    r = rules[rules["n_items"] > 0].iloc[::-1]
    fig = px.bar(r, x="value_at_risk_eur", y="label", orientation="h", custom_data=["n_items", "n_vendors", "definition"],
                 title="Order value behind each exception", color_discrete_sequence=[AMBER])
    fig.update_traces(hovertemplate="<b>%{y}</b><br>%{customdata[2]}<br>€%{x:,.0f} · %{customdata[0]:,} lines · %{customdata[1]:,} vendors<extra></extra>")
    fig.update_xaxes(title=None, tickprefix="€")
    fig.update_yaxes(title=None)
    st.plotly_chart(style(fig, 380), use_container_width=True)
    a, b = st.columns(2)
    with a:
        st.markdown("**Controls that held**")
        ok = rules[rules["n_items"] == 0][["label", "definition"]]
        st.dataframe(ok, hide_index=True, use_container_width=True)
        st.markdown("**Exception rate by spend area**")
        st.dataframe(q("select * from compliance_by_area order by value_flagged desc nulls last limit 8"), hide_index=True, use_container_width=True,
                     column_config={"spend_area": "Spend area", "n_items": st.column_config.NumberColumn("Lines", format="%d"),
                                    "flag_rate": st.column_config.NumberColumn("Exception rate", format="percent"),
                                    "value_flagged": st.column_config.NumberColumn("Value", format="€%,.0f")})
    with b:
        st.markdown("**People most often on both sides of a control**")
        st.dataframe(q("select * from sod_users order by n_items desc limit 12"), hide_index=True, use_container_width=True,
                     column_config={"user_id": "User", "n_items": st.column_config.NumberColumn("Lines", format="%d"),
                                    "value_eur": st.column_config.NumberColumn("Order value", format="€%,.0f")})

# ---------------------------------------------------------------- work queue
with tabs[3]:
    st.subheader("What should a controller look at first?")
    st.caption("Open lines ranked by combining control exceptions, vendor risk, an unusual path and age, with order value setting the order inside a risk level.")
    wq = q("select * from work_queue order by priority desc")
    a, b, c_ = st.columns([1, 1, 1])
    areas = a.multiselect("Spend area", sorted(wq["spend_area"].unique()), placeholder="All areas")
    minv = b.number_input("Minimum order value (€)", 0, 1_000_000, 0, 1000)
    n = c_.slider("Lines to show", 10, 200, 40, 10)
    view = wq[wq["order_value_eur"] >= minv]
    if areas:
        view = view[view["spend_area"].isin(areas)]
    c = st.columns(3)
    c[0].metric("Lines in queue", f"{len(view):,}")
    c[1].metric("Order value", eur(view["order_value_eur"].sum()))
    c[2].metric("Expected paid in 30 days", eur((view["order_value_eur"] * view["p_paid_30d"]).sum()))
    show = view.head(n).drop(columns=["priority"])
    st.dataframe(show, hide_index=True, use_container_width=True, height=460,
                 column_config={"item_id": "Line", "vendor_id": "Vendor", "flow": None, "spend_area": "Spend area",
                                "order_value_eur": st.column_config.NumberColumn("Value", format="€%,.0f"),
                                "age_days": st.column_config.NumberColumn("Age (days)", format="%d"),
                                "risk": st.column_config.ProgressColumn("Risk", min_value=0, max_value=3, format="%.1f"),
                                "p_paid_30d": st.column_config.NumberColumn("P(paid in 30d)", format="percent"),
                                "reasons": st.column_config.TextColumn("Why it's here", width="large")})
    st.download_button("Download this queue (CSV)", view.to_csv(index=False), "p2p_work_queue.csv", "text/csv")

# ---------------------------------------------------------------- payment timing
with tabs[4]:
    st.subheader("How long will payment take?")
    sc = pd.DataFrame(m["survival"]["scores"])
    c = st.columns(3)
    best = sc.dropna(subset=["aic"]).sort_values("concordance").iloc[-1]
    c[0].metric("Ranking accuracy (concordance)", f"{best['concordance']:.2f}", f"vs {sc.iloc[-1]['concordance']:.2f} for flow median", delta_color="off", help="Log-logistic AFT ranks items best. Cash forecasts use the Weibull AFT, chosen separately on a held-out date.")
    c[1].metric("Expected cash-out, 30 days", eur(cash[30]))
    c[2].metric("Expected cash-out, 90 days", eur(cash[90]))
    a, b = st.columns(2)
    with a:
        km = q("select * from km_curves where day <= 240")
        km["flow"] = km["flow"].map(FLOW_NAMES)
        fig = px.line(km, x="day", y="share_unpaid", color="flow", title="Share of items still unpaid (Kaplan-Meier)",
                      color_discrete_sequence=[COBALT, AMBER, TEAL])
        fig.update_yaxes(tickformat=".0%", title=None)
        fig.update_xaxes(title="days since order")
        st.plotly_chart(style(fig, 380), use_container_width=True)
    with b:
        tr = q("select * from time_ratios where p < 0.01 order by time_ratio")
        tr = pd.concat([tr.head(6), tr.tail(6)])
        tr["covariate"] = (tr["covariate"].str.replace(r"^(flow|item_type|spend_area|spend_class|document_type)_", "", regex=True)
                           .str.replace("vendor_prior_days", "Vendor's past payment time").str.replace("vendor_prior_rework", "Vendor's past rework rate")
                           .str.replace("two_way", "2-way flow").str.replace("_", " "))
        fig = go.Figure(go.Scatter(x=tr["time_ratio"], y=tr["covariate"], mode="markers", marker={"color": COBALT, "size": 9},
                                   error_x={"type": "data", "symmetric": False, "array": tr["ci_high"] - tr["time_ratio"], "arrayminus": tr["time_ratio"] - tr["ci_low"], "color": GREY}))
        fig.add_vline(x=1, line_color=AMBER)
        fig.update_layout(title="What speeds up or slows down payment (time ratio)")
        fig.update_xaxes(type="log")
        st.plotly_chart(style(fig, 380), use_container_width=True)

    st.markdown("#### Cash-out forecast backtest")
    bt = q("select * from cash_backtest order by as_of")
    long = bt.melt(id_vars="as_of", value_vars=["forecast_eur", "actual_eur", "naive_last_period_eur"], var_name="series", value_name="eur_value")
    long["series"] = long["series"].map({"forecast_eur": "Survival forecast", "actual_eur": "Actually paid", "naive_last_period_eur": "Last 30 days repeated"})
    fig = px.bar(long, x="as_of", y="eur_value", color="series", barmode="group", title="Next 30 days of payments, forecast from each date using only data known then",
                 color_discrete_map={"Survival forecast": COBALT, "Actually paid": TEXT, "Last 30 days repeated": GREY})
    fig.update_yaxes(tickprefix="€", title=None)
    fig.update_xaxes(title=None, type="category")
    st.plotly_chart(style(fig, 340), use_container_width=True)

    st.markdown("#### Payment ranges that keep their promise")
    cr = pd.DataFrame(m["conformal"]["results"])
    a, b = st.columns([1, 1.3])
    with a:
        st.caption(f"Target: {m['conformal']['meta']['target_coverage']:.0%} of actual payment times inside the range, on later items the model never saw.")
        st.dataframe(cr.rename(columns=lambda s: s.replace("coverage_", "")), hide_index=True, use_container_width=True,
                     column_config={"method": "Method", "coverage": st.column_config.NumberColumn("Coverage", format="percent"),
                                    "avg_width_days": st.column_config.NumberColumn("Width (days)", format="%.0f"),
                                    "three_way_after_gr": st.column_config.NumberColumn("Invoice after receipt", format="percent"),
                                    "three_way_before_gr": st.column_config.NumberColumn("Invoice before receipt", format="percent")})
    with b:
        s = q("select * from conformal_sample order by y").reset_index(drop=True)
        s["i"] = s.index
        fig = go.Figure()
        fig.add_scatter(x=s["i"], y=s["upper"], mode="lines", line={"width": 0}, showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=s["i"], y=s["lower"], mode="lines", line={"width": 0}, fill="tonexty", fillcolor="rgba(138,160,255,0.22)", name="90% range")
        fig.add_scatter(x=s["i"], y=s["y"], mode="markers", marker={"size": 3, "color": AMBER}, name="actual days")
        fig.update_layout(title="400 test items, sorted by actual days")
        fig.update_xaxes(showticklabels=False, title=None)
        st.plotly_chart(style(fig, 340), use_container_width=True)

    if "sequence" in m:
        st.markdown("#### Live prediction after every event (GRU vs process baselines)")
        sq = pd.DataFrame(m["sequence"]["results"])
        st.dataframe(sq, hide_index=True, use_container_width=True,
                     column_config={"scope": "Scope", "prefixes": st.column_config.NumberColumn("Predictions", format="%d"),
                                    "next_acc_gru": st.column_config.NumberColumn("Next step, GRU", format="percent"),
                                    "next_acc_markov": st.column_config.NumberColumn("Next step, Markov", format="percent"),
                                    "next_top3_gru": st.column_config.NumberColumn("In GRU top 3", format="percent"),
                                    "rem_mae_gru": st.column_config.NumberColumn("Days error, GRU", format="%.1f"),
                                    "rem_mae_baseline": st.column_config.NumberColumn("Days error, baseline", format="%.1f")})

# ---------------------------------------------------------------- vendors
with tabs[5]:
    st.subheader("Which vendors are really a problem?")
    bm = m["bayes"]["meta"]
    st.caption("Raw rates crown tiny vendors. A hierarchical Bayesian model shrinks small samples towards the norm, so a vendor only ranks highly on real evidence.")
    val = pd.DataFrame(m["bayes"]["validation"])
    c = st.columns(4)
    c[0].metric("Typical correction rate", f"{bm['typical_rate']:.1%}")
    c[1].metric("Top 20 shared with raw ranking", f"{bm['top20_overlap_with_raw']} of 20")
    c[2].metric("Median lines, raw top 20", f"{bm['median_items_raw_top20']:.0f}")
    c[3].metric("Median lines, Bayesian top 20", f"{bm['median_items_bayes_top20']:.0f}")
    vp = q("select * from vendor_posterior")
    a, b = st.columns([1.2, 1])
    with a:
        top = vp.head(20).iloc[::-1]
        fig = go.Figure(go.Scatter(x=top["odds_multiple"], y=top["vendor_id"], mode="markers", marker={"color": AMBER, "size": 9},
                                   error_x={"type": "data", "symmetric": False, "array": top["ci_high"] - top["odds_multiple"], "arrayminus": top["odds_multiple"] - top["ci_low"], "color": GREY}))
        fig.update_layout(title="Top 20 vendors: correction odds vs typical (90% interval)")
        fig.update_xaxes(type="log", title=None)
        st.plotly_chart(style(fig, 520), use_container_width=True)
    with b:
        st.markdown("**Does shrinkage predict better?** Fit on H1, scored on each vendor's H2.")
        st.dataframe(val, hide_index=True, use_container_width=True,
                     column_config={"model": "Model", "log_score": st.column_config.NumberColumn("Log score (higher is better)", format="%.3f"),
                                    "mae_weighted": st.column_config.NumberColumn("Weighted error", format="%.3f")})
        pick = st.selectbox("Look up a vendor", vp["vendor_id"].head(200))
        r = vp[vp["vendor_id"] == pick].iloc[0]
        st.markdown(f"**{pick}**: {r['n_problems']:,.0f} corrected of {r['n_items']:,.0f} lines ({r['raw_rate']:.0%}). "
                    f"Odds {r['odds_multiple']:.1f}× typical (90% interval {r['ci_low']:.1f} to {r['ci_high']:.1f}). "
                    f"P(at least 3× typical) = {r['p_problem_vendor']:.0%}.")

# ---------------------------------------------------------------- causal
with tabs[6]:
    st.subheader("Does rework cause late payment?")
    st.markdown("Orders that get changed are paid later, so the obvious fix is to stop changing orders. But changed orders also differ in vendor, value and spend area. "
                "**Double machine learning** adjusts for those differences on a landmark cohort, so slow items can't look worse just by having more time to be changed.")
    eff = pd.DataFrame(m["causal"]["effects"])
    labels = {"any_change": "Any price or quantity change", "price_change": "Price change", "quantity_change": "Quantity change", "any_change, excluding later deletions": "Any change, excl. later deletions"}
    eff["label"] = eff["treatment"].map(labels)
    fig = go.Figure()
    fig.add_scatter(x=eff["naive_diff_days"], y=eff["label"], mode="markers", name="Naive difference", marker={"color": GREY, "size": 11, "symbol": "diamond"})
    fig.add_scatter(x=eff["dml_effect_days"], y=eff["label"], mode="markers", name="Adjusted effect (95% CI)", marker={"color": COBALT, "size": 11},
                    error_x={"type": "data", "symmetric": False, "array": eff["ci_high"] - eff["dml_effect_days"], "arrayminus": eff["dml_effect_days"] - eff["ci_low"], "color": COBALT})
    fig.add_vline(x=0, line_color=AMBER)
    fig.update_layout(title="Extra unpaid days in the 180 days after day 14")
    fig.update_xaxes(title="days")
    st.plotly_chart(style(fig, 340), use_container_width=True)
    a, b = st.columns(2)
    with a:
        seg = pd.DataFrame(m["causal"]["segments"])
        fig = go.Figure(go.Scatter(x=seg["dml_effect_days"], y=seg["segment"], mode="markers", marker={"color": TEAL, "size": 10},
                                   error_x={"type": "data", "symmetric": False, "array": seg["ci_high"] - seg["dml_effect_days"], "arrayminus": seg["dml_effect_days"] - seg["ci_low"], "color": GREY}))
        fig.add_vline(x=0, line_color=AMBER)
        fig.update_layout(title="Adjusted effect by spend area")
        st.plotly_chart(style(fig, 300), use_container_width=True)
    with b:
        st.markdown("**How this was checked**")
        st.markdown(f"- Cohort: {any_change['n']:,} lines, {any_change['treated']:,} changed\n"
                    f"- Shuffled-treatment placebo: {any_change['placebo_effect_days']:+.2f} days\n"
                    f"- Cross-fitted by document, standard errors clustered by document\n"
                    f"- Overlap trimming removed {any_change['share_trimmed']:.0%} of lines\n"
                    "- A causal claim still rests on no important hidden confounder, so read this as strong evidence, not proof.")

# ---------------------------------------------------------------- alerts
with tabs[7]:
    st.subheader("Is a review worth its cost?")
    am = m["alerts"]["metrics"]
    c = st.columns(4)
    c[0].metric("Correction rate", f"{am['base_rate']:.1%}")
    c[1].metric("ROC-AUC", f"{am['roc_auc']:.2f}")
    c[2].metric("Precision, top 10%", f"{am['precision_top10pct']:.0%}", f"{am['lift_top10pct']:.1f}× base rate", delta_color="off")
    c[3].metric("Corrections in top 10%", f"{am['recall_top10pct']:.0%}")
    st.caption("When an invoice is booked, the model scores how likely it is to need correcting. The costs below are assumptions, not data: set them to your own numbers. "
               "A review pays only when its chance of catching a correction beats review cost ÷ (correction cost × share prevented).")
    a, b, c_ = st.columns(3)
    rc = a.slider("Cost of one review (€)", 5, 100, int(m["alerts"]["assumptions"]["review_cost_eur"]), 5)
    cc = b.slider("Cost of one correction (€)", 50, 500, int(m["alerts"]["assumptions"]["correction_cost_eur"]), 10)
    sp = c_.slider("Share of corrections a review prevents", 0.1, 1.0, float(m["alerts"]["assumptions"]["share_preventable"]), 0.05)
    # Calibrated scores tie, so the curve moves one score level at a time, as in the analysis code.
    lv = q("select p_correction, count(*) n, sum(corrected) hits from alert_scored group by 1 order by 1 desc")
    idx, hits = lv["n"].cumsum().to_numpy(), lv["hits"].cumsum().to_numpy()
    total = int(idx[-1])
    saving = hits * cc * sp - idx * rc
    best_i = int(saving.argmax())
    fig = go.Figure(go.Scatter(x=idx / total, y=saving, mode="lines", line={"color": COBALT, "width": 2.5}))
    fig.add_vline(x=idx[best_i] / total, line_color=AMBER)
    fig.update_layout(title="Net saving by share of invoices reviewed (test period)")
    fig.update_xaxes(tickformat=".0%", title="share of invoices reviewed")
    fig.update_yaxes(tickprefix="€", title=None)
    st.plotly_chart(style(fig, 340), use_container_width=True)
    c = st.columns(3)
    c[0].metric("Best review share", f"{idx[best_i] / total:.1%}")
    c[1].metric("Invoices to review", f"{int(idx[best_i]):,}")
    c[2].metric("Net saving", eur(max(float(saving[best_i]), 0)))

# ---------------------------------------------------------------- pipeline
with tabs[8]:
    st.subheader("How the data gets here")
    st.graphviz_chart(
        """
        digraph {
          rankdir=LR; bgcolor="transparent";
          node [shape=box style="rounded,filled" fillcolor="#141A24" color="#242E3D" fontcolor="#EEF2F8" fontname="Helvetica" fontsize=11];
          edge [color="#828D9E"];
          src [label="Event log\\n(XES, 730 MB)"];
          bronze [label="Bronze parquet\\nchecksummed, stream-parsed"];
          dbt [label="dbt on DuckDB\\nstaging, intermediate, marts"];
          tests [label="dbt tests\\nkeys, reconciliation, rule unit test" fillcolor="#2A2418" color="#F2B65C"];
          mine [label="Process mining\\nand compliance"];
          ml [label="Survival · causal · Bayesian\\nconformal · GRU · alerts"];
          serve [label="Serving layer"];
          app [label="This dashboard" fillcolor="#1D2546" color="#8AA0FF"];
          src -> bronze; bronze -> dbt; dbt -> tests; dbt -> mine; dbt -> ml; mine -> serve; ml -> serve; serve -> app;
        }
        """
    )
    c = st.columns(3)
    c[0].metric("dbt models", dbt["models"])
    c[1].metric("dbt tests passing", f"{dbt['tests_passed']} of {dbt['tests']}")
    c[2].metric("Events reconciled", f"{k['n_events']:,.0f}")
    st.markdown("**A data finding worth knowing:** the source field *Cumulative net worth* repeats the line's running value on every event. "
                "Summing it across events gives about €5.7B on a €997M order book, so document amounts can't be recovered from it. "
                "This project uses it only as order value, and tests three-way matching on document counts.")
