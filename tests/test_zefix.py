import pytest

from tenderwatch.zefix import compact_uid


def test_compact_uid_is_what_the_api_accepts():
    # With dashes and dots, Zefix answers 404: indistinguishable from "not found".
    assert compact_uid("CHE-100.382.481") == "CHE100382481"
    assert compact_uid("che 100 382 481") == "CHE100382481"


def test_compact_uid_rejects_non_swiss():
    with pytest.raises(ValueError):
        compact_uid("DE123456789")
