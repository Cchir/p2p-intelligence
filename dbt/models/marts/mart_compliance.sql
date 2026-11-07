-- One row per item with each control tested. Rules follow the matching logic in the source
-- description: which documents must exist, in what order, for each of the four flows.
-- Three-way matching is tested on document counts: the value field holds the item's cumulative
-- net worth on every event, so amounts per document are not available. Exposure is the order value.
with i as (select * from {{ ref('fct_po_items') }}),
late_price_changes as (
    select distinct e.item_id
    from {{ ref('int_events_ordered') }} e
    join i on i.item_id = e.item_id
    where e.activity = 'Change Price' and e.event_ts > i.first_invoice_ts
),
flags as (
    select
        i.item_id, document_id, vendor_id, flow, status, spend_area,
        order_value_eur,
        order_value_eur                                                      as value_at_risk_eur,

        -- Goods-based flows must not be paid before goods arrive
        goods_receipt_required and flow <> 'consignment' and first_clear_ts is not null
            and (first_gr_ts is null or first_gr_ts > first_clear_ts)        as r01_paid_before_goods_receipt,
        -- GR-based verification: the invoice may only be booked after the receipt
        flow = 'three_way_after_gr' and first_invoice_ts is not null
            and (first_gr_ts is null or first_invoice_ts < first_gr_ts)      as r02_invoice_before_gr_in_gr_based_flow,
        -- Every invoice should have a matching receipt (services use entry sheets instead)
        flow in ('three_way_after_gr', 'three_way_before_gr') and item_type <> 'Service' and status = 'paid'
            and net_invoices > net_goods_receipts                            as r03_more_invoices_than_receipts,
        -- Money left without a recorded invoice
        flow <> 'consignment' and n_clears > 0 and n_invoices = 0            as r04_cleared_without_invoice,
        -- Vendor invoiced before the order existed: the order was raised after the fact
        coalesce(vendor_invoice_ts < created_ts - interval 1 day, false)     as r05_after_the_fact_purchase,
        -- Segregation of duties: one person both ordered and received, or booked and paid
        len(list_intersect(po_users, gr_users)) > 0
            or len(list_intersect(invoice_users, clear_users)) > 0           as r06_segregation_of_duties,
        -- Price edited after the invoice arrived
        l.item_id is not null                                                as r07_price_change_after_invoice,
        -- More payment runs than live invoices: a duplicate-payment indicator
        status = 'paid' and n_clears > greatest(net_invoices, 1)             as r08_more_payments_than_invoices,
        -- Flow-level expectations
        flow = 'two_way' and n_goods_receipts > 0                            as r09_goods_receipt_on_two_way,
        flow = 'consignment' and n_invoices > 0                              as r10_invoice_on_consignment
    from i
    left join late_price_changes l on l.item_id = i.item_id
)
select
    *,
    (r01_paid_before_goods_receipt::int + r02_invoice_before_gr_in_gr_based_flow::int
     + r03_more_invoices_than_receipts::int + r04_cleared_without_invoice::int
     + r05_after_the_fact_purchase::int + r06_segregation_of_duties::int
     + r07_price_change_after_invoice::int + r08_more_payments_than_invoices::int
     + r09_goods_receipt_on_two_way::int + r10_invoice_on_consignment::int)  as n_rules_broken
from flags
