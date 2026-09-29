"""Collect simap.ch publications into the database.

Five steps, each resumable (whatever is already stored is skipped):

1. ``search``  — projects whose newest publication falls in the window, month by month;
2. ``history`` — past publications of each project, lot by lot;
3. ``details`` — raw detail of every publication;
4. ``vendors`` — public profile of every award winner (carries the UID);
5. ``offices`` — every contracting authority and its type, in one call.

For a daily run:

- ``daily``   — ``search`` over a rolling window, then the four other steps, and
  flags the projects of the window that the search no longer returns;
- ``refresh`` — downloads again the detail of recent publications (weekly).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re

from .simap import Client, NotFound

log = logging.getLogger("tenderwatch")


def months(first: dt.date, last: dt.date):
    """Monthly windows [start, end] covering first..last."""
    cur = first.replace(day=1)
    while cur <= last:
        nxt = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield max(cur, first), min(nxt - dt.timedelta(days=1), last)
        cur = nxt


def content_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize_uid(raw: str | None) -> str | None:
    """'CHE-100.382.481', 'CHE100382481', 'CHE-100.382.481 MWST' → 'CHE-100.382.481'."""
    if not raw:
        return None
    m = re.search(r"CHE\D*(\d{3})\D*(\d{3})\D*(\d{3})", raw.upper())
    return f"CHE-{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else None


def current_refs(project: dict):
    """Current publications of a project, from the search result: one per lot, else one."""
    lots = project.get("lots") or []
    if lots:
        for lot in lots:
            yield {
                "id": lot["publicationId"], "lot_id": lot.get("lotId"), "lot_number": lot.get("lotNumber"),
                "publication_number": lot.get("publicationNumber"), "pub_type": lot.get("pubType"),
                "publication_date": lot.get("publicationDate"), "corrected": lot.get("corrected"),
            }
    else:
        yield {
            "id": project["publicationId"], "lot_id": None, "lot_number": None,
            "publication_number": project.get("publicationNumber"), "pub_type": project.get("pubType"),
            "publication_date": project.get("publicationDate"), "corrected": project.get("corrected"),
        }


UPSERT_PUB = """
INSERT INTO publications (id, project_id, lot_id, lot_number, publication_number, pub_type, publication_date, corrected)
VALUES (%(id)s, %(project_id)s, %(lot_id)s, %(lot_number)s, %(publication_number)s, %(pub_type)s, %(publication_date)s, %(corrected)s)
ON CONFLICT (id) DO UPDATE SET
    lot_id             = COALESCE(publications.lot_id, EXCLUDED.lot_id),
    lot_number         = COALESCE(publications.lot_number, EXCLUDED.lot_number),
    publication_number = COALESCE(EXCLUDED.publication_number, publications.publication_number),
    pub_type           = COALESCE(EXCLUDED.pub_type, publications.pub_type),
    publication_date   = COALESCE(EXCLUDED.publication_date, publications.publication_date),
    corrected          = COALESCE(EXCLUDED.corrected, publications.corrected)
