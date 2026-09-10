"""Unit tests for vendorline_docs._walk_json_for_docs (pure, no browser)."""

from vendorline_docs import _walk_json_for_docs


def _names(payload):
    acc = []
    _walk_json_for_docs(payload, acc)
    # collapse the JSON:API double-hit (attributes dict also matches on filename)
    out = {}
    for d in acc:
        key = (d["name"], d["url"])
        if key not in out or (d["id"] and not out[key]["id"]):
            out[key] = d
    return list(out.values())


def test_jsonapi_bid_document_by_id():
    got = _names({"data": [{"type": "bidDocument", "id": "42",
                            "attributes": {"fileName": "ITB 2025-01.pdf", "fileSize": 999}}]})
    assert got == [{"name": "ITB 2025-01.pdf", "id": "42", "url": None}]


def test_document_with_download_url():
    got = _names({"data": [{"type": "bid-document", "id": 99,
                            "attributes": {"name": "Plans", "downloadUrl": "https://files-prod01.planetbids.com/x.pdf"}}]})
    assert got[0]["url"] == "https://files-prod01.planetbids.com/x.pdf"


def test_bare_name_with_extension():
    got = _names({"included": [{"documentName": "Addendum 1.pdf"}]})
    assert got and got[0]["name"] == "Addendum 1.pdf"


def test_ignores_plain_nav_entries():
    # a nav/menu item — name + url but nothing document-ish — must not match
    got = _names({"nav": [{"name": "Home", "url": "https://x.com/home"}]})
    assert got == []


def test_ignores_empty_payload():
    assert _names({"data": [], "meta": {}}) == []


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed} passed" + (f", {failed} failed" if failed else ""))
    sys.exit(1 if failed else 0)
