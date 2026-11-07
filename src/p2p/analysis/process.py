"""Process mining: what really happens between ordering and paying.

Discovers a Petri net per flow with the inductive miner (pm4py) from the variants covering 80% of
items, then scores it on the full behaviour: fitness (can the model replay what happened?) and
precision (does the model allow much that never happens?). Also measures how orderly the process
is: variant concentration, straight-through rate, automation by activity and bottlenecks.
"""

from __future__ import annotations

import logging

import pandas as pd
import pm4py

from p2p.analysis.common import query

log = logging.getLogger(__name__)
SAMPLE_CASES = 3000


def _flow_log(flow: str) -> pd.DataFrame:
    return query(
        f"""
        select e.item_id as "case:concept:name", e.activity as "concept:name", e.event_ts as "time:timestamp"
        from fct_item_events e
        join fct_po_items i using (item_id)
        where i.flow = '{flow}'
        order by e.item_id, e.event_no
        """
    )


def conformance() -> pd.DataFrame:
    rows = []
    for flow in ["three_way_before_gr", "three_way_after_gr", "two_way", "consignment"]:
        df = _flow_log(flow)
        cases = df["case:concept:name"].drop_duplicates()
        sample = cases.sample(min(SAMPLE_CASES, len(cases)), random_state=42)
        sub = df[df["case:concept:name"].isin(sample)]
        frequent = pm4py.filter_variants_by_coverage_percentage(sub, 0.01)
        net, im, fm = pm4py.discover_petri_net_inductive(frequent, noise_threshold=0.2)
        fit = pm4py.fitness_token_based_replay(sub, net, im, fm)
        precision = pm4py.precision_token_based_replay(sub, net, im, fm)
        rows.append({
            "flow": flow, "cases_sampled": len(sample), "fitness": fit["log_fitness"],
            "fitting_cases_pct": fit["percentage_of_fitting_traces"] / 100, "precision": precision,
            "places": len(net.places), "transitions": len(net.transitions),
        })
        log.info("conformance %s: fitness %.3f precision %.3f", flow, fit["log_fitness"], precision)
    return pd.DataFrame(rows)


def variant_summary() -> pd.DataFrame:
    return query(
        """
        with r as (
            select flow, n_items, sum(n_items) over (partition by flow) as flow_items,
                   row_number() over (partition by flow order by n_items desc) as rnk,
                   count(*) over (partition by flow) as n_variants
            from mart_variants
        )
        select flow, any_value(n_variants) as n_variants, any_value(flow_items) as n_items,
               sum(n_items) filter (rnk = 1) * 1.0 / any_value(flow_items) as top1_share,
               sum(n_items) filter (rnk <= 10) * 1.0 / any_value(flow_items) as top10_share,
               count(*) filter (n_items = 1) as singleton_variants
        from r group by flow order by n_items desc
        """
    )


def top_variants(n: int = 25) -> pd.DataFrame:
    return query(
        f"""
        select flow, variant, n_items, order_value_eur, median_days_to_clear, avg_rework
        from mart_variants qualify row_number() over (partition by flow order by n_items desc) <= {n}
        order by flow, n_items desc
        """
    )


def straight_through() -> pd.DataFrame:
    """Share of paid items that needed no human correction: the process running as designed."""
    return query(
        """
        select flow, count(*) as n_paid,
               avg((n_rework_events = 0)::int) as no_rework_rate,
               avg((n_rework_events = 0 and n_invoices = 1 and n_clears = 1)::int) as straight_through_rate,
               median(days_create_to_clear) filter (n_rework_events = 0) as median_days_clean,
               median(days_create_to_clear) filter (n_rework_events > 0) as median_days_rework
        from fct_po_items where status = 'paid' group by flow order by n_paid desc
        """
    )


def automation() -> pd.DataFrame:
    return query(
        """
        select e.activity, a.process_stage, count(*) as n_events,
               avg((e.user_type = 'batch')::int) as batch_share,
               avg((e.user_type = 'human')::int) as human_share,
               avg((e.user_type = 'none')::int) as external_share
        from fct_item_events e join dim_activity a using (activity)
        group by e.activity, a.process_stage having count(*) >= 1000 order by n_events desc
        """
    )


def bottlenecks() -> pd.DataFrame:
    """Busiest waits, weighted by volume: total item-days spent on each step of the main flow."""
    return query(
        """
        select source_activity, target_activity, n_transitions, median_days, p90_days,
               n_transitions * median_days as item_days
        from mart_process_edges
        where flow = 'three_way_before_gr' and n_transitions >= 2000
        order by item_days desc limit 15
        """
    )


def edges(min_share: float = 0.01) -> pd.DataFrame:
    return query(
        f"""
        select * from mart_process_edges
        qualify n_transitions >= {min_share} * sum(n_transitions) over (partition by flow)
        """
    )


def monthly_stage_times() -> pd.DataFrame:
    return query(
        """
        select strftime(created_ts, '%Y-%m') as year_month,
               median(days_create_to_gr) as create_to_gr,
               median(days_invoice_to_clear) as invoice_to_clear,
               median(days_create_to_clear) as create_to_clear,
               count(*) as n_items
        from fct_po_items
        where flow = 'three_way_before_gr' and status = 'paid' and created_ts < date '2018-08-01'
        group by 1 order by 1
        """
    )
