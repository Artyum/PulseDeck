from app.utils.mfa_ttl import cookie_secure, parse_mfa_ttl_days


def test_parse_mfa_ttl_days() -> None:
    assert parse_mfa_ttl_days("30") == 30
    assert parse_mfa_ttl_days("30d") == 30


def test_cookie_secure() -> None:
    assert cookie_secure("prod") is True
    assert cookie_secure("preprod") is True
    assert cookie_secure("dev") is False
    assert cookie_secure("dev", public_https=True) is True
