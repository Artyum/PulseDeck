#!/usr/bin/env python3
"""Check locale keys: report unused entries and keys missing from the catalog."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

SOURCE_SUFFIXES = {".py", ".html", ".jinja", ".jinja2", ".js", ".mjs", ".ts", ".tsx"}
TEMPLATE_SUFFIXES = {".html", ".jinja", ".jinja2"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "report",
    "mount",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}
LOCALES_DIR = Path("app/locales")
SOURCE_LOCALE = "pl"
KEY_LINE = re.compile(r"(?P<indent> *)(?P<key>[A-Za-z0-9_.-]+):(?P<rest>.*)$")
KEY_SHAPE = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+$")
LITERAL = r'"[^"\n]{0,200}"|\'[^\'\n]{0,200}\''
TOKEN = rf"(?:{LITERAL}|[A-Za-z_$][\w$]*(?:\.[\w$]+|\[[^\]]*\])*)"
CHAIN = re.compile(rf"{TOKEN}(?:\s*[+~]\s*{TOKEN})+")
WILDCARD = "([^.]+)"
MIN_LITERAL_CHARS = 4
PREFIX_CALLS = {"translations_prefix", "enum_labels"}
TEMPLATE_CALL = re.compile(r"\bt\s*\(")
JS_CALL = re.compile(r"\b(?:i18n|i18nFormat)\s*\(")
JS_INDEX = re.compile(r"__i18n\s*\[\s*(" + LITERAL + r")\s*\]")
CALL_LIMIT = 400


@dataclass(frozen=True)
class Scan:
    blob: str
    patterns: dict[str, list[re.Pattern[str]]]
    exported: tuple[str, ...]
    fragments: tuple[str, ...]
    requested: frozenset[str]
    relative: frozenset[str]
    request_patterns: tuple[tuple[str, str], ...]
    unresolved: int
    references: bool = True

    def used(self, key: str) -> bool:
        if not self.references:
            raise RuntimeError("scan without references cannot detect unused keys")
        exact = {key}
        candidates = [key]
        for prefix in self.exported:
            if key.startswith(prefix + "."):
                trimmed = key[len(prefix) + 1 :]
                exact.add(trimmed)
                candidates.append(trimmed)
        if any(f'"{form}"' in self.blob or f"'{form}'" in self.blob for form in exact):
            return True
        if any(
            key.startswith(fragment) or f".{fragment}" in key
            for fragment in self.fragments
        ):
            return True
        return any(self._matches(candidate) for candidate in candidates)

    def _matches(self, candidate: str) -> bool:
        for variant in variants(candidate):
            head = variant.split(".", 1)[0]
            if any(pattern.match(variant) for pattern in self.patterns.get(head, ())):
                return True
        return False


def flatten(data: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            out.update(flatten(value, path))
        elif value is not None:
            out[path] = str(value)
    return out


def load_locales(
    root: Path,
) -> tuple[dict[str, dict[str, str]], dict[str, Path], list[str]]:
    locales_dir = root / LOCALES_DIR
    if not locales_dir.is_dir():
        raise RuntimeError(f"Missing locales directory: {locales_dir}")
    catalogs: dict[str, dict[str, str]] = {}
    paths: dict[str, Path] = {}
    for path in sorted(locales_dir.glob("*.yml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as error:
            raise RuntimeError(f"Cannot read {path}: {error}") from error
        if not isinstance(raw, dict):
            raise TypeError(f"Locale file is not a mapping: {path}")
        lang = path.stem.lower()
        if lang in catalogs:
            raise RuntimeError(
                f"Duplicate locale file for {lang}: {path} and {paths[lang]}"
            )
        catalogs[lang] = flatten(
            {key: value for key, value in raw.items() if key != "meta"}
        )
        paths[lang] = path
    if SOURCE_LOCALE not in catalogs:
        raise RuntimeError(f"Missing source locale: {SOURCE_LOCALE}.yml")
    source = set(catalogs[SOURCE_LOCALE])
    errors = [
        f"{lang}: {label} {len(diff)} keys, e.g. {', '.join(sorted(diff)[:3])}"
        for lang, catalog in catalogs.items()
        for label, diff in (
            ("missing", source - set(catalog)),
            ("extra", set(catalog) - source),
        )
        if diff
    ]
    return catalogs, paths, errors


def iter_sources(root: Path) -> list[Path]:
    locales = root / LOCALES_DIR
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in SOURCE_SUFFIXES
        and locales not in path.parents
        and not any(part in SKIP_DIRS for part in path.relative_to(root).parts)
    )


def pattern(parts: list[str | None]) -> tuple[str, str] | None:
    merged: list[str | None] = []
    for part in parts:
        if part is None and merged and merged[-1] is None:
            continue
        merged.append(part)
    if merged[0] is None:
        return None
    if sum(len(part) for part in merged if part) < MIN_LITERAL_CHARS:
        return None
    if not any(part and "." in part for part in merged):
        return None
    body = "".join(re.escape(part) if part else WILDCARD for part in merged)
    return merged[0].split(".", 1)[0], body


def loose(body: str) -> str:
    return body.replace(WILDCARD, r"[^.]+(?:\.[^.]+)*")


def readable(body: str) -> str:
    return body.replace(WILDCARD, "*").replace("\\.", ".")


def variants(key: str) -> set[str]:
    segments = key.split(".")
    return {
        ".".join(segments[start:end])
        for start in range(len(segments))
        for end in range(start + 1, len(segments) + 1)
    }


def py_parts(node: ast.AST) -> list[str | None]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return [
            value.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
            else None
            for value in node.values
        ]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return py_parts(node.left) + py_parts(node.right)
    return [None]


def chain_parts(text: str) -> list[list[str | None]]:
    return [
        [
            pick(token) if token[0] in "\"'" else None
            for token in re.findall(TOKEN, match.group(0))
        ]
        for match in CHAIN.finditer(text)
    ]


def pick(value: str) -> str:
    return value[1:-1]


def py_scan(
    tree: ast.AST,
) -> tuple[set[tuple[str, str]], set[str], set[str], set[tuple[str, str]], int]:
    patterns: set[tuple[str, str]] = set()
    exported: set[str] = set()
    requested: set[str] = set()
    request_patterns: set[tuple[str, str]] = set()
    unresolved = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.JoinedStr, ast.BinOp)):
            found = pattern(py_parts(node))
            if found:
                patterns.add(found)
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id in PREFIX_CALLS:
            exported |= {
                arg.value
                for arg in node.args
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            }
        elif node.func.id == "t":
            argument = (
                node.args[1]
                if len(node.args) > 1
                else (node.args[0] if node.args else None)
            )
            if argument is None:
                unresolved += 1
            elif isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                if KEY_SHAPE.match(argument.value):
                    requested.add(argument.value)
            else:
                found = pattern(py_parts(argument))
                if found:
                    request_patterns.add(found)
                else:
                    unresolved += 1
    return patterns, exported, requested, request_patterns, unresolved


def balanced_region(text: str, open_index: int) -> str:
    depth = 0
    quote = ""
    limit = min(len(text), open_index + CALL_LIMIT)
    for index in range(open_index, limit):
        char = text[index]
        if quote:
            if char == quote and text[index - 1] != "\\":
                quote = ""
        elif char in "\"'`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : index]
    return text[open_index + 1 : limit]


def region_scan(region: str) -> tuple[set[str], set[tuple[str, str]]]:
    keys = {
        key
        for match in re.finditer(LITERAL, region)
        if KEY_SHAPE.match(key := pick(match.group(0)))
    }
    patterns = file_patterns(region)
    return keys, patterns


def text_scan(
    text: str, call: re.Pattern[str]
) -> tuple[set[str], set[tuple[str, str]], int]:
    keys: set[str] = set()
    patterns: set[tuple[str, str]] = set()
    unresolved = 0
    for match in call.finditer(text):
        region = balanced_region(text, match.end() - 1)
        found_keys, found_patterns = region_scan(region)
        keys |= found_keys
        patterns |= found_patterns
        unresolved += (
            1 if not found_keys and not found_patterns and region.strip() else 0
        )
    return keys, patterns, unresolved


def fragments_of(text: str) -> set[str]:
    return {
        value
        for match in re.finditer(LITERAL, text)
        if len(value := pick(match.group(0))) >= MIN_LITERAL_CHARS
        and value[-1] in "_-"
        and " " not in value
    }


def file_patterns(text: str) -> set[tuple[str, str]]:
    return {found for parts in chain_parts(text) if (found := pattern(parts))}


def scan(root: Path, *, references: bool = True, requests: bool = True) -> Scan:
    if not (references or requests):
        raise RuntimeError("scan() needs at least one direction")
    chunks: list[str] = []
    patterns: set[tuple[str, str]] = set()
    request_patterns: set[tuple[str, str]] = set()
    exported: set[str] = set()
    fragments: set[str] = set()
    requested: set[str] = set()
    relative: set[str] = set()
    unresolved = 0
    for path in iter_sources(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            print(f"[WARN] Cannot read {path}: {error}", file=sys.stderr)
            continue
        if references:
            chunks.append(text)
            fragments |= fragments_of(text)
        if path.suffix == ".py":
            try:
                tree = ast.parse(text, filename=str(path))
            except SyntaxError as error:
                print(f"[WARN] Cannot parse {path}: {error}", file=sys.stderr)
                continue
            py_patterns, py_exported, py_keys, py_requests, py_unresolved = py_scan(
                tree
            )
            exported |= py_exported
            if references:
                patterns |= py_patterns
            if requests:
                requested |= py_keys
                request_patterns |= py_requests
                unresolved += py_unresolved
            continue
        if references:
            patterns |= file_patterns(text)
        if not requests:
            continue
        if path.suffix in TEMPLATE_SUFFIXES:
            keys, found_patterns, count = text_scan(text, TEMPLATE_CALL)
            requested |= keys
        else:
            keys, found_patterns, count = text_scan(text, JS_CALL)
            relative |= keys | {
                pick(match.group(1)) for match in JS_INDEX.finditer(text)
            }
        request_patterns |= found_patterns
        unresolved += count
    index: dict[str, list[re.Pattern[str]]] = {}
    for head, body in sorted(patterns):
        index.setdefault(head, []).append(re.compile(f"^{loose(body)}$"))
    return Scan(
        blob="\n".join(chunks),
        patterns=index,
        exported=tuple(sorted(exported)),
        fragments=tuple(sorted(fragments)),
        requested=frozenset(requested),
        relative=frozenset(key for key in relative if KEY_SHAPE.match(key)),
        request_patterns=tuple(sorted(request_patterns)),
        unresolved=unresolved,
        references=references,
    )


def unmatched(
    catalog: set[str], patterns: tuple[tuple[str, str], ...], exported: tuple[str, ...]
) -> list[str]:
    prefixes = ("",) + tuple(f"{prefix}." for prefix in exported)
    return [
        readable(body)
        for _, body in patterns
        if not any(
            re.match(f"^{re.escape(prefix)}{loose(body)}$", key)
            for prefix in prefixes
            for key in catalog
        )
    ]


def locale_entries(lines: list[str]) -> list[tuple[int, tuple[str, ...], bool]]:
    entries: list[tuple[int, tuple[str, ...], bool]] = []
    stack: list[tuple[int, str]] = []
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = KEY_LINE.match(line.rstrip("\n"))
        if not match:
            raise RuntimeError(f"Unsupported locale line {number}: {stripped}")
        indent = len(match.group("indent"))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = tuple(key for _, key in stack) + (match.group("key"),)
        leaf = bool(match.group("rest").strip())
        entries.append((number, path, leaf))
        if not leaf:
            stack.append((indent, match.group("key")))
    return entries


def rewrite(path: Path, unused: set[str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    entries = locale_entries(lines)
    doomed = {
        number for number, key, leaf in entries if leaf and ".".join(key) in unused
    }
    survivors = [key for number, key, leaf in entries if leaf and number not in doomed]
    doomed |= {
        number
        for number, key, leaf in entries
        if not leaf and not any(item[: len(key)] == key for item in survivors)
    }
    collapsed: list[str] = []
    for number, line in enumerate(lines, start=1):
        if number in doomed:
            continue
        if not line.strip() and collapsed and not collapsed[-1].strip():
            continue
        collapsed.append(line)
    path.write_text("".join(collapsed), encoding="utf-8")


def run_unused(
    paths: dict[str, Path],
    catalogs: dict[str, dict[str, str]],
    found: Scan,
    write: bool,
    check: bool,
) -> int:
    keys = set(catalogs[SOURCE_LOCALE])
    unused = sorted(key for key in keys if not found.used(key))
    for lang, catalog in sorted(catalogs.items()):
        print(f"{lang}: {len(catalog)} keys")
    if not unused:
        print(f"No unused keys ({len(keys)} checked).")
        return 0
    print(f"Unused keys ({len(unused)}):")
    for key in unused:
        print(f"  {key}")
    if not write:
        if check:
            return 1
        print("Dry run — rerun with --write to remove them.")
        return 0
    for lang in sorted(catalogs):
        try:
            rewrite(paths[lang], set(unused))
        except (OSError, RuntimeError) as error:
            print(
                f"[ERROR] Cannot rewrite {paths[lang].name}: {error}", file=sys.stderr
            )
            return 2
    print(f"Removed {len(unused)} keys from {len(catalogs)} locale files.")
    return 0


def run_missing(catalogs: dict[str, dict[str, str]], found: Scan) -> int:
    catalog = set(catalogs[SOURCE_LOCALE])
    missing = sorted(key for key in found.requested if key not in catalog)
    missing_relative = sorted(
        key
        for key in found.relative
        if key not in catalog
        and not any(f"{prefix}.{key}" in catalog for prefix in found.exported)
    )
    broken = unmatched(catalog, found.request_patterns, found.exported)
    print(
        f"{SOURCE_LOCALE}: {len(catalog)} keys, {len(found.requested) + len(found.relative)} requested, "
        f"{len(found.request_patterns)} dynamic"
    )
    for title, items in (
        ("Missing keys", missing),
        ("Missing JS keys", missing_relative),
        ("Dynamic families matching nothing", broken),
    ):
        if items:
            print(f"{title} ({len(items)}):")
            for item in items:
                print(f"  {item}")
    if not (missing or missing_relative or broken):
        print(f"No missing keys ({found.unresolved} dynamic call sites unresolved).")
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root.",
    )
    parser.add_argument(
        "--write", action="store_true", help="Remove unused keys from locale files."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with status 1 when unused keys exist.",
    )
    parser.add_argument(
        "--missing",
        action="store_true",
        help="Report keys used in code but missing from locales.",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    try:
        catalogs, paths, errors = load_locales(root)
    except (RuntimeError, TypeError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2
    if errors:
        print("[ERROR] Locale keys are out of sync:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 2

    wants_requests = args.missing
    wants_references = not args.missing or args.write or args.check
    found = scan(root, references=wants_references, requests=wants_requests)
    status = run_missing(catalogs, found) if wants_requests else 0
    if wants_references:
        status = max(status, run_unused(paths, catalogs, found, args.write, args.check))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
