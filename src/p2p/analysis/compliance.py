"""Compliance summary: how often each control fails and how much money sits behind it."""

from __future__ import annotations

import pandas as pd

from p2p.analysis.common import query

RULES = {
    "r01_paid_before_goods_receipt": ("Paid before goods arrived", "Clear Invoice precedes any Goods Receipt"),
    "r02_invoice_before_gr_in_gr_based_flow": ("Invoice before receipt (GR-based)", "GR-based flow booked invoice first"),
    "r03_more_invoices_than_receipts": ("More invoices than receipts", "Paid item with more live invoices than goods receipts"),
    "r04_cleared_without_invoice": ("Paid without a recorded invoice", "Clear Invoice with no Record Invoice Receipt"),
    "r05_after_the_fact_purchase": ("After-the-fact purchase", "Vendor invoice dated before the order existed"),
    "r06_segregation_of_duties": ("Segregation of duties", "Same person ordered and received, or booked and paid"),
    "r07_price_change_after_invoice": ("Price changed after invoice", "Change Price after Record Invoice Receipt"),
    "r08_more_payments_than_invoices": ("More payments than invoices", "More Clear Invoice events than live invoices"),
    "r09_goods_receipt_on_two_way": ("Goods receipt on 2-way item", "2-way item should not have a receipt"),
    "r10_invoice_on_consignment": ("Invoice on consignment item", "Consignment items are invoiced separately"),
}


def rule_summary() -> pd.DataFrame:
    selects = " union all ".join(
        f"""select '{r}' as rule, count(*) filter ({r}) as n_items,
                   sum(value_at_risk_eur) filter ({r}) as value_at_risk_eur,
                   count(*) filter ({r} and status = 'open') as n_open,
                   count(distinct vendor_id) filter ({r}) as n_vendors,
                   count(*) as population
            from mart_compliance"""
        for r in RULES
    )
    df = query(selects)
    df["label"] = df["rule"].map(lambda r: RULES[r][0])
    df["definition"] = df["rule"].map(lambda r: RULES[r][1])
    df["rate"] = df["n_items"] / df["population"]
    return df.sort_values("value_at_risk_eur", ascending=False)


def overall() -> dict:
    d = query(
        """
        select count(*) as n_items,
               count(*) filter (n_rules_broken > 0) as n_flagged,
               sum(value_at_risk_eur) filter (n_rules_broken > 0) as value_flagged,
               sum(value_at_risk_eur) as value_total,
               count(*) filter (n_rules_broken >= 2) as n_multi
        from mart_compliance
        """
    ).iloc[0]
    return {k: float(v) for k, v in d.items()}


def by_spend_area() -> pd.DataFrame:
    return query(
        """
        select spend_area, count(*) as n_items, avg((n_rules_broken > 0)::int) as flag_rate,
               sum(value_at_risk_eur) filter (n_rules_broken > 0) as value_flagged
        from mart_compliance group by spend_area having count(*) >= 200 order by value_flagged desc nulls last
        """
    )


def sod_users() -> pd.DataFrame:
    """People who most often sat on both sides of a control."""
    return query(
        """
        select u.user_id, count(*) as n_items, sum(c.value_at_risk_eur) as value_eur
        from mart_compliance c
        join fct_po_items i using (item_id),
             unnest(list_distinct(list_concat(list_intersect(i.po_users, i.gr_users),
                                              list_intersect(i.invoice_users, i.clear_users)))) as u(user_id)
        where c.r06_segregation_of_duties
        group by u.user_id order by n_items desc limit 20
        """
    )
