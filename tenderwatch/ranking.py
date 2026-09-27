"""Ranking of the companies that win the most public contracts.

Unit of count: one award = the latest award publication of a (project, lot).
A contract split into 3 lots and won entirely counts 3. One company = one UID
(several simap profiles with the same UID are merged); without a UID, the simap
profile.

Shared amount: the same price published several times within one project (for
several winners or several lots) is a common envelope, typically the volume of
a framework agreement "all lots combined", not what each winner obtained. It is
taken out of `published_amount_chf`, counted once per project in
`shared_amount_chf`, and `shared_amount_projects` says how many projects.

This ranking describes concentration. It does not qualify anyone: read
docs/methodology.md before publishing a figure.
"""
from __future__ import annotations

QUERY = """
WITH a AS (
    SELECT *, COALESCE(uid, 'simap:' || vendor_id::text) AS key,
           price IS NOT NULL
           AND count(*) OVER (PARTITION BY project_id, price, currency) > 1 AS shared
    FROM v_awards_current
    WHERE publication_date BETWEEN %(from)s AND %(to)s
),
shared AS (
    SELECT key, count(DISTINCT project_id) AS projects, sum(price) AS amount
    FROM (SELECT DISTINCT key, project_id, price FROM a
          WHERE shared AND currency = 'chf') d
    GROUP BY key
)
SELECT
    a.key,
    COALESCE(max(z.name), max(a.vendor_name))               AS company,
    max(a.uid)                                              AS uid,
    max(z.legal_seat)                                       AS seat,
    COALESCE(max(z.canton), max(a.vendor_canton))           AS canton,
    max(z.status)                                           AS register_status,
    count(DISTINCT a.publication_id)                        AS awards,
    count(DISTINCT a.proc_office_id)                        AS contracting_authorities,
    round(sum(a.price) FILTER (WHERE a.currency = 'chf' AND NOT a.shared)) AS published_amount_chf,
    max(s.projects)                                         AS shared_amount_projects,
    round(max(s.amount))                                    AS shared_amount_chf,
    count(DISTINCT a.publication_id) FILTER (WHERE a.price IS NULL) AS without_price,
    count(DISTINCT a.publication_id) FILTER (WHERE a.pub_type = 'direct_award') AS direct_awards,
    count(DISTINCT a.publication_id) FILTER (WHERE a.n_submissions = 1)        AS single_bid
FROM a
LEFT JOIN zefix_companies z ON z.uid = a.uid AND z.error IS NULL
LEFT JOIN shared s ON s.key = a.key
GROUP BY 1
ORDER BY {order} DESC NULLS LAST, awards DESC
LIMIT %(top)s
"""

QUALITY = """
WITH a AS (
    SELECT *, price IS NOT NULL
              AND count(*) OVER (PARTITION BY project_id, price, currency) > 1 AS shared
    FROM v_awards_current WHERE publication_date BETWEEN %(from)s AND %(to)s
)
SELECT count(DISTINCT publication_id)                                    AS awards,
       count(*)                                                          AS winner_rows,
       count(*) FILTER (WHERE uid IS NOT NULL)                           AS with_uid,
       count(*) FILTER (WHERE price IS NULL)                             AS without_price,
       count(*) FILTER (WHERE vat_type = 'full')                         AS price_incl_vat,
       count(*) FILTER (WHERE vat_type = 'no_vat')                       AS price_excl_vat,
       count(*) FILTER (WHERE currency IS NOT NULL AND currency <> 'chf') AS other_currency,
       count(DISTINCT project_id) FILTER (WHERE shared)                 AS shared_amount_projects
FROM a
"""

ORDERS = {"count": "awards", "amount": "published_amount_chf", "authorities": "contracting_authorities"}
COLUMNS = ["company", "uid", "canton", "register_status", "awards", "contracting_authorities",
           "published_amount_chf", "shared_amount_projects", "shared_amount_chf", "direct_awards", "single_bid"]
AMOUNTS = {"published_amount_chf", "shared_amount_chf"}


def ranking(conn, date_from: str, date_to: str, order: str = "count", top: int = 50):
    """→ (quality summary dict, list of row dicts)."""
    params = {"from": date_from, "to": date_to, "top": top}
    with conn.cursor() as cur:
        cur.execute(QUALITY, params)
        quality = dict(zip([d[0] for d in cur.description], cur.fetchone()))
        cur.execute(QUERY.format(order=ORDERS[order]), params)
        names = [d[0] for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]
    return quality, rows


def chf(n):
    return "" if n is None else f"{int(n):,}".replace(",", "'")


def to_markdown(quality: dict, rows: list[dict], date_from: str, date_to: str, order: str) -> str:
    out = [f"# simap award winners, {date_from} → {date_to}, sorted by {order}\n",
           f"{quality['awards']} awards · {quality['winner_rows']} winner rows · "
           f"UID known {quality['with_uid']} · without price {quality['without_price']} · "
           f"price incl. VAT {quality['price_incl_vat']} / excl. VAT {quality['price_excl_vat']} · "
           f"other currency {quality['other_currency']} · "
           f"projects with a shared amount {quality['shared_amount_projects']}\n",
           "| # | " + " | ".join(COLUMNS) + " |",
           "|" + "---|" * (len(COLUMNS) + 1)]
    for i, r in enumerate(rows, 1):
        vals = [chf(r[c]) if c in AMOUNTS else ("" if r[c] is None else str(r[c])) for c in COLUMNS]
        out.append(f"| {i} | " + " | ".join(vals) + " |")
    return "\n".join(out)
