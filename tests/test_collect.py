import datetime as dt

from tenderwatch.collect import current_refs, months, normalize_uid, too_many_missing


def test_normalize_uid():
    assert normalize_uid("CHE-100.382.481") == "CHE-100.382.481"
    assert normalize_uid("CHE100382481") == "CHE-100.382.481"
    assert normalize_uid("che-100.382.481 MWST") == "CHE-100.382.481"
    assert normalize_uid(None) is None
    assert normalize_uid("DE123456789") is None


def test_months_cover_the_window_without_gap():
    w = list(months(dt.date(2026, 1, 15), dt.date(2026, 3, 10)))
    assert w == [(dt.date(2026, 1, 15), dt.date(2026, 1, 31)),
                 (dt.date(2026, 2, 1), dt.date(2026, 2, 28)),
                 (dt.date(2026, 3, 1), dt.date(2026, 3, 10))]


def test_one_lot_is_one_publication():
    p = {"publicationId": "a", "lots": [
        {"publicationId": "a", "lotId": "L1", "lotNumber": 1, "pubType": "award"},
        {"publicationId": "b", "lotId": "L2", "lotNumber": 2, "pubType": "award"}]}
    assert [r["id"] for r in current_refs(p)] == ["a", "b"]
    assert [r["lot_id"] for r in current_refs({"publicationId": "c", "lots": []})] == [None]


def test_an_empty_search_does_not_mark_the_window_as_gone():
    assert too_many_missing(3909, 3909)
    assert too_many_missing(400, 3909)
    assert not too_many_missing(12, 3909)
    assert not too_many_missing(15, 100)   # floor: a few withdrawals in a small window
