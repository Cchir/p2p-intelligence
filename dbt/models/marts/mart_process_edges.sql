-- Directly-follows graph per flow: the raw material of process discovery.
with e as (
    select c.flow, o.prev_activity, o.activity, o.days_since_prev
    from {{ ref('int_events_ordered') }} o
    join {{ ref('stg_cases') }} c using (item_id)
    where o.prev_activity is not null
)
select
    flow, prev_activity as source_activity, activity as target_activity,
    count(*)                       as n_transitions,
    median(days_since_prev)        as median_days,
    quantile_cont(days_since_prev, 0.9) as p90_days
from e
group by flow, prev_activity, activity
