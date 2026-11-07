select item_id from {{ ref('fct_item_events') }}
group by item_id having max(event_no) <> count(*)
