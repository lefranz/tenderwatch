import pytest

from tenderwatch import db, single_bid


def test_binomial_upper_tail():
    # P(X >= 4), X ~ B(10, 0.1) = 0.0128; the normal approximation would give 0.0007
    assert single_bid.binom_sf(4, 10, 0.1) == pytest.approx(0.012795, abs=1e-6)
    assert single_bid.binom_sf(0, 10, 0.1) == 1.0


def test_benjamini_hochberg():
    q = single_bid.benjamini_hochberg([0.01, 0.04, 0.03, 0.5])
    assert q == pytest.approx([0.04, 0.04 * 4 / 3, 0.04 * 4 / 3, 0.5])


def test_brackets():
    assert single_bid.parse_brackets("250k, 1M,5M") == single_bid.DEFAULT_BRACKETS
    assert single_bid.parse_brackets("100000,1.5M") == (100_000, 1_500_000)
    assert single_bid.parse_brackets("none") == ()
    for bad in ("1M,250k", "250k,250k", "0,1M", "abc"):
        with pytest.raises(ValueError):
            single_bid.parse_brackets(bad)
    case = single_bid.bracket_case((100_000, 1_500_000))
    assert "'<100k'" in case and "'100k-1.5M'" in case and "'>=1.5M'" in case
    assert single_bid.bracket_case(()) == "'any'"


def lot(po, single, expected, weight=1.0, winner="W"):
    return {"proc_office_id": po, "authority": po, "jurisdiction": "GE", "weight": weight,
            "single": single, "expected": expected, "winner": winner, "winner_name": winner}


def test_a_project_with_lots_weighs_one():
    # 4 lots of one project, all single bid, + 9 one-lot projects without: 1 single bid out of 10
    lots = [lot("A", 1, 0.1, 0.25) for _ in range(4)] + [lot("A", 0, 0.1) for _ in range(9)]
    (r,) = single_bid.by_authority(lots, min_projects=10)
    assert (r["projects"], r["lots"], r["single_bid"], r["expected"], r["ratio"]) == (10, 13, 1, 1, 1)


def test_threshold_and_top_winner():
    lots = [lot("A", 1, 0.1, winner="X" if i < 3 else "Y") for i in range(4)]
    lots += [lot("A", 0, 0.1) for _ in range(6)] + [lot("B", 1, 0.1)]
    (r,) = single_bid.by_authority(lots, min_projects=10)
    assert (r["proc_office_id"], r["top_winner"], r["top_winner_lots"]) == ("A", "X", 3)


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
                order_type text, process_type text, n_submissions int, price numeric, currency text,
                uid text, vendor_id text, vendor_name text, pub_type text)""")
        cur.execute("CREATE TEMP TABLE proc_offices (id text, name text)")
    yield c
    c.rollback()
    c.close()


def add(cur, pub, project, po, jur, n_sub, pub_type="award", price=100000):
    cur.execute("INSERT INTO v_awards_current VALUES (%s,%s,%s,%s,'2026-03-01','t',%s,%s,'construction',"
                "'open',%s,%s,'chf',NULL,'v','V',%s)", (pub, project, po, project, po, jur, n_sub, price, pub_type))


def lots_by_pub(conn, min_peers, brackets=single_bid.DEFAULT_BRACKETS):
    rows = single_bid.lots(conn, "2026-01-01", "2026-12-31", min_peers, brackets)
    return {r["publication_id"]: r for r in rows}


def test_expected_excludes_the_authority_and_falls_back(conn):
    with conn.cursor() as cur:
        for i in range(4):                       # A (GE): 4 projects, all single bid
            add(cur, f"a{i}", f"pa{i}", "A", "GE", 1)
        add(cur, "b0", "pb0", "B", "GE", 1)      # B (GE): 1 out of 4
        for i in range(1, 4):
            add(cur, f"b{i}", f"pb{i}", "B", "GE", 3)
        for i in range(4):                       # C (VD): none
            add(cur, f"c{i}", f"pc{i}", "C", "VD", 2)
        add(cur, "d0", "pd0", "D", "GE", 1, pub_type="direct_award")   # direct award: out of scope
    r = lots_by_pub(conn, min_peers=4)
    assert "d0" not in r
    a = r["a0"]                                  # Geneva peers without A = B alone: 1/4
    assert (a["peer_level"], float(a["expected"])) == ("canton", 0.25)
    b = r["b0"]                                  # Geneva peers without B = A: 4/4
    assert (b["peer_level"], float(b["expected"])) == ("canton", 1.0)
    r = lots_by_pub(conn, min_peers=5)           # Geneva group too small: the country, without A
    assert (r["a0"]["peer_level"], float(r["a0"]["expected"])) == ("country", 0.125)


def test_brackets_set_the_comparison_group(conn):
    with conn.cursor() as cur:
        add(cur, "a0", "pa0", "A", "GE", 1, price=100000)
        add(cur, "b0", "pb0", "B", "GE", 1, price=100000)      # same bracket as a0 by default
        add(cur, "b1", "pb1", "B", "GE", 3, price=200000)
        add(cur, "b2", "pb2", "B", "GE", 3, price=2000000)
    r = lots_by_pub(conn, min_peers=1)                         # < 250k: b0, b1 → 1/2
    assert (r["a0"]["bracket"], float(r["a0"]["expected"])) == ("<250k", 0.5)
    r = lots_by_pub(conn, min_peers=1, brackets=(150_000,))    # < 150k: b0 → 1/1
    assert (r["a0"]["bracket"], float(r["a0"]["expected"])) == ("<150k", 1.0)
    r = lots_by_pub(conn, min_peers=1, brackets=())            # price ignored: 1/3
    assert (r["a0"]["bracket"], float(r["a0"]["expected"])) == ("any", pytest.approx(1 / 3))
