"""Command line: ``tenderwatch <command>``.

    tenderwatch init-db
    tenderwatch collect all --from 2026-01-01 --to 2026-09-30
    tenderwatch collect daily              # rolling 60-day window, e.g. from cron
    tenderwatch collect refresh            # re-read details of the last 30 days, weekly
    tenderwatch zefix
    tenderwatch ranking --order amount --top 100 --csv ranking.csv
    tenderwatch ranking --canton GE        # authorities of Geneva (CH = federal)
    tenderwatch ranking --by-canton        # one row per canton
    tenderwatch single-bid                 # risk indicator, by contracting authority
    tenderwatch single-bid --authority <proc_office_id>   # its lots, one by one
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import sys

from . import collect, db, ranking, single_bid, zefix
from .simap import Client


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tenderwatch", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create tables and views (idempotent)")

    c = sub.add_parser("collect", help="download from simap.ch")
    c.add_argument("step", choices=["search", "history", "details", "vendors", "offices", "all",
                                    "daily", "refresh"])
    c.add_argument("--from", dest="date_from", type=dt.date.fromisoformat)
    c.add_argument("--to", dest="date_to", type=dt.date.fromisoformat, default=dt.date.today())
    c.add_argument("--days", type=int,
                   help="daily: rolling window (default 60); refresh: age of publications (default 30)")
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
    r.add_argument("--canton", type=str.upper, help="authorities of this canton (CH = federal)")
    r.add_argument("--by-canton", action="store_true", help="one row per canton of the contracting authority")

    s = sub.add_parser("single-bid", help="risk indicator: single bids by contracting authority")
    s.add_argument("--from", dest="date_from", default="2024-07-01")
    s.add_argument("--to", dest="date_to", default=dt.date.today().isoformat())
    s.add_argument("--min-projects", type=int, default=10, help="minimum projects to test an authority")
    s.add_argument("--min-peers", type=int, default=50, help="minimum projects in a comparison group")
    s.add_argument("--canton", type=str.upper, help="only show authorities of this canton (CH = federal)")
    s.add_argument("--top", type=int, default=50)
    s.add_argument("--csv", help="write every tested authority to this CSV file")
    s.add_argument("--authority", help="lot-by-lot detail of one authority (proc_office_id)")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(message)s")
    conn = db.connect()

    if args.command == "init-db":
        db.init_schema(conn)
    elif args.command == "collect":
        if args.step in ("search", "all") and not args.date_from:
            ap.error("--from is required for search/all")
        client = Client(min_interval=args.interval)
        if args.step == "daily":
            return 0 if collect.step_daily(conn, client, args.date_to, args.days or 60) else 1
        if args.step == "refresh":
            collect.step_refresh(conn, client, args.date_to - dt.timedelta(days=args.days or 30))
            return 0
        if args.step in ("search", "all"):
            collect.step_search(conn, client, args.date_from, args.date_to)
        if args.step in ("history", "all"):
            collect.step_history(conn, client)
        if args.step in ("details", "all"):
            collect.step_details(conn, client, args.limit)
        if args.step in ("vendors", "all"):
            collect.step_vendors(conn, client)
        if args.step in ("offices", "all"):
            collect.step_offices(conn, client)
    elif args.command == "zefix":
        if zefix.enrich(conn, retry=args.retry):
            return 1
    elif args.command == "ranking":
        if args.canton and args.by_canton:
            ap.error("--canton and --by-canton are mutually exclusive")
        if args.by_canton:
            rows = ranking.by_canton(conn, args.date_from, args.date_to)
            columns = ranking.CANTON_COLUMNS
        else:
            quality, rows = ranking.ranking(conn, args.date_from, args.date_to, args.order, args.top, args.canton)
            columns = ranking.COLUMNS
        if args.csv:
            with open(args.csv, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else columns)
                w.writeheader()
                w.writerows(rows)
            print(f"{len(rows)} rows → {args.csv}", file=sys.stderr)
        if args.by_canton:
            print(ranking.canton_markdown(rows, args.date_from, args.date_to))
        else:
            print(ranking.to_markdown(quality, rows, args.date_from, args.date_to, args.order, args.canton))
    elif args.command == "single-bid":
        lots = single_bid.lots(conn, args.date_from, args.date_to, args.min_peers)
        if args.authority:
            out = single_bid.detail_markdown(lots, args.authority)
            if out is None:
                print(f"no lot awarded after competition for {args.authority} in the period", file=sys.stderr)
                return 1
            print(out)
            return 0
        rows = single_bid.by_authority(lots, args.min_projects)
        if args.csv:
            with open(args.csv, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else single_bid.COLUMNS)
                w.writeheader()
                w.writerows(rows)
            print(f"{len(rows)} rows → {args.csv}", file=sys.stderr)
        print(single_bid.to_markdown(lots, rows, args.date_from, args.date_to, args.min_projects,
                                     args.top, args.canton))
    return 0


if __name__ == "__main__":
    sys.exit(main())
