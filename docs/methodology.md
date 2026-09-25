# Methodology

## Principles

1. **Risk indicators, never verdicts.** An indicator flags a procedure worth a
   closer look. It does not say that anything improper happened: each signal has
   legitimate explanations, and only a combination of signals, compared with
   similar contracts, carries meaning.
2. **Compare like with like.** Same type of contract (works, services,
   supplies), same canton, same amount bracket.
3. **Score procedures and contracting authorities** — the use of public money —
   rather than companies.
4. **Publish the method with the result**, including the known limits below.
5. **Calibrate before publishing.** An indicator that does not bring out known,
   documented cases is worthless; one that flags hundreds of ordinary contracts
   must be revised.

## Unit of count

- **One award** = the latest award publication (`award` or `direct_award`) of a
  (project, lot). Earlier versions of a corrected award are dropped
  (`v_awards_current`). A contract in three lots won entirely counts three.
- **One company** = one UID. Several simap profiles with the same UID are merged.
  Without a UID (foreign vendors, rare cases), the simap profile stands alone.
- **Published amount** = sum of the prices published for the winner, in CHF.

## Ranking

`tenderwatch ranking` orders winners by number of awards (`count`), published
amount (`amount`) or number of distinct contracting authorities
(`authorities`). For each winner it also shows how many awards were direct
awards and how many received a single bid.

A raw ranking mostly surfaces large construction firms: by count, those who win
many lots; by amount, those who win large works and framework agreements. This
is expected and says little on its own. More telling, and the first planned
indicator: **concentration at a contracting authority** — the share of one
authority's awards that goes to the same company.

## Known limits of the data

- **Consortia.** Only the lead vendor has a `vendorId`; other members are named
  in free text only. A contract won by three firms counts for the lead alone.
- **Prices.** The published price may include VAT (`vat_type = full`) or not
  (`no_vat`); the amount excluding VAT is sometimes only in the free-text note. It
  may be a framework-agreement ceiling rather than actual spending. Totals are
  orders of magnitude, not accounts.
- **Corporate groups** are not consolidated: a parent and its subsidiaries are
  distinct UIDs.
- **Lots** count one award each.
- **Losing bidders and their prices are never published.** Detecting collusion
  between bidders (bid rotation, cover bids, price patterns) requires all bids;
  only the competition authority has them.
- **No estimated value, no contract amendments** are published: cost overruns
  are invisible.
- **Below the publication thresholds, nothing is published**, so deliberate
  splitting of a contract is invisible by construction. For the Confederation,
  the annual list of contracts of CHF 50,000 and more (published by the Federal
  Procurement Conference, BKB) partly fills the gap and lists direct awards that
  never appeared on simap.
- **History starts on 1 July 2024** for structured data with UIDs. The 2007–2024
  archive has winners by name only.

## References

- Open Contracting Partnership, *[Red Flags in Public Procurement. A guide to
  using data to detect and mitigate risks](https://www.open-contracting.org/resources/red-flags-in-public-procurement-a-guide-to-using-data-to-detect-and-mitigate-risks/)*,
  2024 ([PDF](https://www.open-contracting.org/wp-content/uploads/2024/12/OCP2024-RedFlagProcurement-1.pdf)).
  73 indicators with formulas over OCDS data. Many of them need data simap does
  not publish (losing bids, estimated value, contract amendments); each
  TenderWatch indicator will state which red flag of the guide it implements,
  and why others are out of reach.
- [Cardinal](https://github.com/open-contracting/cardinal-rs), OCP's
  open-source implementation of part of the guide on OCDS data. Converting
  simap publications to OCDS would make it usable here.

