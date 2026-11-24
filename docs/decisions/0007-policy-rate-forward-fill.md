# 0007: Policy rates: bounded forward fill, MRO gap kept as NULL

**Context.** Spec §5: DFR, MRO and MLF "forward-filled onto the date spine". The FM series turned out to have a
row for every calendar day, except `MRR_FR` (MRO fixed rate), which has no observations from 2000-06-28 to
2008-10-14 (3,032 days) because the ECB ran variable-rate tenders then. An unbounded forward fill would
report the June 2000 value (4.25%) for eight years, which is false.

**Decision.** Forward fill carries a value over at most `max_ffill_days` = 7 days without an observation
(dbt var). As a result MRO is NULL from 2000-07-05 to 2008-10-14; DFR and MLF are complete.
`is_change_day` compares each day with the previous day (NULL-safe), since the source has no "change date"
flag.

**Consequences.** No invented values. Within a week of a real gap the last value is still shown (first 7 days
of the tender period carry 4.25%). Optional extension, not done because it is outside the spec's key list:
the ECB publishes the minimum bid rate `FM.D.U2.EUR.4F.KR.MRR_MBR.LEV`, which covers exactly that period
(checked live 2026-11-24: 3,031 daily rows 2000-06-28..2008-10-14); adding it to `config.yaml` would allow an
"MRO (fixed or minimum bid)" column.
