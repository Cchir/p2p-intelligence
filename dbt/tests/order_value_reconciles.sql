-- Total order value on the item fact must equal the value on the item creation events.
select 1
where abs((select sum(order_value_eur) from {{ ref('fct_po_items') }})
        - (select sum(net_value_eur) from {{ ref('fct_item_events') }} where activity = 'Create Purchase Order Item')) > 1
