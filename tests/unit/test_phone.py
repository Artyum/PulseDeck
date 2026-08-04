from app.utils.phone import format_phone, normalize_phone


def test_normalize_phone_none():
    assert normalize_phone(None) is None


def test_normalize_phone_empty():
    assert normalize_phone("") is None
    assert normalize_phone("  ") is None


def test_normalize_phone_valid_e164():
    assert normalize_phone("+48123456789") == "+48123456789"


def test_normalize_phone_strips_whitespace():
    assert normalize_phone("  +48 123 456 789  ") == "+48123456789"


def test_normalize_phone_strips_dashes():
    assert normalize_phone("+48-123-456-789") == "+48123456789"


def test_normalize_phone_strips_parentheses():
    assert normalize_phone("+48(12)3456789") == "+48123456789"


def test_normalize_phone_invalid_raises():
    import pytest

    with pytest.raises(ValueError):
        normalize_phone("abc")
    with pytest.raises(ValueError):
        normalize_phone("123")
    with pytest.raises(ValueError):
        normalize_phone("+48abc")
    with pytest.raises(ValueError):
        normalize_phone("+")  # too short


def test_format_phone_empty():
    assert format_phone(None) == ""
    assert format_phone("") == ""
    assert format_phone("  ") == ""


def test_format_phone_pl():
    assert format_phone("+48123456789") == "+48 123 456 789"
    assert format_phone("+48 123 456 789") == "+48 123 456 789"


def test_format_phone_us():
    assert format_phone("+12025551234") == "+1 202 555 1234"


def test_format_phone_invalid_passthrough():
    assert format_phone("not-a-phone") == "not-a-phone"
