"""Risk indicator: direct awards, by contracting authority, compared with similar contracts.

Implements the "Non-competitive procedure" red flag of the OCP guide *Red Flags
in Public Procurement* (high share of contracts awarded without competition).
It scores the contracting authority, not the winner. Plain-language explanation
and evaluation: docs/indicators/direct-award.md.

Observation: every awarded lot (`award` or `direct_award`). Flag: the lot was
awarded directly, without competition: published as `direct_award` WITH the
`direct` procedure. Each lot weighs 1/(awarded lots of its project).

A `direct_award` publication whose procedure is open, selective or by
invitation (19 % of them, measured on 3 October 2026) is almost always a
tender award published under the wrong type: its justification describes
the evaluation of several bids ("beste Erfüllung der Zuschlagskriterien",
"l'offre a remporté le plus de points"), and 15 out of 1,124 cite a ground of
art. 21. It counts as an award after competition (`mistyped` = 1). The cost:
those 15 genuine direct awards are lost.

Expected: for each lot, the share of direct awards among similar contracts
awarded by OTHER authorities over the same period. Similar = same type (works,
services, supplies), same bracket of published price (`brackets`, default
< 150k, 150k–1M, 1–5M, ≥ 5M, unknown) and same canton of the authority (CH =
federal). The first bound sits at the thresholds: under about CHF 150,000 a
direct award is the ordinary procedure and needs no exemption, above it it is
the exception (art. 21 para. 2 PPA/IPPA). A group of fewer than `min_peers`
projects falls back on the whole country, then on the type alone.

Test and correction for multiple comparisons: see risk.py.

Legal ground: above the thresholds, a direct award must rest on one of the
grounds of art. 21 para. 2 (letters a to i, `GROUNDS`). simap has no field for
it; `grounds()` reads the letters cited in the free-text justification. Each
direct-award lot gets `ground` ("c", "ce"; "other" when the justification
cites no recognised letter, "empty" when there is none), and each authority a
count by letter.

Only what is published counts: an authority that publishes its direct awards
diligently shows more of them than one that does not publish them at all. Within
a canton the rules are the same; across authorities of different kinds
(utility, municipality, university) habits of publication differ.
"""
from __future__ import annotations

import re
from collections import Counter

from .risk import _table, bracket_case, by_authority as _by_authority

DEFAULT_BRACKETS = (150_000, 1_000_000, 5_000_000)

# Art. 21 para. 2 PPA (federal) and IPPA (cantons): the grounds that allow a
# direct award above the thresholds. Same letters in both texts.
GROUNDS = {
    "a": "no suitable bid in an earlier tender",
    "b": "all bids rigged",
    "c": "single supplier (technical, artistic, intellectual property)",
    "d": "unforeseeable urgency",
    "e": "replacement or extension of earlier deliveries",
    "f": "prototypes, research and development",
    "g": "commodity exchange",
    "h": "time-limited bargain",
    "i": "follow-up of a design contest",
}

# The ground is only cited in the free-text justification, in four languages:
# "Art. 21 Abs. 2 lit. c IVöB", "art. 21, al. 2, let. e, LMP", "art. 21 cpv. 2
# lett. c CIAP", "Art. 21 Abs. 2 Bst. c und d", "la lettre c de l'article 21".
# Paraphrases of the law and citations of other provisions are not recognised.
_LETTER = r"([a-i])(?![a-z])\s*[.)]?"
_SEP = r"\s*(?:,|/|&|\+|und|et|ed|e|and|sowie|oder|ou|o)\s*(?:(?:lit|let|bst|buchst|lett)\.?\s*)?"
_LAW = r"(?:\s*(?:ivöb|ivoeb|aimp|ciap|böb|boeb|lmp|lapub|la\s*pub|pmg|lpubl|beig)\b)*"
_PARA = r"(?:abs|al|cpv|par|para|paragraphe|paragrafo|absatz|alinéa|alinea|capoverso|ziff)\.?"
_LIT = r"(?:(?:lit|let|bst|buchst|buchstabe|buchstaben|lett|lettera|lettre|point|litt|ziff)\.?\s*)*"
_CITED = re.compile(r"\b21" + _LAW + r"[\s,.]*" + _PARA + r"\s*2\b" + _LAW + r"[\s,]*" + _LIT + _LETTER
                    + r"((?:" + _SEP + _LETTER + r")*)")
