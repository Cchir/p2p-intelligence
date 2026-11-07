-- Each distinct path through the process. A long tail of variants is a measure of disorder.
select
    flow,
    trace                     as variant,
    count(*)                  as n_items,
    sum(order_value_eur)      as order_value_eur,
    median(days_create_to_clear) as median_days_to_clear,
    avg(n_rework_events)      as avg_rework
from {{ ref('fct_po_items') }}
group by flow, trace
