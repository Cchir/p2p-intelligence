-- Pivot the event stream to one row per item: when each milestone happened and how often.
select
    item_id,
    min(event_ts)                                                       as first_event_ts,
    max(event_ts)                                                       as last_event_ts,
    count(*)                                                            as n_events,
    bool_and(is_valid_ts)                                               as all_ts_valid,
    min(event_ts) filter (activity = 'Create Purchase Requisition Item') as requisition_ts,
    min(event_ts) filter (activity = 'Create Purchase Order Item')       as created_ts,
    min(event_ts) filter (activity = 'Vendor creates invoice')           as vendor_invoice_ts,
    min(event_ts) filter (activity = 'Record Goods Receipt')             as first_gr_ts,
    min(event_ts) filter (activity = 'Record Invoice Receipt')           as first_invoice_ts,
    min(event_ts) filter (activity = 'Clear Invoice')                    as first_clear_ts,
    max(event_ts) filter (activity = 'Clear Invoice')                    as last_clear_ts,
    min(event_ts) filter (activity = 'Delete Purchase Order Item')       as deleted_ts,
    min(event_ts) filter (activity = 'Remove Payment Block')             as payment_block_removed_ts,
    count(*) filter (activity = 'Record Goods Receipt')                  as n_goods_receipts,
    count(*) filter (activity = 'Record Invoice Receipt')                as n_invoices,
    count(*) filter (activity = 'Clear Invoice')                         as n_clears,
    count(*) filter (activity = 'Change Price')                          as n_price_changes,
    count(*) filter (activity = 'Change Quantity')                       as n_quantity_changes,
    count(*) filter (activity = 'Cancel Invoice Receipt')                as n_invoice_cancels,
    count(*) filter (activity = 'Cancel Goods Receipt')                  as n_gr_cancels,
    count(*) filter (activity = 'Remove Payment Block')                  as n_block_removals,
    count(*) filter (activity like 'Change %' or activity like 'Cancel %'
                     or activity in ('Delete Purchase Order Item', 'Reactivate Purchase Order Item',
                                     'Block Purchase Order Item', 'Set Payment Block')) as n_rework_events,
    max(net_value_eur) filter (activity = 'Create Purchase Order Item')  as order_value_eur,
    -- Document balance as counts. The value field repeats the item's cumulative net worth on every
    -- event, so document amounts cannot be recovered and values must not be summed across events.
    count(*) filter (activity = 'Record Goods Receipt') - count(*) filter (activity = 'Cancel Goods Receipt') as net_goods_receipts,
    count(*) filter (activity = 'Record Invoice Receipt') - count(*) filter (activity = 'Cancel Invoice Receipt') as net_invoices,
    coalesce(list(distinct user_id) filter (activity = 'Create Purchase Order Item' and user_type = 'human'), []) as po_users,
    coalesce(list(distinct user_id) filter (activity = 'Record Goods Receipt' and user_type = 'human'), [])       as gr_users,
    coalesce(list(distinct user_id) filter (activity = 'Record Invoice Receipt' and user_type = 'human'), [])     as invoice_users,
    coalesce(list(distinct user_id) filter (activity = 'Clear Invoice' and user_type = 'human'), [])              as clear_users,
    string_agg(activity, ' > ' order by event_no)                        as trace
from {{ ref('int_events_ordered') }}
group by item_id
