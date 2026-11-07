select
    d::date                     as date_key,
    year(d)                     as year,
    month(d)                    as month,
    strftime(d, '%Y-%m')        as year_month,
    date_trunc('week', d)::date as week_start,
    isodow(d)                   as iso_weekday,
    isodow(d) >= 6              as is_weekend
from range(date '2017-01-01', date '{{ var("snapshot_date") }}' + interval 1 day, interval 1 day) t(d)