"""


def step_search(conn, client: Client, first: dt.date, last: dt.date):
    # Month by month. Not an API constraint (a 3-month window returns exactly
    # the sum of the 3 months, measured 2026-09-25) but a restart after an
    # interruption then redoes one month only.
    total = 0
    for a, b in months(first, last):
        n = 0
        with conn.cursor() as cur:
            for p in client.search(a.isoformat(), b.isoformat()):
                cur.execute(
                    """INSERT INTO projects (id, project_number, newest_publication_date, search_json)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (id) DO UPDATE SET
                           project_number = EXCLUDED.project_number,
                           newest_publication_date = EXCLUDED.newest_publication_date,
                           search_json = EXCLUDED.search_json,
                           last_seen = now(),
                           missing_since = NULL""",
                    (p["id"], p["projectNumber"], p.get("publicationDate"), json.dumps(p)))
                for ref in current_refs(p):
                    cur.execute(UPSERT_PUB, {**ref, "project_id": p["id"]})
                n += 1
        conn.commit()
        total += n
        log.info("search %s → %s: %d projects", a, b, n)
    log.info("search done: %d projects, %d calls", total, client.calls)
    return total


# Beyond this share, a broken search is more likely than withdrawals: nothing is
# flagged. A search returning nothing must never mark the whole window as gone.
MAX_MISSING = 0.05


def too_many_missing(missing: int, expected: int) -> bool:
    return missing > max(20, MAX_MISSING * expected)


def mark_missing(conn, first: dt.date, last: dt.date, since) -> bool:
    """Flag the projects of the window that the search started at `since` did not see.

    A project's newest publication date only grows: a project that was in
    [first, last] and still exists is still in it. Returns False when too many
    projects are missing to be credible (nothing is flagged then).
    """
    with conn.cursor() as cur:
        cur.execute("""SELECT count(*), count(*) FILTER (WHERE last_seen < %s AND missing_since IS NULL)
                       FROM projects WHERE newest_publication_date BETWEEN %s AND %s""",
                    (since, first, last))
        expected, missing = cur.fetchone()
        if too_many_missing(missing, expected):
            log.error("missing: %d of %d projects not returned by the search, flagging suspended",
                      missing, expected)
            return False
        cur.execute("""UPDATE projects SET missing_since = now()
                       WHERE newest_publication_date BETWEEN %s AND %s
                         AND last_seen < %s AND missing_since IS NULL
                       RETURNING project_number""", (first, last, since))
        gone = [r[0] for r in cur.fetchall()]
    conn.commit()
    log.info("missing: %d new projects no longer returned by the search %s", len(gone), " ".join(gone[:20]))
    return True


def step_daily(conn, client: Client, last: dt.date, days: int = 60) -> bool:
    """Rolling-window search, flag missing projects, then the four other steps.

    Returns False if flagging was suspended (see ``mark_missing``).
    """
    first = last - dt.timedelta(days=days)
    with conn.cursor() as cur:
        cur.execute("SELECT now()")
        since = cur.fetchone()[0]
    conn.commit()
    step_search(conn, client, first, last)
    ok = mark_missing(conn, first, last, since)
    step_history(conn, client)
    step_details(conn, client)
    step_vendors(conn, client)
    step_offices(conn, client)
    return ok


def step_history(conn, client: Client):
    with conn.cursor() as cur:
        cur.execute("""SELECT id, search_json FROM projects
                       WHERE history_for IS DISTINCT FROM (search_json->>'publicationId')::uuid""")
        todo = cur.fetchall()
    log.info("history: %d projects to read", len(todo))
    for i, (pid, sj) in enumerate(todo, 1):
        with conn.cursor() as cur:
            for ref in current_refs(sj):
                try:
                    past = client.past_publications(ref["id"], ref["lot_id"])
                except NotFound as exc:
                    log.warning("history not found %s: %s", ref["id"], exc)
                    continue
                for pp in past:
                    cur.execute(UPSERT_PUB, {
                        "id": pp["id"], "project_id": pid, "lot_id": ref["lot_id"] if pp.get("lotNumber") else None,
                        "lot_number": pp.get("lotNumber"), "publication_number": pp.get("publicationNumber"),
                        "pub_type": pp.get("pubType"), "publication_date": pp.get("publicationDate"),
                        "corrected": pp.get("corrected")})
            cur.execute("UPDATE projects SET history_for = (search_json->>'publicationId')::uuid WHERE id = %s", (pid,))
        conn.commit()
        if i % 500 == 0:
            log.info("history: %d/%d", i, len(todo))
    log.info("history done, %d calls", client.calls)


def fetch_detail(conn, client: Client, pub_id, proj_id) -> str:
    """Download one detail; the previous version goes to publication_history if it changed.

    Returns "ok", "changed", "gone" (was stored, now not found) or "not_found".
    """
    with conn.cursor() as cur:
        try:
            d = client.publication_detail(str(proj_id), str(pub_id))
        except NotFound as exc:
            # A detail already stored is kept: only the error is recorded.
            cur.execute("UPDATE publications SET detail_error = %s WHERE id = %s RETURNING detail IS NOT NULL",
                        (str(exc)[:500], pub_id))
            had = cur.fetchone()[0]
            conn.commit()
            return "gone" if had else "not_found"
        h = content_hash(d)
        # Keep the previous version if the content changed (see schema.sql)
        cur.execute("""INSERT INTO publication_history (publication_id, content_hash, detail, fetched_at)
                       SELECT id, content_hash, detail, detail_fetched_at FROM publications
                       WHERE id = %s AND detail IS NOT NULL AND content_hash <> %s
                       ON CONFLICT DO NOTHING""", (pub_id, h))
        changed = cur.rowcount
        cur.execute("""UPDATE publications SET detail = %s, content_hash = %s,
                           detail_fetched_at = now(), detail_error = NULL
                       WHERE id = %s""", (json.dumps(d), h, pub_id))
    conn.commit()
    return "changed" if changed else "ok"


def step_details(conn, client: Client, limit: int | None = None):
    with conn.cursor() as cur:
        cur.execute("""SELECT id, project_id FROM publications
                       WHERE detail IS NULL AND detail_error IS NULL
                       ORDER BY publication_date DESC NULLS LAST""" + (f" LIMIT {int(limit)}" if limit else ""))
        todo = cur.fetchall()
    log.info("details: %d publications to download", len(todo))
    for i, (pub_id, proj_id) in enumerate(todo, 1):
        fetch_detail(conn, client, pub_id, proj_id)
        if i % 500 == 0:
            log.info("details: %d/%d (%d calls)", i, len(todo), client.calls)
    log.info("details done, %d calls", client.calls)


def step_refresh(conn, client: Client, since: dt.date):
    """Download again the detail of stored publications published since `since`.

    Measured 2026-09-29: a correction arrives as a NEW publication (caught by
    search and history), not in place. What changes in place is thinner (the TED
    link, added afterwards): hence a weekly pace rather than a daily one.
    """
    with conn.cursor() as cur:
        cur.execute("""SELECT id, project_id FROM publications
                       WHERE detail IS NOT NULL AND publication_date >= %s
                       ORDER BY publication_date DESC""", (since,))
        todo = cur.fetchall()
    log.info("refresh: %d publications since %s", len(todo), since)
    stats = {}
    for pub_id, proj_id in todo:
        r = fetch_detail(conn, client, pub_id, proj_id)
        stats[r] = stats.get(r, 0) + 1
        if r in ("changed", "gone"):
            log.warning("refresh %s: %s", pub_id, r)
    log.info("refresh done: %s, %d calls", stats, client.calls)


def step_vendors(conn, client: Client):
    with conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT (v->>'vendorId')::uuid
                       FROM publications p,
                            jsonb_array_elements(COALESCE(p.detail->'decision'->'vendors', '[]')) v
                       WHERE v->>'vendorId' IS NOT NULL
                         AND NOT EXISTS (SELECT 1 FROM vendors x WHERE x.id = (v->>'vendorId')::uuid)""")
        todo = [r[0] for r in cur.fetchall()]
    log.info("vendors: %d profiles to read", len(todo))
    for i, vid in enumerate(todo, 1):
        with conn.cursor() as cur:
            try:
                d = client.vendor_public(str(vid))
            except NotFound as exc:
                cur.execute("INSERT INTO vendors (id, error) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (vid, str(exc)[:500]))
            else:
                cur.execute("""INSERT INTO vendors (id, uid, name, detail) VALUES (%s, %s, %s, %s)
                               ON CONFLICT (id) DO UPDATE SET uid = EXCLUDED.uid, name = EXCLUDED.name,
                                   detail = EXCLUDED.detail, fetched_at = now(), error = NULL""",
                            (vid, normalize_uid(d.get("uidNo")), d.get("name"), json.dumps(d)))
        conn.commit()
        if i % 500 == 0:
            log.info("vendors: %d/%d", i, len(todo))
    log.info("vendors done, %d calls", client.calls)


def step_offices(conn, client: Client):
    # The whole list in one call, read again every time: a new authority shows
    # up there before its first publication.
    offices = client.proc_offices()
    with conn.cursor() as cur:
        for o in offices:
            cur.execute("""INSERT INTO proc_offices (id, type, name, institution_id, detail)
                           VALUES (%s, %s, %s, %s, %s)
                           ON CONFLICT (id) DO UPDATE SET type = EXCLUDED.type, name = EXCLUDED.name,
                               institution_id = EXCLUDED.institution_id, detail = EXCLUDED.detail,
                               last_seen = now()""",
                        (o["id"], o.get("type"), o.get("name"), o.get("institutionId"), json.dumps(o)))
    conn.commit()
    log.info("contracting authorities: %d", len(offices))
