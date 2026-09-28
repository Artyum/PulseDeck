from app.utils.mfa_ttl import cookie_secure, normalize_environment, parse_mfa_ttl_days


def test_parse_mfa_ttl_days() -> None:
    assert parse_mfa_ttl_days("30") == 30
    assert parse_mfa_ttl_days("30d") == 30


def test_cookie_secure() -> None:
    assert cookie_secure("prod") is True
    assert cookie_secure("preprod") is True
    assert cookie_secure("development") is False
    assert cookie_secure("development", public_https=True) is True


def test_normalize_environment_rejects_legacy_names() -> None:
    assert normalize_environment("development") == "development"
    assert normalize_environment("preprod") == "preprod"
    assert normalize_environment("prod") == "prod"
    for name in ("dev", "staging", "production"):
        try:
            normalize_environment(name)
        except ValueError as exc:
            assert "ENVIRONMENT must be" in str(exc)
        else:
            raise AssertionError(name)
