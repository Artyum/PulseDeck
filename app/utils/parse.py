from __future__ import annotations


def parse_positive_int(value: object, *, default: int = 1) -> int:
    if value is None:
        return default
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default
