-- fct_policy_rate_daily is a calendar-day spine: no date may be missing between its first and last day.
select
    min(full_date) as first_date,
    max(full_date) as last_date,
    count(*) as n_days
from {{ ref('fct_policy_rate_daily') }}
having count(*) <> max(full_date) - min(full_date) + 1
