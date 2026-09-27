import pytest

from tenderwatch import db, ranking

# (project, publication, winner, price, jurisdiction) — temporary tables: pg_temp comes before
# public in the search path, so the real view is neither read nor touched.
ROWS = [
    # framework agreement "all lots combined": 2 lots × 2 winners, same amount everywhere
    ("P1", "P1-lot1", "A", 600, "GE"), ("P1", "P1-lot1", "B", 600, "GE"),
    ("P1", "P1-lot2", "A", 600, "GE"), ("P1", "P1-lot2", "B", 600, "GE"),
    # one price per winner: what each obtained
    ("P2", "P2", "A", 100, "CH"), ("P2", "P2", "B", 150, "CH"),
    # a single winner, the same total copied on its two lots
    ("P3", "P3-lot1", "B", 40, "CH"), ("P3", "P3-lot2", "B", 40, "CH"),
]
# Winners A and B are based in Geneva.


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
                publication_date date, jurisdiction text, price_zero bool DEFAULT false)""")
        cur.execute("CREATE TEMP TABLE zefix_companies (uid text, name text, legal_seat text,"
                    " canton text, status text, error text)")
        for proj, pub, vendor, price, jur in ROWS:
            cur.execute("INSERT INTO v_awards_current VALUES (%s,%s,%s,NULL,%s,'GE',%s,'award',"
                        "2,%s,'chf','full','2026-03-01',%s)", (pub, proj, vendor, vendor, jur, price, jur))
    yield c
    c.rollback()
    c.close()


def test_shared_amount_counted_once_and_kept_out_of_published_amount(conn):
    quality, rows = ranking.ranking(conn, "2026-01-01", "2026-12-31")
    by = {r["company"]: r for r in rows}
    a, b = by["A"], by["B"]
    assert (a["awards"], a["projects"], a["published_amount_chf"]) == (3, 2, 100)
    assert (a["shared_amount_projects"], a["shared_amount_chf"]) == (1, 600)
    assert (b["awards"], b["projects"], b["published_amount_chf"]) == (5, 3, 150)
    assert (b["shared_amount_projects"], b["shared_amount_chf"]) == (2, 640)
    assert quality["shared_amount_projects"] == 2


def test_canton_filter_keeps_only_its_authorities(conn):
    _, rows = ranking.ranking(conn, "2026-01-01", "2026-12-31", canton="GE")
    assert {r["company"]: r["awards"] for r in rows} == {"A": 2, "B": 2}
    quality, _ = ranking.ranking(conn, "2026-01-01", "2026-12-31", canton="CH")
    assert (quality["awards"], quality["shared_amount_projects"]) == (3, 1)


def test_by_canton_keeps_the_confederation_apart(conn):
    rows = {r["canton"]: r for r in ranking.by_canton(conn, "2026-01-01", "2026-12-31")}
    assert set(rows) == {"GE", "CH"}
    assert (rows["GE"]["awards"], rows["GE"]["winners"], rows["GE"]["pct_winner_same_canton"]) == (2, 2, 100)
    assert (rows["CH"]["awards"], rows["CH"]["pct_winner_same_canton"]) == (3, None)


def test_price_published_as_zero_counts_as_without_price(conn):
    with conn.cursor() as cur:  # the view yields NULL and price_zero for a "confidential" 0
        cur.execute("INSERT INTO v_awards_current VALUES ('P4','P4','C',NULL,'C','GE','GE','award',"
                    "2,NULL,NULL,NULL,'2026-03-01','GE',true)")
    quality, _ = ranking.ranking(conn, "2026-01-01", "2026-12-31")
    assert (quality["without_price"], quality["price_zero"], quality["shared_amount_projects"]) == (1, 1, 2)
