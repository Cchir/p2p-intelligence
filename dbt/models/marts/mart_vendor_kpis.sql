select
    i.vendor_id,
    v.vendor_name,
    count(*)                                     as n_items,
    sum(i.order_value_eur)                       as order_value_eur,
    count(*) filter (i.first_invoice_ts is not null) as n_invoiced,
    count(*) filter (i.n_block_removals > 0 or i.n_invoice_cancels > 0) as n_invoice_problems,
    count(*) filter (i.n_rework_events > 0)      as n_reworked,
    median(i.days_create_to_clear)               as median_days_to_clear,
    sum(c.n_rules_broken)                        as n_rule_breaks
from {{ ref('fct_po_items') }} i
join {{ ref('dim_vendor') }} v using (vendor_id)
join {{ ref('mart_compliance') }} c using (item_id)
group by i.vendor_id, v.vendor_name
