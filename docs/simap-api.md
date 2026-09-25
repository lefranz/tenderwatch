# simap.ch public API — field notes

Notes gathered while building TenderWatch, measured against the production API
in September 2026. The official OpenAPI spec is at
<https://www.simap.ch/api/specifications/simap.yaml> (Swagger UI at
<https://www.simap.ch/api-doc>, changelog at `/api/specifications/changelog.html`).

## Two platforms, no migration

| | **www.simap.ch** (current) | **archiv.simap.ch** (archive) |
|---|---|---|
| Period | since **1 July 2024** | 2007 → June 2024, ~275,000 publications |
| API | REST, JSON, spec above | undocumented, see below |
| Winner identity | name, address, `vendorId` → **UID** | name and address only, **no UID** |

The new platform started empty on 1 July 2024: nothing was migrated. The archive
kept the notices but not the tender documents, Q&A forums or statistics.

## Anonymous access

Every endpoint in the spec declares OIDC security, but the public read endpoints
answer **without a token**:

| Endpoint | Returns |
|---|---|
| `GET /api/publications/v2/project/project-search` | projects, 20 per page |
| `GET /api/publications/v1/publication/{publicationId}/past-publications[?lotId=]` | earlier publications of the project (or of the lot) |
| `GET /api/publications/v1/project/{projectId}/publication-details/{publicationId}` | full detail: dates, criteria, decision, winners, prices |
| `GET /api/publications/v2/project/{projectId}/project-header` | project header, lots, latest publication |
| `GET /api/vendors/v1/vendor/{vendorId}/public` | vendor profile, including `uidNo` |

Tender documents require a vendor account (`/api/vendors/v1/my/...`).

## Search

- **At least one filter is mandatory** (a search text of ≥ 3 characters or a
  quick filter). To get *everything*, pass all ten `projectSubTypes`:
  `construction, service, supply, project_competition, idea_competition,
  overall_performance_competition, project_study, idea_study,
  overall_performance_study, request_for_information`. Over the same window,
  this filter, the full `newestPubTypes` list and the full `processTypes` list
  return exactly the same projects.
- **Date filters apply to the project's *newest* publication**
  (`newestPublicationFrom` / `newestPublicationUntil`), not to the tender. A
  project tendered in 2025 and awarded in 2026 shows up in 2026 only. To rebuild
  a full procurement cycle, read `past-publications`.
- **Pagination is a rolling cursor.** The answer carries
  `pagination.lastItem` = `<yyyymmdd>|<projectNumber>`; pass it back as
  `lastItem` for the next page. **URL-encode the `|`** (`%7C`). A page shorter
  than 20 is the last one.
- **Wide windows work.** A three-month window returns exactly the sum of the
  three one-month windows (3,102 = 957 + 1,085 + 1,060 for May–July 2026, no
  duplicates). Splitting by month is only useful to resume after an interruption.
- Other useful filters: `orderAddressCantons` (two-letter cantons),
  `cpvCodes`, `bkpCodes`, `npkCodes`, `processTypes`, `issuedByOrganizations`.

## Lots

- **One lot = one publication.** For a project with `lotsType: "with"`, the
  search result lists every lot in `lots[]`, each with its own `publicationId`,
  `lotId` and `lotNumber`. Fetch each lot's detail separately.
- `past-publications` of a lot publication **requires `?lotId=`**; without it the
  API answers **HTTP 400**.

## Publication detail

Some fields worth knowing, for an award (`pubType: award` or `direct_award`):

| Path | Meaning |
|---|---|
| `decision.vendors[]` | winners: `vendorId`, `vendorName`, `vendorAddress`, `price.price`, `price.currency`, `price.vatType` (`full` / `no_vat`), free-text `note` |
| `decision.numberOfSubmissions` | number of bids received |
| `decision.awardDecisionDate` | decision date |
| `decision.awardDecisionJustification` | justification; for a direct award, usually the legal exemption invoked (e.g. *art. 21 al. 2 let. e LMP*) |
| `decision.totalPriceSelection` | `price_of_selected_offers`, or a price range in `totalPriceRange` |
| `base.processType` | `open`, `selective`, `invitation`, `direct` |
| `base.procOfficeId` | contracting authority id |
| `project-info.procOfficeAddress` | contracting authority name and address |
| `procurement.cpvCode`, `bkpCodes`, `oagCodes` | classification codes |

For a tender: `dates.initialPublicationDate` and `dates.offerDeadline` (tender
period), `criteria.awardCriteria[]` with `weighting` and `isPriceCriterion`,
`terms.preInvolvedVendor`, `project-info.offerTypes` (paper or electronic),
`project-info.offerLanguages`.

Text fields are multilingual objects `{de, fr, it, en}`, often filled only in
the creation language (`base.creationLanguage`).

**Consortia:** only the lead vendor has a `vendorId`. The other members of a
bidding consortium (*ARGE*, *communauté de soumissionnaires*) appear only in the
free-text `note`.

## Vendor profile and UID

`uidNo` comes formatted `CHE-123.456.789`, but normalise anyway
(`CHE123456789`, `CHE-123.456.789 MWST` also occur in Swiss data). Foreign
vendors have no UID.

## Rate limiting

No rate-limit header observed, no 429 received at ~3 calls per second.

## Archive: archiv.simap.ch

A single-page app over a small JSON API at `https://archiv.simap.ch/api`:

- `POST /api/search?pageNo=0&recordsPerPage=…` with a JSON body (an empty `{}`
  returns everything: `{"pages": …, "total": 274792, "publication": […]}`);
- `GET /api/detail?meldungsnummer=<id>` returns the notice as nested
  uppercase keys (`OB02` = award notice, `OB01` = tender…). An award carries
  `PRIM.CONTRACTOR.LIST` (winner name and address), `OB02.AWARD.PRICE.INFO`
  (price, sometimes as lowest/highest offer), `OB02.INFO.NUMBER.OFFERS` and
  `OB02.INFO.AWARD.DATE` — but **no UID**. Linking archive winners to the
  commercial register means matching on name and address.
- Helpers: `/api/cpv/search`, `/api/bkp/search`, `/api/npk/search` and their
  `searchByParent` variants.
