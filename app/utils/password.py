import re
import string

import bcrypt

PASSWORD_MIN_LEN = 8
PASSWORD_MAX_BYTES = 72
BCRYPT_ROUNDS = 12

_SPECIAL_RE = re.compile(rf"[{re.escape(string.punctuation)}]")


def validate_password_strength(password: str) -> str:
    if len(password) < PASSWORD_MIN_LEN:
        raise ValueError(f"Hasło musi mieć co najmniej {PASSWORD_MIN_LEN} znaków.")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError("Hasło jest zbyt długie.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Hasło musi zawierać małą literę.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Hasło musi zawierać wielką literę.")
    if not re.search(r"\d", password):
        raise ValueError("Hasło musi zawierać cyfrę.")
    if not _SPECIAL_RE.search(password):
        raise ValueError("Hasło musi zawierać znak specjalny.")
    return password


def _password_bytes(password: str) -> bytes:
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > PASSWORD_MAX_BYTES:
        raise ValueError("Hasło jest zbyt długie.")
    return pwd_bytes


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        _password_bytes(password), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
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
