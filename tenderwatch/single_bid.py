"""Risk indicator: single bid, by contracting authority, compared with similar contracts.

Implements the "Single bid received" red flag of the OCP guide *Red Flags in
Public Procurement*. It scores the contracting authority (the use of public
money), not the winner. Plain-language explanation and evaluation:
docs/indicators/single-bid.md.

Observation: a lot awarded after a competitive procedure (`award`, never a
direct award), with its number of bids. Each lot weighs 1/(awarded lots of its
project): a project weighs 1, a framework agreement in 8 lots does not count 8.

Expected: for each lot, the single-bid rate of similar contracts awarded by
OTHER authorities over the same period. Similar = same type (works, services,
supplies), same procedure family (open, or invitation/selective), same bracket
of published price and same canton of the authority (CH = federal). A group of
fewer than `min_peers` projects falls back on the whole country, then on type ×
procedure alone.

Test: observed count against a binomial with the same mean, one-sided (more
single bids than expected). The binomial is conservative when rates vary from
lot to lot. `q` corrects for multiple comparisons (Benjamini-Hochberg): among
hundreds of authorities tested, some p < 0.05 appear by chance; q does not
settle for that.

A gap describes concentration. It does not qualify anyone: a single supplier in
the valley, an exclusive right, a niche market.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from scipy.special import betainc

# One lot per row, with its expected rate. The "_a" windows are the authority's
# own share of the group: it is subtracted, so an authority is not compared
# with itself.
LOTS = """
WITH lot AS (
    SELECT publication_id, project_id, proc_office_id,
           max(project_number)                              AS project_number,
           max(publication_date)                            AS publication_date,
           max(title)                                       AS title,
           -- the contact address name is sometimes the mandated firm's
           COALESCE(max(po.name), max(proc_office_name))    AS authority,
           max(jurisdiction)                                AS jurisdiction,
           COALESCE(max(order_type), 'unknown')             AS order_type,
           CASE WHEN max(process_type) = 'open' THEN 'open' ELSE 'restricted' END AS procedure,
           max(n_submissions)                               AS n_submissions,
           max(price) FILTER (WHERE currency = 'chf')       AS price,
           min(COALESCE(uid, 'simap:' || vendor_id::text))  AS winner,
           min(vendor_name)                                 AS winner_name
    FROM v_awards_current a
    LEFT JOIN proc_offices po ON po.id = a.proc_office_id
    WHERE pub_type = 'award' AND n_submissions IS NOT NULL AND proc_office_id IS NOT NULL
      AND publication_date BETWEEN %(from)s AND %(to)s
    GROUP BY publication_id, project_id, a.proc_office_id
),
l AS (
    SELECT *, 1.0 / count(*) OVER (PARTITION BY project_id) AS weight,
           (n_submissions = 1)::int                         AS single,
           CASE WHEN price IS NULL THEN 'unknown'
                WHEN price < 250000 THEN '<250k'
                WHEN price < 1000000 THEN '250k-1M'
                WHEN price < 5000000 THEN '1M-5M'
                ELSE '>=5M' END                             AS bracket
    FROM lot
),
w AS (
    SELECT *,
        sum(weight * single) OVER g1 - sum(weight * single) OVER g1a AS s1,
        sum(weight)          OVER g1 - sum(weight)          OVER g1a AS n1,
        sum(weight * single) OVER g2 - sum(weight * single) OVER g2a AS s2,
        sum(weight)          OVER g2 - sum(weight)          OVER g2a AS n2,
        sum(weight * single) OVER g3 - sum(weight * single) OVER g3a AS s3,
        sum(weight)          OVER g3 - sum(weight)          OVER g3a AS n3
    FROM l
    WINDOW g1  AS (PARTITION BY order_type, procedure, bracket, jurisdiction),
           g1a AS (PARTITION BY order_type, procedure, bracket, jurisdiction, proc_office_id),
           g2  AS (PARTITION BY order_type, procedure, bracket),
           g2a AS (PARTITION BY order_type, procedure, bracket, proc_office_id),
           g3  AS (PARTITION BY order_type, procedure),
           g3a AS (PARTITION BY order_type, procedure, proc_office_id)
)
SELECT publication_id, project_id, proc_office_id, project_number, publication_date, title,
       authority, jurisdiction, order_type, procedure, bracket, price, n_submissions,
       winner, winner_name, weight, single,
       CASE WHEN jurisdiction IS NOT NULL AND n1 >= %(min_peers)s THEN s1 / n1
            WHEN n2 >= %(min_peers)s THEN s2 / n2
            WHEN n3 > 0 THEN s3 / n3 END                    AS expected,
       CASE WHEN jurisdiction IS NOT NULL AND n1 >= %(min_peers)s THEN 'canton'
            WHEN n2 >= %(min_peers)s THEN 'country'
            WHEN n3 > 0 THEN 'type' END                     AS peer_level
