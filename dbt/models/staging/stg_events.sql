-- One row per event. Implausible timestamps are flagged, never dropped.
with typed as (
    select
        case_id                                     as item_id,
        event_seq::int                              as source_seq,
        "concept:name"                              as activity,
        "User"                                      as user_id,
        (("time:timestamp")::timestamptz at time zone 'UTC')::timestamp as event_ts,
        "Cumulative net worth (EUR)"::double        as net_value_eur
    from {{ source('bronze', 'events') }}
)
select
    *,
    case when user_id like 'batch%' then 'batch'
         when user_id = 'NONE' then 'none'
         else 'human' end                           as user_type,
    event_ts >= date '{{ var("earliest_valid_date") }}'
        and event_ts < date '{{ var("snapshot_date") }}' + interval 1 day as is_valid_ts
from typed
