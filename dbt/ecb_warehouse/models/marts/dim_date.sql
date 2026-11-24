-- Calendar dimension 1999-01-01 .. 2030-12-31 (full rebuild).
-- TARGET closing days (the ECB publishes no reference rates): 1 Jan, Good Friday, Easter Monday, 1 May,
-- 25 and 26 Dec. Easter Sunday uses the anonymous Gregorian algorithm (Meeus/Jones/Butcher).
-- is_ecb_working_day comes from the EXR data itself (spec §5); is_target_business_day from the calendar.
with days as (
    select cast(gs.d as date) as full_date
    from generate_series(date '1999-01-01', date '2030-12-31', interval '1 day') as gs (d)
),

years as (
    select distinct cast(extract(year from full_date) as integer) as y
    from days
),

easter_terms as (
    select
        y,
        y % 19 as a,
        y / 100 as b,
        y % 100 as c
    from years
),

easter_calc as (
    select
        y,
        a,
        c,
        b % 4 as e,
        (19 * a + b - b / 4 - (b - (b + 8) / 25 + 1) / 3 + 15) % 30 as h
    from easter_terms
),

easter_calc2 as (
    select
        y,
        a,
        h,
        (32 + 2 * e + 2 * (c / 4) - h - c % 4) % 7 as l
    from easter_calc
),

easter as (
    select
        y,
        make_date(
            y,
            (h + l - 7 * ((a + 11 * h + 22 * l) / 451) + 114) / 31,
            (h + l - 7 * ((a + 11 * h + 22 * l) / 451) + 114) % 31 + 1
        ) as easter_sunday
    from easter_calc2
),

target_holidays as (
    select make_date(y, 1, 1) as holiday_date from years
    union all
    select easter_sunday - 2 from easter
    union all
    select easter_sunday + 1 from easter
    union all
    select make_date(y, 5, 1) from years
    union all
    select make_date(y, 12, 25) from years
    union all
    select make_date(y, 12, 26) from years
),

exr_days as (
    select distinct rate_date
    from {{ ref('stg_ecb__exr') }}
),

calendar as (
    select
        d.full_date,
        cast(to_char(d.full_date, 'YYYYMMDD') as integer) as date_key,
        cast(extract(year from d.full_date) as integer) as year_number,
        cast(extract(quarter from d.full_date) as integer) as quarter_number,
        cast(extract(month from d.full_date) as integer) as month_number,
        trim(to_char(d.full_date, 'Month')) as month_name,
        cast(date_trunc('month', d.full_date) as date) as month_start,
        cast(date_trunc('month', d.full_date) + interval '1 month - 1 day' as date) as month_end,
        cast(extract(day from d.full_date) as integer) as day_of_month,
        cast(extract(isodow from d.full_date) as integer) as iso_day_of_week,
        trim(to_char(d.full_date, 'Day')) as day_name,
        cast(extract(week from d.full_date) as integer) as iso_week,
        extract(isodow from d.full_date) in (6, 7) as is_weekend,
        h.holiday_date is not null as is_target_holiday,
        e.rate_date is not null as is_ecb_working_day
    from days as d
    left join target_holidays as h on d.full_date = h.holiday_date
    left join exr_days as e on d.full_date = e.rate_date
)

select
    date_key,
    full_date,
    year_number,
    quarter_number,
    month_number,
    month_name,
    month_start,
    month_end,
    day_of_month,
    iso_day_of_week,
    day_name,
    iso_week,
    is_weekend,
    is_target_holiday,
    not is_weekend and not is_target_holiday as is_target_business_day,
    is_ecb_working_day,
    full_date = month_end as is_month_end
from calendar
