"""Minimal client for the public simap.ch API (anonymous, read-only).

Spec: https://www.simap.ch/api/specifications/simap.yaml
Only endpoints that answer without a token are used. See docs/simap-api.md.
"""
from __future__ import annotations

import logging
import os
import time
import urllib.parse

import requests

BASE = "https://www.simap.ch/api"
USER_AGENT = os.environ.get("TENDERWATCH_USER_AGENT", "tenderwatch/0.1 (+https://github.com/lefranz/tenderwatch)")

# The search endpoint refuses a query without at least one filter. These ten
# sub-types cover everything: over the same window, this filter, the
# publication-type filter and the process-type filter return exactly the same
# projects (779 vs 779 vs 779, measured on 2026-09-25).
ALL_SUBTYPES = [
    "construction", "service", "supply",
    "project_competition", "idea_competition", "overall_performance_competition",
    "project_study", "idea_study", "overall_performance_study",
    "request_for_information",
]

log = logging.getLogger("tenderwatch")


class NotFound(Exception):
    pass


class Client:
    def __init__(self, min_interval: float = 0.35, timeout: int = 60):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.s.headers["Accept"] = "application/json"
        self.min_interval = min_interval
        self.timeout = timeout
        self._last = 0.0
        self.calls = 0

    def get(self, path: str, params: dict | None = None):
        url = BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        for attempt in range(6):
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.calls += 1
            try:
                r = self.s.get(url, timeout=self.timeout)
            except requests.RequestException as exc:
                log.warning("network error (%s), attempt %d: %s", type(exc).__name__, attempt + 1, url)
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code in (400, 404):
                raise NotFound(f"HTTP {r.status_code} {url}")
            # 429 and 5xx: slow down and retry
            log.warning("HTTP %d, attempt %d: %s", r.status_code, attempt + 1, url)
            time.sleep(10 * (attempt + 1))
        raise RuntimeError(f"giving up after 6 attempts: {url}")

    def search(self, date_from: str, date_until: str):
        """Every project whose *newest* publication falls in the window.

        Rolling pagination: 20 projects per page, ``lastItem`` cursor.
        """
        last = None
        while True:
            params = {
                "projectSubTypes": ALL_SUBTYPES,
                "newestPublicationFrom": date_from,
                "newestPublicationUntil": date_until,
            }
            if last:
                params["lastItem"] = last
            d = self.get("/publications/v2/project/project-search", params)
            projects = d.get("projects") or []
            yield from projects
            last = (d.get("pagination") or {}).get("lastItem")
            if len(projects) < 20 or not last:
                return

    def past_publications(self, publication_id: str, lot_id: str | None = None):
        # For a lot publication, lotId is mandatory: without it the API answers 400.
        params = {"lotId": lot_id} if lot_id else None
        d = self.get(f"/publications/v1/publication/{publication_id}/past-publications", params)
        return d.get("pastPublications") or []

    def publication_detail(self, project_id: str, publication_id: str):
        return self.get(f"/publications/v1/project/{project_id}/publication-details/{publication_id}")

    def vendor_public(self, vendor_id: str):
        return self.get(f"/vendors/v1/vendor/{vendor_id}/public")
