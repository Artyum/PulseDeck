import bcrypt

from app.config import get_settings
from app.utils.i18n import DEFAULT_LANG, t

BCRYPT_ROUNDS = 12


def validate_password_strength(password: str, *, lang: str | None = None) -> str:
    from app.validation import clean

    return clean("user.password", password, lang=lang or DEFAULT_LANG)


def _password_bytes(password: str, *, lang: str | None = None) -> bytes:
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > get_settings().password_max_len:
        raise ValueError(t(lang or DEFAULT_LANG, "messages.password.too_long"))
    return pwd_bytes


def hash_password(password: str, *, lang: str | None = None) -> str:
    return bcrypt.hashpw(
        _password_bytes(password, lang=lang), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if len(plain_password.encode("utf-8")) > get_settings().password_max_len:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("ascii"),
        )
    except (ValueError, TypeError):
        return False
