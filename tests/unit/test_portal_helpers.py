"""Tests for portal helper functions that need DB (like _parse_ticket_ref)."""

import pytest
from fastapi import HTTPException


def test_parse_ticket_ref_valid():
    from app.routes.portal import _parse_ticket_ref

    key, tid = _parse_ticket_ref("DEMO-42", lang="en")
    assert key == "DEMO"
    assert tid == 42


def test_parse_ticket_ref_lowercase():
    from app.routes.portal import _parse_ticket_ref

    key, tid = _parse_ticket_ref("demo-42", lang="en")
    assert key == "DEMO"
    assert tid == 42


def test_parse_ticket_ref_whitespace():
    from app.routes.portal import _parse_ticket_ref

    key, tid = _parse_ticket_ref("  DEMO-42  ", lang="en")
    assert key == "DEMO"
    assert tid == 42


def test_parse_ticket_ref_invalid():
    from app.routes.portal import _parse_ticket_ref

    with pytest.raises(HTTPException) as exc:
        _parse_ticket_ref("invalid", lang="en")
    assert exc.value.status_code == 404


def test_parse_ticket_ref_bad_format():
    from app.routes.portal import _parse_ticket_ref

    with pytest.raises(HTTPException) as exc:
        _parse_ticket_ref("DEMO-", lang="en")
    assert exc.value.status_code == 404


def test_parse_ticket_ref_empty():
    from app.routes.portal import _parse_ticket_ref

    with pytest.raises(HTTPException) as exc:
        _parse_ticket_ref("", lang="en")
    assert exc.value.status_code == 404
