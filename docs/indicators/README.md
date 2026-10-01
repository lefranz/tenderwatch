# Risk indicators: testing protocol

A risk indicator flags a contract or a contracting authority worth a closer
look. It does not qualify anyone (see [methodology](../methodology.md),
principle 1). Each indicator has a page here, named after it
(`single-bid.md`): what it measures in plain words, its exact criteria, the
tests it went through and what each run gave.

**Results are published in aggregate only**: number of lots, rates, number of
authorities flagged. An indicator that has not been calibrated (status below)
names no one. Lists of flagged authorities are a starting point for reading
files, not a finding.

## Statuses

| Status | What it takes | What it can be used for |
|---|---|---|
| **preliminary** | the code runs and is tested; the method is written down | opening files, internally |
| **evaluated** | the five tests below are passed and recorded | choosing where to look |
| **calibrated** | it brings out known cases without drowning them in noise | citing it, with the method attached |
| **publishable** | legal review of vocabulary and method | showing it in a public tool |

No step is skipped, and an indicator goes back down if a re-run test fails.

## The five tests

1. **Unit tests**: hand-built cases (lots, fallback groups, self-exclusion)
   give the expected result. `pytest`.
2. **Reading the flagged files**: read lot by lot at least the first five
   authorities flagged, and sort each: obvious legitimate explanation (niche,
   exclusive right, brand-tied maintenance), data artefact, or **worth
   investigating**. An indicator that only brings out artefacts must be revised.
3. **Sensitivity to settings**: vary every arbitrary threshold (minimum size of
   a group, of an authority, price brackets). A signal that vanishes at the
   slightest change is not one.
4. **Stability over time**: split the period in two. An authority flagged on
   both halves has a practice; on one only, an episode, to be dated.
5. **Calibration**: known cases, established by a ruling or a published
   investigation, must come out, and the number flagged must stay readable.

## Recording a run

Every run that matters (first use, change of method, re-run test) adds a dated
entry to the indicator's **log**: date, commit, exact command and period;
overall figures; what changed since the previous run and why. Entries are never
deleted: a wrong result is corrected in a new entry that says what was wrong.
