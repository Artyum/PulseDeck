PROTECTED_ENVIRONMENTS = frozenset({"production", "staging", "prod", "preprod"})


def parse_mfa_ttl_days(raw: str) -> int:
    text = (raw or "").strip().lower()
    if text.endswith("d"):
        text = text[:-1].strip()
    days = int(text)
    if days < 1 or days > 365:
        raise ValueError("MFA_TTL must be between 1 and 365 days")
    return days


def is_protected_environment(environment: str) -> bool:
    return (environment or "").strip().lower() in PROTECTED_ENVIRONMENTS


def cookie_secure(environment: str, public_https: bool = False) -> bool:
    return is_protected_environment(environment) or public_https
