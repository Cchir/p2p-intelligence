-- Grain: one purchase order item. The central fact of the warehouse.
-- status: paid = cleared at least once; deleted = removed before any payment; open = neither.
-- Items open at the snapshot are right-censored: their cycle time is unknown, not missing.
with base as (
    select c.*, m.* exclude (item_id)
    from {{ ref('stg_cases') }} c
    join {{ ref('int_item_milestones') }} m using (item_id)
)
select
    *,
    case when first_clear_ts is not null then 'paid'
         when deleted_ts is not null then 'deleted'
         else 'open' end                                                 as status,
    created_ts >= date '2018-01-01'                                      as in_analysis_window,
    date_diff('minute', created_ts, first_clear_ts) / 1440.0             as days_create_to_clear,
    date_diff('minute', first_invoice_ts, first_clear_ts) / 1440.0       as days_invoice_to_clear,
    date_diff('minute', created_ts, first_gr_ts) / 1440.0                as days_create_to_gr,
    date_diff('minute', created_ts, timestamp '{{ var("snapshot_date") }} 23:59:00') / 1440.0 as days_since_created
from base
