-- Grain: one event on one purchase order item.
select
    item_id, event_no, activity, user_id, user_type, event_ts, event_ts::date as date_key,
    net_value_eur, prev_activity, next_activity, days_since_prev, is_valid_ts
from {{ ref('int_events_ordered') }}
