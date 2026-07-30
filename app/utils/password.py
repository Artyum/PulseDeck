import re
import string

import bcrypt

from app.utils.i18n import DEFAULT_LANG, t

PASSWORD_MIN_LEN = 8
PASSWORD_MAX_BYTES = 72
BCRYPT_ROUNDS = 12

_SPECIAL_RE = re.compile(rf"[{re.escape(string.punctuation)}]")


def validate_password_strength(password: str, *, lang: str | None = None) -> str:
    lang = lang or DEFAULT_LANG
    if len(password) < PASSWORD_MIN_LEN:
        raise ValueError(t(lang, "messages.password.min_length", min=PASSWORD_MIN_LEN))
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError(t(lang, "messages.password.too_long"))
    if not re.search(r"[a-z]", password):
        raise ValueError(t(lang, "messages.password.need_lower"))
    if not re.search(r"[A-Z]", password):
        raise ValueError(t(lang, "messages.password.need_upper"))
    if not re.search(r"\d", password):
        raise ValueError(t(lang, "messages.password.need_digit"))
    if not _SPECIAL_RE.search(password):
        raise ValueError(t(lang, "messages.password.need_special"))
    return password


def _password_bytes(password: str, *, lang: str | None = None) -> bytes:
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > PASSWORD_MAX_BYTES:
        raise ValueError(t(lang or DEFAULT_LANG, "messages.password.too_long"))
    return pwd_bytes


def hash_password(password: str, *, lang: str | None = None) -> str:
    return bcrypt.hashpw(
        _password_bytes(password, lang=lang), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if len(plain_password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("ascii"),
        )
    except (ValueError, TypeError):
        return False