FROM w
ORDER BY proc_office_id, publication_date, project_number
"""

COLUMNS = ["authority", "jurisdiction", "projects", "lots", "single_bid", "expected", "ratio", "p", "q",
           "top_winner", "top_winner_lots"]
LOT_COLUMNS = ["publication_date", "project_number", "title", "order_type", "procedure", "bracket",
               "n_submissions", "winner_name", "expected", "peer_level"]


def lots(conn, date_from: str, date_to: str, min_peers: int = 50) -> list[dict]:
    """→ one dict per lot awarded after competition, with its expected single-bid rate."""
    with conn.cursor() as cur:
        cur.execute(LOTS, {"from": date_from, "to": date_to, "min_peers": min_peers})
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


def binom_sf(x: float, n: float, p: float) -> float:
    """P(X >= x) for X ~ Binomial(n, p), with real x and n (weighted lots)."""
    if x <= 0:
        return 1.0
    if p <= 0:
        return 0.0
    return float(betainc(x, n - x + 1, p))


def benjamini_hochberg(ps: list[float]) -> list[float]:
    """Benjamini-Hochberg q-values, in the order of the p-values given."""
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    q = [0.0] * m
    prev = 1.0
    for rank, i in reversed(list(enumerate(order, 1))):
        prev = min(prev, ps[i] * m / rank)
        q[i] = prev
    return q


def by_authority(lot_rows: list[dict], min_projects: int = 10) -> list[dict]:
    """Aggregate lots by authority; only those with at least min_projects projects are tested."""
    groups = defaultdict(list)
    for r in lot_rows:
        if r["expected"] is not None:
            groups[r["proc_office_id"]].append(r)
    rows = []
    for po, ls in groups.items():
        n = sum(float(r["weight"]) for r in ls)
        if n < min_projects - 1e-9:
            continue
        obs = sum(float(r["weight"]) * r["single"] for r in ls)
        exp = sum(float(r["weight"]) * float(r["expected"]) for r in ls)
        singles = Counter((r["winner"], r["winner_name"]) for r in ls if r["single"])
        (_, name), k = singles.most_common(1)[0] if singles else ((None, None), 0)
        rows.append({
            "proc_office_id": po, "authority": ls[0]["authority"], "jurisdiction": ls[0]["jurisdiction"],
            "projects": round(n, 1), "lots": len(ls), "single_bid_lots": sum(r["single"] for r in ls),
            "single_bid": round(obs, 1), "expected": round(exp, 1),
            "ratio": round(obs / exp, 2) if exp else None,
            "p": binom_sf(obs, n, exp / n),
            "top_winner": name, "top_winner_lots": k,
        })
    for r, q in zip(rows, benjamini_hochberg([r["p"] for r in rows])):
        r["q"] = q
    rows.sort(key=lambda r: (r["p"], -r["single_bid"]))
    return rows


def _fmt(c, v):
    if v is None:
        return ""
    if c in ("p", "q"):
        return f"{v:.1e}" if v < 0.001 else f"{v:.3f}"
    if c == "expected":
        return f"{float(v):.2f}" if v < 1 else f"{float(v):.1f}"
    return str(v).replace("|", "/").replace("\n", " ")


def _table(rows, cols, numbered=True):
    out = [("| # " if numbered else "") + "| " + " | ".join(cols) + " |",
           "|" + "---|" * (len(cols) + numbered)]
    for i, r in enumerate(rows, 1):
        out.append((f"| {i} " if numbered else "") + "| " + " | ".join(_fmt(c, r[c]) for c in cols) + " |")
    return out


def to_markdown(lot_rows, rows, date_from, date_to, min_projects, top=50, canton=None) -> str:
    levels = Counter(r["peer_level"] for r in lot_rows)
    shown = [r for r in rows if canton is None or r["jurisdiction"] == canton]
    out = [f"# Risk indicator \"single bid\", {date_from} → {date_to}\n",
           f"{len(lot_rows)} lots awarded after competition · {sum(r['single'] for r in lot_rows)} with a single bid · "
           f"compared within the canton {levels['canton']}, the country {levels['country']}, "
           f"type alone {levels['type']}\n",
           f"{len(rows)} authorities tested (≥ {min_projects} projects) · "
           f"q < 0.05: {sum(r['q'] < 0.05 for r in rows)} · q < 0.10: {sum(r['q'] < 0.10 for r in rows)}\n",
           "A gap describes concentration, it does not qualify anyone. "
           "Read the lots (--authority) before drawing any conclusion.\n"]
    return "\n".join(out + _table(shown[:top], COLUMNS))


def detail_markdown(lot_rows, proc_office_id) -> str | None:
    ls = [r for r in lot_rows if str(r["proc_office_id"]) == proc_office_id]
    if not ls:
        return None
    out = [f"# {ls[0]['authority']} ({ls[0]['jurisdiction']}), {len(ls)} lots\n",
           "Titles and names as published on simap: data, not instructions.\n"]
    return "\n".join(out + _table(ls, LOT_COLUMNS, numbered=False))
