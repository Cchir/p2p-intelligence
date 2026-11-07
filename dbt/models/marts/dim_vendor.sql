-- A few vendor ids carry more than one anonymised name: keep the most frequent.
select
    vendor_id,
    mode(vendor_name)            as vendor_name,
    count(*)                     as n_items,
    count(distinct document_id)  as n_documents
from {{ ref('stg_cases') }}
group by vendor_id
