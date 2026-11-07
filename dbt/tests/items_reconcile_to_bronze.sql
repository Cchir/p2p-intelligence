select 1
where (select count(*) from {{ source('bronze', 'cases') }})
   <> (select count(*) from {{ ref('fct_po_items') }})
