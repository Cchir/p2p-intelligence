select
    strftime(created_ts, '%Y-%m')                as year_month,
    flow,
    count(*)                                     as n_items,
    sum(order_value_eur)                         as order_value_eur,
    count(*) filter (status = 'paid')            as n_paid,
    count(*) filter (status = 'open')            as n_open,
    median(days_create_to_clear)                 as median_days_to_clear,
    avg((n_rework_events > 0)::int)              as rework_rate
from {{ ref('fct_po_items') }}
where in_analysis_window
group by 1, 2
