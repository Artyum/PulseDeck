#!/usr/bin/env python3
"""Tłumaczy app/locales/en.yml na pliki app/locales/<kod>.yml.

Uruchamiaj z katalogu projektu. Można przerwać i puścić ponownie: postęp jest
w mount/locale_gen_cache.json, a app/locales/<kod>.yml zapisuje się po każdej
paczce. Brakujące stringi zostają po angielsku do końca tłumaczenia.

  .venv/bin/python scripts/generate_locales_from_en.py --list
  .venv/bin/python scripts/generate_locales_from_en.py --status
  .venv/bin/python scripts/generate_locales_from_en.py --only it
  .venv/bin/python scripts/generate_locales_from_en.py --only sk cs hu
  .venv/bin/python scripts/generate_locales_from_en.py

Kody: it pt ru zh ja ko nl tr uk ar sk cs hu.
--delay SEC zmienia pauzę między paczkami (domyślnie 0.4).
Potem: .venv/bin/python scripts/check_locale_keys.py --write
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOCALES_DIR = ROOT / "app" / "locales"
SOURCE = LOCALES_DIR / "en.yml"
DEFAULT_CACHE = ROOT / "mount" / "locale_gen_cache.json"

LOCALES: dict[str, tuple[str, str]] = {
    "it": ("Italiano", "it"),
    "pt": ("Português", "pt"),
    "ru": ("Русский", "ru"),
    "zh": ("简体中文", "zh-CN"),
    "ja": ("日本語", "ja"),
    "ko": ("한국어", "ko"),
    "nl": ("Nederlands", "nl"),
    "tr": ("Türkçe", "tr"),
    "uk": ("Українська", "uk"),
    "ar": ("العربية", "ar"),
    "sk": ("Slovenčina", "sk"),
    "cs": ("Čeština", "cs"),
    "hu": ("Magyar", "hu"),
}

PH = re.compile(r"\{[^{}]+\}")
TOK = "__PH{}__"
TOK_LOOSE = re.compile(r"__\s*PH(\d+)\s*__")
SEP = "\n§§§\n"
SEP_SPLIT = re.compile(r"\n\s*§§§\s*\n")
GTX = "https://translate.googleapis.com/translate_a/single"
BATCH_CHARS = 3500

logger = logging.getLogger("generate_locales")


def protect(text: str) -> tuple[str, list[str]]:
    found: list[str] = []

    def repl(m: re.Match[str]) -> str:
        found.append(m.group(0))
        return TOK.format(len(found) - 1)

    return PH.sub(repl, text), found


def restore(text: str, found: list[str]) -> str:
    def repl(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if 0 <= index < len(found):
            return found[index]
        return match.group(0)

    return TOK_LOOSE.sub(repl, text or "")


def collect_strings(node: Any, out: list[str]) -> None:
    if isinstance(node, dict):
        for v in node.values():
            collect_strings(v, out)
    elif isinstance(node, str):
        out.append(node)


def load_source() -> dict[str, Any]:
    raw = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"{SOURCE} must be a YAML mapping")
    return raw


def source_unique_strings() -> list[str]:
    data = load_source()
    body = {k: v for k, v in data.items() if k != "meta"}
    strings: list[str] = []
    collect_strings(body, strings)
    return list(dict.fromkeys(strings))


def load_cache(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Uszkodzony cache — start od pustego: %s", path)
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for lang, table in raw.items():
        if isinstance(lang, str) and isinstance(table, dict):
            out[lang] = {str(k): str(v) for k, v in table.items()}
    return out


def save_cache(path: Path, cache: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def progress(
    cache: dict[str, dict[str, str]], unique: list[str]
) -> dict[str, tuple[int, int]]:
    total = len(unique)
    out: dict[str, tuple[int, int]] = {}
    for code in LOCALES:
        done = sum(1 for s in unique if cache.get(code, {}).get(s))
        out[code] = (done, total)
    return out


def gtx_translate(text: str, target: str) -> str:
    query = urllib.parse.urlencode(
        {"client": "gtx", "sl": "en", "tl": target, "dt": "t", "q": text}
    )
    request = urllib.request.Request(
        f"{GTX}?{query}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode())
            parts = payload[0] if isinstance(payload, list) else None
            if not parts:
                raise RuntimeError("pusta odpowiedź Google")
            return "".join(seg[0] for seg in parts if seg and seg[0])
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code != 429:
                raise
            wait = min(90.0, (2**attempt) + random.uniform(0, 0.4))
            logger.warning("HTTP 429 — czekam %.1f s (próba %d)", wait, attempt + 1)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            wait = min(30.0, (attempt + 1) * 2)
            logger.warning("Błąd sieci: %s — retry za %.1f s", error, wait)
            time.sleep(wait)
    raise RuntimeError(f"Nie udało się przetłumaczyć: {last_error}") from last_error


def pack_batches(texts: list[str]) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for text in texts:
        extra = len(text) + (len(SEP) if current else 0)
        if current and size + extra > BATCH_CHARS:
            batches.append(current)
            current = [text]
            size = len(text)
        else:
            current.append(text)
            size += extra
    if current:
        batches.append(current)
    return batches


def translate_batch(texts: list[str], target: str) -> list[str]:
    protected: list[tuple[str, list[str]]] = [protect(text) for text in texts]
    joined = SEP.join(item[0] for item in protected)
    raw = gtx_translate(joined, target)
    parts = SEP_SPLIT.split(raw)
    if len(parts) != len(texts):
        logger.warning(
            "Paczka rozjechała się (%d ≠ %d) — tłumaczę pojedynczo",
            len(parts),
            len(texts),
        )
        return [restore(gtx_translate(item[0], target), item[1]) for item in protected]
    return [restore(part, item[1]) for part, item in zip(parts, protected, strict=True)]


def translate_tree(node: Any, table: dict[str, str]) -> Any:
    if isinstance(node, dict):
        return {key: translate_tree(value, table) for key, value in node.items()}
    if isinstance(node, str):
        return table.get(node, node)
    return node


def write_yaml(
    code: str, cache: dict[str, dict[str, str]], unique: list[str]
) -> Path | None:
    display, _ = LOCALES[code]
    table = cache.get(code, {})
    if not table:
        return None
    data = load_source()
    meta = data.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    meta["name"] = display
    data["meta"] = meta
    body = {
        key: value if key == "meta" else translate_tree(value, table)
        for key, value in data.items()
    }
    path = LOCALES_DIR / f"{code}.yml"
    path.write_text(
        yaml.dump(body, allow_unicode=True, sort_keys=False, width=10_000),
        encoding="utf-8",
    )
    missing = sum(1 for item in unique if item not in table)
    if missing:
        logger.info(
            "Zapisano %s (%d/%d, %d jeszcze po angielsku)",
            path.name,
            len(table),
            len(unique),
            missing,
        )
    else:
        logger.info("Zapisano %s (%d/%d)", path.name, len(table), len(unique))
    return path


def run_translate(
    codes: list[str],
    cache: dict[str, dict[str, str]],
    cache_path: Path,
    unique: list[str],
    delay: float,
) -> None:
    for code in codes:
        display, target = LOCALES[code]
        table = cache.setdefault(code, {})
        pending = [s for s in unique if s not in table]
        if not pending:
            logger.info("%s (%s): cache kompletny (%d)", code, display, len(unique))
            write_yaml(code, cache, unique)
            continue
        logger.info(
            "%s (%s): tłumaczę %d / %d brakujących",
            code,
            display,
            len(pending),
            len(unique),
        )
        batches = pack_batches(pending)
        logger.info("%s: %d paczek", code, len(batches))
        for index, batch in enumerate(batches, start=1):
            try:
                translated = translate_batch(batch, target)
            except RuntimeError:
                logger.error(
                    "%s: przerwano na paczce %d/%d — cache i YAML zapisane",
                    code,
                    index,
                    len(batches),
                )
                save_cache(cache_path, cache)
                write_yaml(code, cache, unique)
                raise
            for source, value in zip(batch, translated, strict=True):
                table[source] = value
            save_cache(cache_path, cache)
            write_yaml(code, cache, unique)
            logger.info(
                "%s: paczka %d/%d — %d/%d",
                code,
                index,
                len(batches),
                len(table),
                len(unique),
            )
            time.sleep(delay)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache",
        type=Path,
        default=DEFAULT_CACHE,
        help=f"Plik cache (domyślnie {DEFAULT_CACHE.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        metavar="CODE",
        help=f"Kody języków: {', '.join(LOCALES)}",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Wypisz obsługiwane locale i wyjdź",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Postęp tłumaczeń w cache (bez wywołań API)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.4,
        metavar="SEC",
        help="Pauza między paczkami (domyślnie 0.4)",
    )
    args = parser.parse_args(argv)

    if args.list:
        for code, (name, target) in LOCALES.items():
            print(f"{code}\t{name}\t(en → {target})")
        return 0

    if not SOURCE.is_file():
        logger.error("Brak źródła: %s", SOURCE)
        return 2

    codes = list(LOCALES) if not args.only else [c for c in args.only if c in LOCALES]
    unknown = [c for c in (args.only or []) if c not in LOCALES]
    if unknown:
        logger.error("Nieznane kody: %s", ", ".join(unknown))
        return 2
    if not codes:
        parser.error("Podaj --only CODE … lub uruchom bez --only dla wszystkich")

    unique = source_unique_strings()
    cache = load_cache(args.cache)

    if args.status:
        for code, (done, total) in progress(cache, unique).items():
            mark = " " if code in codes or not args.only else "·"
            pct = (100.0 * done / total) if total else 0
            print(f"{mark} {code}: {done}/{total} ({pct:.0f}%)")
        return 0

    try:
        run_translate(codes, cache, args.cache, unique, args.delay)
    except RuntimeError:
        return 1
    save_cache(args.cache, cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
