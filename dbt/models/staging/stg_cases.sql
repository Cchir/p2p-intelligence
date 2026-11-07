-- One row per purchase order item. In process-mining terms each item is a "case".
select
    "concept:name"                                  as item_id,
    "Purchasing Document"                           as document_id,
    "Item"                                          as item_no,
    "Vendor"                                        as vendor_id,
    "Name"                                          as vendor_name,
    "Company"                                       as company_id,
    "Document Type"                                 as document_type,
    "Item Type"                                     as item_type,
    "Item Category"                                 as item_category,
    case "Item Category"
        when '3-way match, invoice after GR'  then 'three_way_after_gr'
        when '3-way match, invoice before GR' then 'three_way_before_gr'
        when '2-way match'                    then 'two_way'
        when 'Consignment'                    then 'consignment'
    end                                             as flow,
    coalesce(nullif(trim("Spend area text"), ''), 'Unclassified')     as spend_area,
    coalesce(nullif(trim("Sub spend area text"), ''), 'Unclassified') as sub_spend_area,
    coalesce(nullif(trim("Spend classification text"), ''), 'Unclassified') as spend_class,
    "GR-Based Inv. Verif." = 'true'                 as gr_based_invoice_verification,
    "Goods Receipt" = 'true'                        as goods_receipt_required
from {{ source('bronze', 'cases') }}
