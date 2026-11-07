-- Grain: one purchasing document (header), which holds one or more items.
select
    document_id,
    any_value(vendor_id)          as vendor_id,
    any_value(company_id)         as company_id,
    any_value(document_type)      as document_type,
    min(created_ts)               as created_ts,
    count(*)                      as n_items,
    sum(order_value_eur)          as order_value_eur,
    count(*) filter (status = 'paid')    as n_paid,
    count(*) filter (status = 'open')    as n_open,
    count(*) filter (status = 'deleted') as n_deleted
from {{ ref('fct_po_items') }}
group by document_id
