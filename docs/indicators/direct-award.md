# Direct award

**Status: preliminary** (3 October 2026). Protocol and statuses:
[README](./README.md).

Code: [`tenderwatch/direct_award.py`](../../tenderwatch/direct_award.py),
`tenderwatch direct-award`. Red flag of the OCP guide *Red Flags in Public
Procurement*: *Non-competitive procedure*, here as a share, per authority, of
contracts awarded without competition. It scores the **contracting
authority**, not the winner.

## In two minutes, for someone new to this

Most public purchases above a certain amount must be put out to tender, so that
several companies can bid. The law allows exceptions: the authority may then
award the contract **directly** to a company of its choice, without
competition. A direct award is legitimate when only one supplier can do the job
(a patent, a brand of equipment already installed), when there is a genuine
emergency (a landslide), or when an earlier tender drew no valid bid. In
Switzerland, about **one published contract in four** is a direct award.

A direct award on its own says nothing. So we look at each **public body** as a
whole, over two years, and ask whether it awards directly much more often than
other bodies buying similar things: same kind (works, services, supplies), same
order of magnitude of price, same canton. That gives a "normal" number of
direct awards for what it buys, and only gaps **too large to be chance** are
kept, taking into account how many bodies were examined.

This is not an accusation but a **risk indicator**: "here, competition was set
aside more often than elsewhere; the files are worth reading". The answer is
often in the files themselves, since a direct award above the thresholds must
state its legal ground.

## Exact criteria

| | |
|---|---|
| **Observation** | an awarded lot (`pub_type` `award` or `direct_award`), latest version (`v_awards_current`) |
| **Flag** | `pub_type = 'direct_award'` |
| **Weight** | 1 / (awarded lots of the project): a project weighs 1 |
| **Comparison group** | same type (`orderType`), same bracket of published price (< 150k, 150k–1M, 1–5M, ≥ 5M, unknown; `--brackets`), same canton of the authority (CH = federal) |
| **Why 150k** | the direct-award thresholds: CHF 150,000 for federal supplies and services, 100,000–150,000 for cantonal supplies and services, 150,000–300,000 for works. Below them, a direct award is the ordinary procedure and needs no ground |
| **Fallback** | a group of fewer than 50 projects (`--min-peers`) → whole country, then type alone |
| **Self-exclusion** | the authority tested is removed from its own group |
| **Authorities tested** | at least 10 projects (`--min-projects`) |
| **Test** | one-sided binomial, conservative; Benjamini-Hochberg `q` over all authorities tested |
| **Flagged** | `q < 0.05` |
| **Authority name** | `proc_offices.name` via `procOfficeId`, not the contact address name |

## Limits specific to this indicator

- **Only published direct awards count.** Below the thresholds, publishing a
  direct award is optional, and above them some are never published. An
  authority that publishes diligently shows more direct awards than one that
  hides them: a high share can be a sign of transparency. This is the main
  reason the indicator cannot be read alone.
- **Like is not always like.** The comparison group is the canton, the type and
  the price bracket, not the kind of authority. A university hospital renewing
  brand-tied imaging equipment is compared with municipalities building
  roads. Hospitals, universities and utilities are therefore expected near the
  top; the files say whether their grounds hold.
- **In-house awards** (an authority awarding to an entity it controls) are
  sometimes published as direct awards, though outside procurement law.
- **The published price sets the bracket**, with the same caveats as for single
  bids (framework ceilings, amounts copied onto every lot).
- **An office is not an institution**: see the single-bid page.

## Tests

| # | Test | State | Result |
|---|---|---|---|
| 1 | Unit tests | ✅ 3 Oct 2026 | self-exclusion, fallback, type and bracket groups, lot weights |
| 2 | Reading the flagged files | ⬜ | |
| 3 | Sensitivity to settings | ✅ 3 Oct 2026 | 38 of the 56 flagged stay at q < 0.10 in all six settings |
| 4 | Stability over time | ✅ 3 Oct 2026 | 8 authorities flagged on both halves |
| 5 | Calibration | ⬜ | |

## Log

### 3 October 2026 — first run

`tenderwatch direct-award --to 2026-10-01`, 1 July 2024 → 1 October 2026
(same data as the single-bid runs), default settings.

- 25,291 awarded lots, 22,307 projects once weighted; **5,774 direct awards,
  25.9 % of projects**. Groups: canton 19,992 lots, country 5,252, type
  alone 47.
- Share of direct awards by price bracket (projects): < 150k 38 %,
  150k–1M 24 %, 1–5M 21 %, ≥ 5M 27 %, unknown 36 %.
- 456 authorities tested, covering 75 % of projects.
- **56 flagged (q < 0.05)**, 68 at q < 0.10: 12 federal, 43 cantonal or
  communal, 1 without a canton. Far more than the
  single-bid indicator (7), and expected: direct awards are frequent, so even
  moderate gaps are significant on a few dozen projects. The number flagged
  is not yet readable; test 2 decides whether it must be narrowed (e.g. by
  kind of authority).
- **Sensitivity** (flagged by default, still q < 0.10): brackets ignored 55,
  brackets 250k/1M/5M 55, 100k/300k/1M/5M 56, minimum group 30 → 55, 100 →
  55; minimum authority 20 projects → 40 (231 authorities tested instead of
  456). **38** stay at q < 0.10 in all six settings: the core.
- **Stability**: July 2024–June 2025 flags 23 (170 tested), July 2025–
  September 2026 flags 28 (341 tested); **8 on both halves**, all among the 56.
- First reading of the top of the list, names only, files not read yet:
  hospitals (imaging and medical equipment), universities (instruments and
  subscriptions), public insurers and utilities, road offices, and at least
  one authority awarding to an entity of its own. Mostly the categories the
  limits above predict.