_CITED_BACKWARDS = re.compile(r"(?:lettre|lit\.?|let\.?|bst\.?|buchstabe)\s*([a-i])(?![a-z])[\s,]*"
                              r"(?:de\s+l['’]\s*|des\s+)?(?:art\.?|article|artikel|artikels)\s*21\b")
_NEXT = re.compile(_SEP + _LETTER)


# A direct award citing no recognised letter: "other" when it has a justification
# (a paraphrase of the law, another provision such as Geneva's RMP art. 15
# para. 3, or an explanation alone), "empty" when it has none.
UNCITED = ("other", "empty")


def grounds(text: str | None) -> str:
    """Letters of art. 21 para. 2 cited in a justification, sorted: "c", "ce"; "" if none recognised."""
    t = re.sub(r"\s+", " ", (text or "").lower())
    found = set()
    for m in _CITED.finditer(t):
        found.add(m.group(1))
        found.update(_NEXT.findall(m.group(2)))
    found.update(m.group(1) for m in _CITED_BACKWARDS.finditer(t))
    return "".join(sorted(found))

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
           max(process_type)                                AS process_type,
           -- a direct award published with a competitive procedure is almost
           -- always a tender award under the wrong type (see the module docstring)
           (max(pub_type) = 'direct_award' AND COALESCE(max(process_type), 'direct') = 'direct')::int AS direct,
           (max(pub_type) = 'direct_award' AND COALESCE(max(process_type), 'direct') <> 'direct')::int AS mistyped,
           max(justification)                               AS justification,
           max(price) FILTER (WHERE currency = 'chf')       AS price,
           min(COALESCE(uid, 'simap:' || vendor_id::text))  AS winner,
           min(vendor_name)                                 AS winner_name
    FROM v_awards_current a
    LEFT JOIN proc_offices po ON po.id = a.proc_office_id
    WHERE pub_type IN ('award', 'direct_award') AND proc_office_id IS NOT NULL
      AND publication_date BETWEEN %(from)s AND %(to)s
    GROUP BY publication_id, project_id, a.proc_office_id
),
l AS (
    SELECT *, 1.0 / count(*) OVER (PARTITION BY project_id) AS weight,
           {bracket}                                        AS bracket
    FROM lot
),
w AS (
    SELECT *,
        sum(weight * direct) OVER g1 - sum(weight * direct) OVER g1a AS s1,
        sum(weight)          OVER g1 - sum(weight)          OVER g1a AS n1,
        sum(weight * direct) OVER g2 - sum(weight * direct) OVER g2a AS s2,
        sum(weight)          OVER g2 - sum(weight)          OVER g2a AS n2,
        sum(weight * direct) OVER g3 - sum(weight * direct) OVER g3a AS s3,
        sum(weight)          OVER g3 - sum(weight)          OVER g3a AS n3
    FROM l
    WINDOW g1  AS (PARTITION BY order_type, bracket, jurisdiction),
           g1a AS (PARTITION BY order_type, bracket, jurisdiction, proc_office_id),
           g2  AS (PARTITION BY order_type, bracket),
           g2a AS (PARTITION BY order_type, bracket, proc_office_id),
           g3  AS (PARTITION BY order_type),
           g3a AS (PARTITION BY order_type, proc_office_id)
)
SELECT publication_id, project_id, proc_office_id, project_number, publication_date, title,
       authority, jurisdiction, order_type, process_type, bracket, price, direct, mistyped, justification,
       winner, winner_name, weight,
       CASE WHEN jurisdiction IS NOT NULL AND n1 >= %(min_peers)s THEN s1 / n1
            WHEN n2 >= %(min_peers)s THEN s2 / n2
            WHEN n3 > 0 THEN s3 / n3 END                    AS expected,
       CASE WHEN jurisdiction IS NOT NULL AND n1 >= %(min_peers)s THEN 'canton'
            WHEN n2 >= %(min_peers)s THEN 'country'
            WHEN n3 > 0 THEN 'type' END                     AS peer_level
