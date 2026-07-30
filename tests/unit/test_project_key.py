import pytest

from app.utils.project_key import normalize_project_key, validate_project_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("demo", "DEMO"),
        (" DEMO ", "DEMO"),
        ("abc12", "ABC12"),
        ("", ""),
        ("  ", ""),
        (None, ""),
    ],
)
def test_normalize_project_key(raw, expected):
    assert normalize_project_key(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "A",
        "AB",
        "ABC",
        "ABCD",
        "ABCDE",
        "A1B2C",
        "12345",
    ],
)
def test_validate_project_key_valid(raw):
    assert validate_project_key(raw) == raw.upper().strip()


@pytest.mark.parametrize(
    "raw",
    [
        "ABCDEF",  # too long
        "abcdef",  # too long after upper (6 chars)
        "",
        "  ",
        "a b",
        "a-b",
        "a_b",
    ],
)
def test_validate_project_key_invalid(raw):
    with pytest.raises(ValueError):
        validate_project_key(raw)
