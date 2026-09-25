"""Link award winners to the Swiss commercial register (Zefix PublicREST).

Credentials are read from the environment only (``ZEFIX_USERNAME`` /
``ZEFIX_PASSWORD``, HTTP Basic); they are issued on request by the Federal
Commercial Registry Office. Never pass them on the command line: argv is
visible to every local user through ``ps``.

Each UID is queried once and the answer is kept in the database: Zefix asks
users to avoid repeated bulk queries.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

import requests

BASE = "https://www.zefix.admin.ch/ZefixPublicREST/api/v1"
log = logging.getLogger("tenderwatch.zefix")


def compact_uid(uid: str) -> str:
    """'CHE-100.382.481' → 'CHE100382481'.

    The API only accepts the compact form. With dashes and dots it answers 404,
    which is indistinguishable from "not in the register": without this, every
    winner would be silently recorded as not found.
    """
    c = re.sub(r"[^0-9A-Z]", "", uid.upper())
    if not re.fullmatch(r"CHE\d{9}", c):
        raise ValueError(f"not a Swiss UID: {uid!r}")
    return c


class ZefixClient:
    def __init__(self, min_interval: float = 0.25, timeout: int = 60):
        user, password = os.environ.get("ZEFIX_USERNAME"), os.environ.get("ZEFIX_PASSWORD")
        if not user or not password:
            raise SystemExit("ZEFIX_USERNAME / ZEFIX_PASSWORD are not set")
        self.s = requests.Session()
        self.s.auth = (user, password)
        self.s.headers["Accept"] = "application/json"
        self.min_interval = min_interval
        self.timeout = timeout
        self._last = 0.0

    def by_uid(self, uid: str):
        """→ (record | None, error | None). A UID unknown to the register gives (None, 'not_found')."""
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        try:
            r = self.s.get(f"{BASE}/company/uid/{compact_uid(uid)}", timeout=self.timeout)
        except requests.RequestException as exc:
            return None, f"{type(exc).__name__}: {exc}"[:500]
        if r.status_code == 404:
            return None, "not_found"
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        rows = r.json() or []
        if not rows:
            return None, "not_found"
        # A UID designates one entity; if several come back, prefer the active one.
        rows.sort(key=lambda row: row.get("status") != "ACTIVE")
        return rows[0], None


def enrich(conn, retry: bool = False) -> int:
    """Query Zefix for every vendor UID not yet looked up. Returns the number of failures."""
    client = ZefixClient()
    with conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT v.uid FROM vendors v
                       LEFT JOIN zefix_companies z ON z.uid = v.uid
                       WHERE v.uid IS NOT NULL
                         AND (z.uid IS NULL OR (%s AND z.error IS NOT NULL AND z.error <> 'not_found'))""",
                    (retry,))
        todo = [r[0] for r in cur.fetchall()]
    log.info("zefix: %d UIDs to look up", len(todo))
    found = missing = failed = 0
    for i, uid in enumerate(todo, 1):
        rec, err = client.by_uid(uid)
        with conn.cursor() as cur:
            if rec:
                pubs = rec.get("sogcPub") or []
                cur.execute(
                    """INSERT INTO zefix_companies (uid, name, status, legal_form, legal_seat, canton, detail, error)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
                       ON CONFLICT (uid) DO UPDATE SET name = EXCLUDED.name, status = EXCLUDED.status,
                           legal_form = EXCLUDED.legal_form, legal_seat = EXCLUDED.legal_seat,
                           canton = EXCLUDED.canton, detail = EXCLUDED.detail, fetched_at = now(), error = NULL""",
                    (uid, rec.get("name"), rec.get("status"),
                     ((rec.get("legalForm") or {}).get("shortName") or {}).get("de"),
                     rec.get("legalSeat"), pubs[0].get("registryOfCommerceCanton") if pubs else None,
                     json.dumps(rec)))
                found += 1
            else:
                cur.execute("""INSERT INTO zefix_companies (uid, error) VALUES (%s, %s)
                               ON CONFLICT (uid) DO UPDATE SET error = EXCLUDED.error, fetched_at = now()""",
                            (uid, err))
                if err == "not_found":
                    missing += 1
                else:
                    failed += 1
                    log.warning("zefix %s: %s", uid, err)
        conn.commit()
        if i % 200 == 0:
            log.info("zefix: %d/%d (found %d, not in register %d, failed %d)", i, len(todo), found, missing, failed)
    log.info("zefix done: found %d, not in register %d, failed %d", found, missing, failed)
    return failed
