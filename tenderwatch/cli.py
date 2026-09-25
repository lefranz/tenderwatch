"""Command line: ``tenderwatch <command>``.

    tenderwatch init-db
    tenderwatch collect all --from 2026-01-01 --to 2026-09-30
    tenderwatch zefix
    tenderwatch ranking --order amount --top 100 --csv ranking.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import sys

from . import collect, db, ranking, zefix
from .simap import Client


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tenderwatch", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create tables and views (idempotent)")

    c = sub.add_parser("collect", help="download from simap.ch")
    c.add_argument("step", choices=["search", "history", "details", "vendors", "all"])
    c.add_argument("--from", dest="date_from", type=dt.date.fromisoformat)
    c.add_argument("--to", dest="date_to", type=dt.date.fromisoformat, default=dt.date.today())
    c.add_argument("--limit", type=int, help="details: at most N publications")
    c.add_argument("--interval", type=float, default=0.35, help="minimum seconds between two calls")

    z = sub.add_parser("zefix", help="link winners' UIDs to the commercial register")
    z.add_argument("--retry", action="store_true", help="retry UIDs that failed (not 'not_found')")

    r = sub.add_parser("ranking", help="rank award winners")
    r.add_argument("--from", dest="date_from", default=f"{dt.date.today().year}-01-01")
    r.add_argument("--to", dest="date_to", default=f"{dt.date.today().year}-12-31")
    r.add_argument("--order", choices=list(ranking.ORDERS), default="count")
    r.add_argument("--top", type=int, default=50)
    r.add_argument("--csv", help="also write the ranking to this CSV file")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(message)s")
    conn = db.connect()

    if args.command == "init-db":
        db.init_schema(conn)
    elif args.command == "collect":
        if args.step in ("search", "all") and not args.date_from:
            ap.error("--from is required for search/all")
        client = Client(min_interval=args.interval)
        if args.step in ("search", "all"):
            collect.step_search(conn, client, args.date_from, args.date_to)
        if args.step in ("history", "all"):
            collect.step_history(conn, client)
        if args.step in ("details", "all"):
            collect.step_details(conn, client, args.limit)
        if args.step in ("vendors", "all"):
            collect.step_vendors(conn, client)
    elif args.command == "zefix":
        if zefix.enrich(conn, retry=args.retry):
            return 1
    elif args.command == "ranking":
        quality, rows = ranking.ranking(conn, args.date_from, args.date_to, args.order, args.top)
        if args.csv:
            with open(args.csv, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ranking.COLUMNS)
                w.writeheader()
                w.writerows(rows)
            print(f"{len(rows)} rows → {args.csv}", file=sys.stderr)
        print(ranking.to_markdown(quality, rows, args.date_from, args.date_to, args.order))
    return 0


if __name__ == "__main__":
    sys.exit(main())
