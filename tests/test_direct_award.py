import pytest

from tenderwatch import db, direct_award


@pytest.fixture
def conn():
    try:
        c = db.connect()
    except Exception as e:  # no local database
        pytest.skip(f"database unavailable: {e}")
    with c.cursor() as cur:  # pg_temp comes before public: the real view is not read
        cur.execute("""
            CREATE TEMP TABLE v_awards_current (
                publication_id text, project_id text, proc_office_id text, project_number text,
                publication_date date, title text, proc_office_name text, jurisdiction text,
                order_type text, process_type text, justification text, price numeric, currency text,
                uid text, vendor_id text, vendor_name text, pub_type text)""")
        cur.execute("CREATE TEMP TABLE proc_offices (id text, name text)")
    yield c
    c.rollback()
    c.close()


def add(cur, pub, project, po, jur, direct, price=500000, order_type="service"):
    pub_type, process = ("direct_award", "direct") if direct else ("award", "open")
    cur.execute("INSERT INTO v_awards_current VALUES (%s,%s,%s,%s,'2026-03-01','t',%s,%s,%s,%s,NULL,%s,'chf',"
                "NULL,'v','V',%s)", (pub, project, po, project, po, jur, order_type, process, price, pub_type))


def lots_by_pub(conn, min_peers, brackets=direct_award.DEFAULT_BRACKETS):
    rows = direct_award.lots(conn, "2026-01-01", "2026-12-31", min_peers, brackets)
    return {r["publication_id"]: r for r in rows}


def test_expected_excludes_the_authority_and_falls_back(conn):
    with conn.cursor() as cur:
        for i in range(4):                       # A (GE): 4 direct awards
            add(cur, f"a{i}", f"pa{i}", "A", "GE", True)
        add(cur, "b0", "pb0", "B", "GE", True)   # B (GE): 1 out of 4
        for i in range(1, 4):
            add(cur, f"b{i}", f"pb{i}", "B", "GE", False)
        for i in range(4):                       # C (VD): none
            add(cur, f"c{i}", f"pc{i}", "C", "VD", False)
    r = lots_by_pub(conn, min_peers=4)
    assert (r["a0"]["direct"], r["b1"]["direct"]) == (1, 0)
    assert (r["a0"]["peer_level"], float(r["a0"]["expected"])) == ("canton", 0.25)
    assert (r["b0"]["peer_level"], float(r["b0"]["expected"])) == ("canton", 1.0)
    r = lots_by_pub(conn, min_peers=5)           # Geneva group too small: the country, without A
    assert (r["a0"]["peer_level"], float(r["a0"]["expected"])) == ("country", 0.125)


def test_type_and_bracket_set_the_comparison_group(conn):
    with conn.cursor() as cur:
        add(cur, "a0", "pa0", "A", "GE", True, price=100000)
        add(cur, "b0", "pb0", "B", "GE", True, price=120000)                        # same group
        add(cur, "b1", "pb1", "B", "GE", False, price=900000)                       # other bracket
        add(cur, "b2", "pb2", "B", "GE", False, price=110000, order_type="construction")  # other type
    r = lots_by_pub(conn, min_peers=1)
    assert (r["a0"]["bracket"], float(r["a0"]["expected"])) == ("<150k", 1.0)
    r = lots_by_pub(conn, min_peers=1, brackets=())                                 # price ignored: b0, b1
    assert float(r["a0"]["expected"]) == 0.5


def test_lots_of_a_project_weigh_one_and_authorities_are_tested(conn):
    with conn.cursor() as cur:
        for i in range(4):                       # one project in 4 lots, all direct
            add(cur, f"a{i}", "pa", "A", "GE", True)
        for i in range(9):
            add(cur, f"a1{i}", f"pa1{i}", "A", "GE", False)
        for i in range(20):                      # peers: 2 direct out of 20
            add(cur, f"b{i}", f"pb{i}", "B", "GE", i < 2)
    rows = direct_award.by_authority(lots_by_pub(conn, min_peers=1).values(), min_projects=10)
    a = next(r for r in rows if r["proc_office_id"] == "A")
    assert (a["projects"], a["lots"], a["direct_award_lots"], a["direct_award"], a["expected"]) == (10, 13, 4, 1, 1)
    assert all(0 <= r["q"] <= 1 for r in rows)
