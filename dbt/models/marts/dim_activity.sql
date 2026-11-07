select
    activity,
    case
        when activity like 'SRM:%' then 'SRM approval'
        when activity like '%Requisition%' then 'Requisition'
        when activity in ('Create Purchase Order Item', 'Receive Order Confirmation', 'Update Order Confirmation',
                          'Release Purchase Order') then 'Order'
        when activity in ('Record Goods Receipt', 'Record Service Entry Sheet') then 'Receipt'
        when activity in ('Vendor creates invoice', 'Vendor creates debit memo', 'Record Invoice Receipt',
                          'Record Subsequent Invoice') then 'Invoice'
        when activity in ('Clear Invoice', 'Remove Payment Block', 'Set Payment Block') then 'Payment'
        else 'Change / cancel'
    end                                as process_stage,
    activity like 'Change %' or activity like 'Cancel %'
        or activity in ('Delete Purchase Order Item', 'Reactivate Purchase Order Item',
                        'Block Purchase Order Item', 'Set Payment Block') as is_rework,
    count(*)                           as n_events,
    count(distinct item_id)            as n_items
from {{ ref('stg_events') }}
group by activity
