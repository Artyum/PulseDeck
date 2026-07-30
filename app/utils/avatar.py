from __future__ import annotations


def user_initials(name: str | None) -> str:
    if not name or not name.strip():
        return "?"
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][0].upper()
    if len(parts) == 2:
        return (parts[0][0] + parts[1][0]).upper()
    return (parts[0][0] + parts[-1][0]).upper()


def avatar_tone(user_id: int) -> int:
    return int(user_id) % 32
