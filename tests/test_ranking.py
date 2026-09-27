import pytest

from tenderwatch import db, ranking

# (project, publication, winner, price) — temporary tables: pg_temp comes before
# public in the search path, so the real view is neither read nor touched.
ROWS = [
    # framework agreement "all lots combined": 2 lots × 2 winners, same amount everywhere
    ("P1", "P1-lot1", "A", 600), ("P1", "P1-lot1", "B", 600),
    ("P1", "P1-lot2", "A", 600), ("P1", "P1-lot2", "B", 600),
    # one price per winner: what each obtained
    ("P2", "P2", "A", 100), ("P2", "P2", "B", 150),
    # a single winner, the same total copied on its two lots
    ("P3", "P3-lot1", "B", 40), ("P3", "P3-lot2", "B", 40),
]


@pytest.fixture
def conn():
    try:
        c = db.connect()
    except Exception as e:  # no local database
        pytest.skip(f"database unavailable: {e}")
    with c.cursor() as cur:
        cur.execute("""
            CREATE TEMP TABLE v_awards_current (
                publication_id text, project_id text, vendor_id text, uid text,
                vendor_name text, vendor_canton text, proc_office_id text, pub_type text,
                n_submissions int, price numeric, currency text, vat_type text,
                publication_date date)""")
        cur.execute("CREATE TEMP TABLE zefix_companies (uid text, name text, legal_seat text,"
                    " canton text, status text, error text)")
        for proj, pub, vendor, price in ROWS:
            cur.execute("INSERT INTO v_awards_current VALUES (%s,%s,%s,NULL,%s,NULL,'office','award',"
                        "2,%s,'chf','full','2026-03-01')", (pub, proj, vendor, vendor, price))
    yield c
    c.rollback()
    c.close()


def test_shared_amount_counted_once_and_kept_out_of_published_amount(conn):
    quality, rows = ranking.ranking(conn, "2026-01-01", "2026-12-31")
    by = {r["company"]: r for r in rows}
    a, b = by["A"], by["B"]
    assert (a["awards"], a["published_amount_chf"]) == (3, 100)
    assert (a["shared_amount_projects"], a["shared_amount_chf"]) == (1, 600)
    assert (b["awards"], b["published_amount_chf"]) == (5, 150)
    assert (b["shared_amount_projects"], b["shared_amount_chf"]) == (2, 640)
    assert quality["shared_amount_projects"] == 2
