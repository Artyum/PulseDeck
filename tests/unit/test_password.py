from app.utils.password import (
    hash_password,
    validate_password_strength,
    verify_password,
)


def test_password_roundtrip():
    h = hash_password("Admin123!")
    assert verify_password("Admin123!", h)
    assert not verify_password("wrong", h)


def test_password_strength():
    try:
        validate_password_strength("short")
        assert False
    except ValueError:
        pass
    assert validate_password_strength("Admin123!") == "Admin123!"