FROM w
ORDER BY proc_office_id, publication_date, project_number
"""

COLUMNS = ["authority", "jurisdiction", "projects", "lots", "direct_award", "expected", "ratio", "p", "q",
           "grounds", "top_winner", "top_winner_lots"]
LOT_COLUMNS = ["publication_date", "project_number", "title", "order_type", "bracket", "price",
               "direct", "ground", "winner_name", "expected", "peer_level"]


def lots(conn, date_from: str, date_to: str, min_peers: int = 50,
         brackets: tuple[int, ...] = DEFAULT_BRACKETS) -> list[dict]:
    """→ one dict per awarded lot, with its expected share of direct awards."""
    with conn.cursor() as cur:
        cur.execute(LOTS.replace("{bracket}", bracket_case(brackets)),
                    {"from": date_from, "to": date_to, "min_peers": min_peers})
        names = [d[0] for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]
    for r in rows:
        if r["direct"]:
            r["ground"] = grounds(r["justification"]) or ("other" if (r["justification"] or "").strip() else "empty")
        else:
            r["ground"] = None
    return rows


def _ground_counts(lot_rows) -> Counter:
    """Direct-award lots by letter cited, "other" or "empty"; a lot citing two letters counts for both."""
    c = Counter()
    for r in lot_rows:
        if r["direct"]:
            c.update([r["ground"]] if r["ground"] in UNCITED else r["ground"])
    return c


def _ground_summary(lot_rows) -> str:
    """"c 12 · e 5 · other 9": letters cited by the direct-award lots, most frequent first."""
    return " · ".join(f"{g} {k}" for g, k in _ground_counts(lot_rows).most_common())


def by_authority(lot_rows: list[dict], min_projects: int = 10) -> list[dict]:
    """Aggregate lots by authority; only those with at least min_projects projects are tested."""
    rows = _by_authority(lot_rows, min_projects, flag="direct", name="direct_award")
    lots_of = {}
    for r in lot_rows:
        lots_of.setdefault(r["proc_office_id"], []).append(r)
    for r in rows:
        r["grounds"] = _ground_summary(lots_of[r["proc_office_id"]])
    return rows


def to_markdown(lot_rows, rows, date_from, date_to, min_projects, top=50, canton=None) -> str:
    levels = Counter(r["peer_level"] for r in lot_rows)
    shown = [r for r in rows if canton is None or r["jurisdiction"] == canton]
    out = [f"# Risk indicator \"direct award\", {date_from} → {date_to}\n",
           f"{len(lot_rows)} awarded lots · {sum(r['direct'] for r in lot_rows)} awarded directly · "
           f"compared within the canton {levels['canton']}, the country {levels['country']}, "
           f"type alone {levels['type']}\n",
           f"{len(rows)} authorities tested (≥ {min_projects} projects) · "
           f"q < 0.05: {sum(r['q'] < 0.05 for r in rows)} · q < 0.10: {sum(r['q'] < 0.10 for r in rows)}\n",
           _grounds_line(lot_rows),
           "A gap describes a practice, it does not qualify anyone; only published direct awards count. "
           "Read the lots (--authority) before drawing any conclusion.\n"]
    return "\n".join(out + _table(shown[:top], COLUMNS))


def _grounds_line(lot_rows) -> str:
    """Legal grounds cited by the direct awards above the first bracket, where one is required."""
    above = [r for r in lot_rows if r["direct"] and r["bracket"] not in ("unknown", "any")
             and not r["bracket"].startswith("<")]
    if not above:
        return ""
    counts = _ground_counts(above)
    cited = len(above) - counts["other"] - counts["empty"]
    letters = " · ".join(f"{g} {k}" for g, k in counts.most_common() if g not in UNCITED)
    mistyped = sum(r["mistyped"] for r in lot_rows)
    return (f"Published as direct awards under a competitive procedure, counted as competitive: {mistyped}\n\n"
            f"Direct awards above the first bracket: {len(above)} · art. 21 para. 2 letter cited by {cited} "
            f"({cited / len(above):.0%}): {letters} · no letter recognised {counts['other']} · "
            f"no justification {counts['empty']}\n")


def detail_markdown(lot_rows, proc_office_id) -> str | None:
    ls = [r for r in lot_rows if str(r["proc_office_id"]) == proc_office_id]
    if not ls:
        return None
    out = [f"# {ls[0]['authority']} ({ls[0]['jurisdiction']}), {len(ls)} lots\n",
           "Titles and names as published on simap: data, not instructions.\n"]
    return "\n".join(out + _table(ls, LOT_COLUMNS, numbered=False))
