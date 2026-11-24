-- Calendar sanity: the ECB publishes reference rates only on TARGET business days. A row here means either
-- the holiday logic in dim_date is wrong or the source changed its calendar.
select
    f.rate_date,
    f.currency_code
from {{ ref('stg_ecb__exr') }} as f
inner join {{ ref('dim_date') }} as d on f.rate_date = d.full_date
where not d.is_target_business_day
