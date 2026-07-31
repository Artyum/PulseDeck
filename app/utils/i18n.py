from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import Request

from app.config import project_root

logger = logging.getLogger("pulsedeck.app.i18n")

LANG_STORAGE_KEY = "pulsedeck_lang"
DEFAULT_LANG = "en"
LOCALES_DIR = project_root() / "app" / "locales"


@dataclass(frozen=True, slots=True)
class LangChoice:
    id: str
    name: str


_cache: tuple[float, dict[str, dict[str, str]], tuple[LangChoice, ...]] | None = None
_missing_keys: set[str] = set()
_format_failed: set[str] = set()


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            out.update(_flatten(value, path))
        elif value is None:
            continue
        else:
            out[path] = str(value)
    return out


def _load_locale_file(path: Path) -> tuple[str, str, dict[str, str]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise TypeError(f"Locale file must be a mapping: {path}")
    meta = raw.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}
    code = path.stem.lower()
    name = str(meta.get("name") or code).strip() or code
    flat = _flatten({k: v for k, v in raw.items() if k != "meta"})
    return code, name, flat


def _catalog() -> tuple[dict[str, dict[str, str]], tuple[LangChoice, ...]]:
    global _cache
    paths = sorted(LOCALES_DIR.glob("*.yml")) if LOCALES_DIR.is_dir() else []
    stamp = max((p.stat().st_mtime for p in paths), default=0.0)
    if _cache is not None and _cache[0] == stamp:
        return _cache[1], _cache[2]
    if not paths:
        logger.error("Locales directory missing: %s", LOCALES_DIR)
        _cache = (stamp, {}, ())
        return _cache[1], _cache[2]
    by_lang: dict[str, dict[str, str]] = {}
    choices: list[LangChoice] = []
    for path in paths:
        try:
            code, name, flat = _load_locale_file(path)
        except Exception:
            logger.exception("Failed to load locale %s", path)
            continue
        by_lang[code] = flat
        choices.append(LangChoice(id=code, name=name))
    if DEFAULT_LANG not in by_lang and by_lang:
        logger.warning(
            "Default locale %s missing; available: %s", DEFAULT_LANG, list(by_lang)
        )
    _cache = (stamp, by_lang, tuple(choices))
    return _cache[1], _cache[2]


def list_languages() -> tuple[LangChoice, ...]:
    return _catalog()[1]


def available_lang_ids() -> frozenset[str]:
    return frozenset(_catalog()[0])


def normalize_lang(code: str | None) -> str:
    langs = available_lang_ids()
    cleaned = (code or "").strip().lower()
    if cleaned in langs:
        return cleaned
    if DEFAULT_LANG in langs:
        return DEFAULT_LANG
    return next(iter(langs), DEFAULT_LANG)


def resolve_lang(request: Request | None = None, explicit: str | None = None) -> str:
    langs = available_lang_ids()
    if explicit and explicit in langs:
        return explicit
    if request is not None:
        cookie = (request.cookies.get(LANG_STORAGE_KEY) or "").strip().lower()
        if cookie in langs:
            return cookie
    return normalize_lang(None)


def t(lang: str, message_key: str, **kwargs: Any) -> str:
    by_lang, _ = _catalog()
    text = by_lang.get(lang, {}).get(message_key)
    if text is None and lang != DEFAULT_LANG:
        text = by_lang.get(DEFAULT_LANG, {}).get(message_key)
    if text is None:
        miss = f"{lang}:{message_key}"
        if miss not in _missing_keys:
            _missing_keys.add(miss)
            logger.warning("Missing i18n key %s (lang=%s)", message_key, lang)
        text = message_key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            if message_key not in _format_failed:
                _format_failed.add(message_key)
                logger.warning(
                    "i18n format failed for %s kwargs=%s", message_key, kwargs
                )
            return text
    return text


def translations_prefix(lang: str, prefix: str) -> dict[str, str]:
    by_lang, _ = _catalog()
    flat = by_lang.get(lang) or by_lang.get(DEFAULT_LANG) or {}
    start = f"{prefix}."
    out: dict[str, str] = {}
    for key, value in flat.items():
        if key.startswith(start):
            out[key[len(start) :]] = value
    return out


def enum_labels(lang: str, group: str) -> dict[str, str]:
    return translations_prefix(lang, f"enums.{group}")
