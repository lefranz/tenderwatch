# Single bid

**Status: preliminary** (1 October 2026). Protocol and statuses:
[README](./README.md).

Code: [`tenderwatch/single_bid.py`](../../tenderwatch/single_bid.py),
`tenderwatch single-bid`. Red flag of the OCP guide *Red Flags in Public
Procurement*: *Single bid received*. It scores the **contracting authority**,
not the winner.

## In two minutes, for someone new to this

When a public body buys something substantial, it publishes a call for tenders
and interested companies bid. The more bids, the more competition works.
Sometimes only one company bids: in Switzerland, about **one time in ten**.

A single-bid contract on its own says nothing: there is often a good reason (a
single supplier in the region, a very specialised product, software that only
its publisher maintains). So we look at each **public body** as a whole, over
two years, and ask whether it receives single bids much more often than the
others.

To compare fairly, we do not set a mountain municipality repaving a road
against the Confederation buying computers. For each purchase, we look at what
happens with **similar purchases by other public bodies**: same kind (works,
services, supplies), same order of magnitude of price, same canton. That gives
a "normal" number of single bids. Example: given what it buys, one authority
should have had about 12; it had 28.

With hundreds of public bodies compared, some exceed the norm by mere bad luck,
like a few coins landing heads five times in a row when many are tossed. Only
gaps **too large to be chance** are kept, taking into account how many bodies
were examined, and bodies with fewer than 10 contracts are left aside, too small
to tell.

This is not an accusation but a **risk indicator**: "here, competition worked
less than elsewhere; the files are worth reading". The explanation may be
entirely legitimate: a federal purchasing centre receiving a single bid for coin
blanks, because very few plants in the world make them.

## Exact criteria

| | |
|---|---|
| **Observation** | a lot awarded after competition (`pub_type = 'award'`); direct awards are excluded, nobody else could bid |
| **Single bid** | `decision.numberOfSubmissions = 1` |
| **Weight** | 1 / (awarded lots of the project): a project weighs 1 |
| **Comparison group** | same type (`orderType`), same procedure family (open, or invitation/selective), same bracket of published price (< 250k, 250k–1M, 1–5M, ≥ 5M, unknown; `--brackets`), same canton of the authority (CH = federal) |
| **Fallback** | a group of fewer than 50 projects (`--min-peers`) → whole country, then type × procedure |
| **Self-exclusion** | the authority tested is removed from its own group |
| **Authorities tested** | at least 10 projects (`--min-projects`) |
| **Test** | one-sided binomial, conservative; Benjamini-Hochberg `q` over all authorities tested |
| **Flagged** | `q < 0.05` |
| **Authority name** | `proc_offices.name` via `procOfficeId`, not the contact address name (sometimes a mandated firm) |

## Limits specific to this indicator

- **The published price sets the bracket**, yet it is sometimes a
  framework-agreement ceiling or an envelope copied onto every lot (see
  methodology). A lot can land in too high a bracket.
- **What is not published does not exist**: an authority that awards directly
  what others put out to tender does not show here. That is a separate
  indicator (share of direct awards, exemptions invoked).
- **An office is not an institution**: a canton buying through several offices
  is split into as many authorities, often too small to be tested (about 2,600
  of 2,960 have fewer than 10 projects). Grouping by `institution_id` is an
  avenue.
- **The number of bids is the one in the published decision**; whether
  inadmissible bids are included is up to the authority and never stated.

## Tests

| # | Test | State | Result |
|---|---|---|---|
| 1 | Unit tests | ✅ 1 Oct 2026 | binomial tail, BH, lot weights, threshold, self-exclusion, fallback |
| 2 | Reading the flagged files | 🟡 2 of 7 | one worth investigating (brand-tied maintenance renewals), one legitimate niche |
| 3 | Sensitivity to settings | ✅ 3 Oct 2026 | group and authority thresholds: stable core of 5–6; price brackets: the 7 flagged stay flagged in all 6 settings |
| 4 | Stability over time | ✅ 1 Oct 2026 | unstable: see log |
| 5 | Calibration | ⬜ | no known case within the data window (from July 2024) |

## Log

### 1 October 2026 — first run

`tenderwatch single-bid`, 1 July 2024 → 1 October 2026, default settings.

- 19,499 lots awarded after competition, 2,114 with a single bid (10.8 %).
  Groups: canton 13,537 lots, country 5,636, type alone 326.
- 357 authorities tested out of about 2,600, covering 70 % of projects.
- **7 flagged (q < 0.05)**: 5 cantonal or communal, 2 federal.
- **Sensitivity** (q < 0.05): minimum group 30 projects → 9 flagged, 100 → 6;
  minimum authority 20 projects → 6. Five authorities stay flagged or just
  above (q < 0.10) in every setting: the core.
- **Stability**: split in two, the period flags only **1** authority over
  July 2024–June 2025 (120 tested) and **2** over July 2025–September 2026
  (274 tested), not the same ones. Half the data per half means less power, but
  the authorities do come out on one half rather than the other: to be dated in
  the files.
- **Fixed along the way**: the authority name first came from the
  publication's contact address, sometimes that of the mandated architects.
  It now comes from `proc_offices`.

### 3 October 2026 — price brackets varied

`tenderwatch single-bid --brackets …`, same period and data as the first run
(1 July 2024 → 1 October 2026, 19,499 lots, 357 authorities tested), every
other setting at its default. Closes test 3: group and authority thresholds
were varied on 1 October, brackets were not.

| Brackets (CHF) | Lots compared within the canton | q < 0.05 | q < 0.10 | of the 7 flagged by default, still q < 0.05 |
|---|---|---|---|---|
| 250k, 1M, 5M (default) | 13,537 | 7 | 9 | 7 |
| none (price ignored) | 18,247 | 7 | 13 | 7 |
| 1M | 15,478 | 9 | 10 | 7 |
| 100k, 500k, 2M | 13,396 | 9 | 10 | 7 |
| 500k, 2M, 10M | 13,791 | 8 | 10 | 7 |
| 150k, 350k, 1M, 5M, 10M | 12,440 | 7 | 8 | 7 |

- **The signal does not depend on the brackets**: the 7 authorities flagged
  by default stay flagged in every setting, even with the price ignored.
- Two more authorities (a municipal department, a municipal utility) are
  flagged under some brackets only: borderline cases, not part of the core.
- Finer brackets push more lots to the country-wide fallback (groups under
  50 projects), coarser ones keep them in their canton: the flagged set
  barely moves either way.

