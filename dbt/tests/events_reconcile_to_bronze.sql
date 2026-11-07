-- Fails if any bronze event was lost or duplicated on the way to the fact table.
select 1
where (select count(*) from {{ source('bronze', 'events') }})
   <> (select count(*) from {{ ref('fct_item_events') }})
