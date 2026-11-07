select
    user_id,
    any_value(user_type)    as user_type,
    count(*)                as n_events,
    count(distinct item_id) as n_items,
    mode(activity)          as main_activity
from {{ ref('stg_events') }}
group by user_id
