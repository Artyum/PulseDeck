from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path

_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def parse_env_file(path: Path | str) -> list[tuple[str, str]]:
    """Parse an env file into a list of (key, value) pairs."""
    env_path = Path(path)
    if not env_path.is_file():
        raise FileNotFoundError(env_path)

    pairs: list[tuple[str, str]] = []
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _LINE_RE.match(line)
        if not match:
            continue
        key, value = match.group(1), _strip_quotes(match.group(2).strip())
        pairs.append((key, value))
    return pairs


def apply_env_file(path: Path | str, *, override: bool = True) -> int:
    """Set env vars from a file in the current Python process."""
    count = 0
    for key, value in parse_env_file(path):
        if override or key not in os.environ:
            os.environ[key] = value
            count += 1
    return count


def _escape_cmd_value(value: str) -> str:
    return value.replace("%", "%%")


def write_cmd_batch(path: Path | str) -> Path:
    """Generate a temporary .bat with set commands (override in cmd session)."""
    pairs = parse_env_file(path)
    bat_path = Path(tempfile.gettempdir()) / f"pulsedeck_env_{uuid.uuid4().hex}.bat"
    lines = ["@echo off"]
    for key, value in pairs:
        lines.append(f'set "{key}={_escape_cmd_value(value)}"')
    bat_path.write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")
    return bat_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load deploy env file into environment"
    )
    parser.add_argument("env_file", help="Path to .env file")
    parser.add_argument(
        "--emit-cmd-batch",
        action="store_true",
        help="Print path to temporary .bat with set commands (for Windows cmd)",
    )
    args = parser.parse_args()

    try:
        if args.emit_cmd_batch:
            bat_path = write_cmd_batch(args.env_file)
            print(bat_path)
            return 0
        n = apply_env_file(args.env_file)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"Loaded {n} variables from {args.env_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
