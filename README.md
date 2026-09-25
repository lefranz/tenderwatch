# TenderWatch

**Who wins Swiss public contracts?** TenderWatch keeps a local copy of the
publications of [simap.ch](https://www.simap.ch) — the joint procurement platform
of the Swiss Confederation, cantons and municipalities — and links every award
winner to the Swiss commercial register (Zefix) through its UID
(`CHE-123.456.789`).

What it does today:

- **collects** every simap publication (tenders, awards, direct awards,
  abandonments…) through simap's public API, project by project and lot by lot,
  and keeps the **raw** answers — an edited publication never overwrites the
  previous version;
- **links** each winner to its commercial-register record (legal name, status,
  seat, legal form, official gazette notices);
- **ranks** the companies that win the most contracts, by number of awards,
  published amount or number of contracting authorities.

What it is heading for: **risk indicators** on procedures — single bids, direct
awards and the exemption invoked, short tender periods, concentration of one
winner at one contracting authority… See [docs/methodology.md](docs/methodology.md).

The most reusable piece is probably **[docs/simap-api.md](docs/simap-api.md)**:
field-level notes on simap's public API — which endpoints answer without a
token, pagination, lots, and the traps found while building this.

> **Status:** early, working version. Data from **1 July 2024** onwards (the new
> simap platform); the 2007–2024 archive is not collected yet.

## A word on vocabulary

TenderWatch computes **risk indicators**, never verdicts. A single signal says
little: in August 2026, **13 % of awards received a single bid** (150 sampled),
and each signal has legitimate explanations — a remote valley with one supplier,
an intellectual-property right, a short deadline announced long in advance.
Indicators are always compared with similar contracts, and the method is
published with the result.

## Install

Requires Python ≥ 3.11 and PostgreSQL (≥ 13).

```bash
python3 -m venv venv
venv/bin/pip install -e '.[test]'
createdb tenderwatch
venv/bin/tenderwatch init-db
```

The database is reached through a libpq connection string in
`TENDERWATCH_DSN` (default `dbname=tenderwatch`, local unix socket).

## Zefix credentials

Linking winners to the commercial register needs access to the **Zefix
PublicREST API**, run by the Federal Registry of Commerce (FRC). Access is free
but personal: request a username and password by email to
**`zefix@bj.admin.ch`**, stating your intended use. The API is documented on its
[Swagger page](https://www.zefix.admin.ch/ZefixPublicREST/swagger-ui/index.html).

Credentials are read **from the environment only**, never from the command line
(argv is visible to every local user through `ps`):

```bash
export ZEFIX_USERNAME=…  ZEFIX_PASSWORD=…
# or keep them in a file readable by you only, then:
set -a && . ~/.config/tenderwatch/zefix.env && set +a
```

Zefix asks users to avoid repeated bulk queries: TenderWatch queries each UID
**once** and keeps the answer.

Collection from simap needs no credentials.

## Usage

```bash
# 1. Collect — every step is resumable, whatever is stored is skipped
venv/bin/tenderwatch collect all --from 2026-01-01 --to 2026-09-30
#    = search (projects, month by month) → history (past publications)
#      → details (raw detail) → vendors (profiles, UID)

# 2. Link winners to the commercial register
venv/bin/tenderwatch zefix

# 3. Rank
venv/bin/tenderwatch ranking                                 # current year, top 50 by number of awards
venv/bin/tenderwatch ranking --order amount --top 100 --csv ranking.csv
```

Pace: about 3 calls per second (`--interval 0.35`). A full year is roughly
16,000 projects and 40,000 calls, i.e. 4 to 5 hours. No rate-limit header was
observed; the pace is a courtesy, not a measured constraint.

## Data model

See [`tenderwatch/schema.sql`](tenderwatch/schema.sql). Raw API answers are
stored as `jsonb`; everything else is derived by views, so changing an analysis
never requires downloading again.

| Table / view | Content |
|---|---|
| `projects` | one project per row, with the search answer |
| `publications` | one publication per row (one **lot** = one publication), raw `detail` |
| `publication_history` | replaced versions: an edited publication is never overwritten |
| `vendors` | public profiles of winners, including the normalised UID |
| `zefix_companies` | Zefix record per UID |
| `v_awards` | one row per (award, winner) |
| `v_awards_current` | same, without earlier versions of a corrected award |

## Limits — read before publishing a figure

Summarised here, detailed in [docs/methodology.md](docs/methodology.md):

- members of a **bidding consortium** are only named in free text: only the lead
  vendor is counted;
- the **price is the published price** — VAT included or not, sometimes a
  framework-agreement ceiling: totals are orders of magnitude;
- **corporate groups are not consolidated**;
- **losing bidders and their prices are never published**, so bid-rigging
  detection is out of reach;
- **below the publication thresholds, nothing appears at all**.

## Related work

- **[Red Flags in Public Procurement](https://www.open-contracting.org/resources/red-flags-in-public-procurement-a-guide-to-using-data-to-detect-and-mitigate-risks/)**
  (Open Contracting Partnership, 2024): the reference guide for data-driven risk
  indicators — 73 red flags across the procurement cycle, with definitions and
  formulas mapped to the Open Contracting Data Standard (OCDS). TenderWatch's
  indicators will start from this list.
- **[Cardinal](https://github.com/open-contracting/cardinal-rs)** (Open
  Contracting Partnership): open-source library that computes some of these red
  flags on OCDS data.
- **[Government Transparency Institute](https://www.govtransparency.eu)** and
  **[opentender.eu](https://opentender.eu)**: academic work led by Mihály
  Fazekas on procurement corruption-risk indicators, and their application to
  European procurement data.
- **[IntelliProcure](https://intelliprocure.ch/)** (Bern University of Applied
  Sciences): simap since 2009 including tender documents, full-text search; free
  accounts for journalists.
- **[Digilac/simap-mcp](https://github.com/Digilac/simap-mcp)**: an MCP server to
  query simap from an AI assistant.

## License

[GNU Affero General Public License v3.0 or later](LICENSE). If you run a modified
version as a network service, you must offer its source to its users.
