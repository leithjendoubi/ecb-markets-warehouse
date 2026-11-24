# 0004: Calendar: TARGET days computed, ECB working days observed

**Context.** Spec §5 asks for `dim_date.is_ecb_working_day` "from EXR dates", and §7 for a test that no ECB
working day is missing for active currencies. If working days are only *observed*, a day the pipeline failed
to load is simply "not a working day" and the gap test can never fire.

**Decision.** `dim_date` carries both:
- `is_ecb_working_day`: the day has EXR reference rates in the data (spec definition).
- `is_target_business_day`: computed from the calendar: not a weekend and not a TARGET closing day
  (1 Jan, Good Friday, Easter Monday, 1 May, 25/26 Dec; Easter by the anonymous Gregorian algorithm).
The two are cross-checked by tests: EXR rates never fall on a non-business day (error), and every past
TARGET business day has rates for every active currency (warn, M5).

**Consequences.** Verified on load: for 2015-01-02..2026-11-23 both flags give 3,045 days with zero
mismatches. If the ECB ever closes on an extra day, the warn-level gap test surfaces it for review.
