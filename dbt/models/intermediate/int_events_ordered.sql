-- Events in process order with their neighbours: the base for every sequence analysis.
-- Same-minute ties keep the source order, which is the order the ERP recorded them in.
with ordered as (
    select
        *,
        row_number() over w                         as event_no,
        lag(activity) over w                        as prev_activity,
        lag(event_ts) over w                        as prev_ts,
        lead(activity) over w                       as next_activity
    from {{ ref('stg_events') }}
    window w as (partition by item_id order by event_ts, source_seq)
)
select
    *,
    date_diff('minute', prev_ts, event_ts) / 1440.0 as days_since_prev
from ordered
