from __future__ import annotations

from dataclasses import dataclass

THEME_STORAGE_KEY = "pulsedeck_theme"
DEFAULT_THEME = "morning-mist"

THEME_GRADIENT_STORAGE_KEY = "pulsedeck_theme_gradients"
DEFAULT_THEME_GRADIENT = "on"

DENSITY_STORAGE_KEY = "pulsedeck_density"
DEFAULT_DENSITY = "balanced"

FONT_SIZE_STORAGE_KEY = "pulsedeck_font_size"
DEFAULT_FONT_SIZE = "natural"

THREAD_ORDER_STORAGE_KEY = "pulsedeck_thread_order"
DEFAULT_THREAD_ORDER = "oldest"
THREAD_ORDER_IDS = ("oldest", "newest")


@dataclass(frozen=True, slots=True)
class ThemePreview:
    page: str
    aside: str
    surface: str
    soft: str
    pulse: str
    ink: str


@dataclass(frozen=True, slots=True)
class ThemeChoice:
    id: str
    preview: ThemePreview


@dataclass(frozen=True, slots=True)
class AppearanceChoice:
    id: str


THEME_PAIRS: tuple[tuple[str, str], ...] = (
    ("morning-mist", "deep-ocean"),
    ("sandy-dawn", "amber-night"),
    ("green-meadow", "northern-spruce"),
    ("graphite-day", "charcoal-dusk"),
    ("berry-dawn", "midnight-berry"),
    ("rose-dawn", "rose-night"),
)

_THEMES: dict[str, ThemeChoice] = {
    "morning-mist": ThemeChoice(
        id="morning-mist",
        preview=ThemePreview(
            page="#f5f8fc",
            aside="#eef3fa",
            surface="#ffffff",
            soft="#d8e6f7",
            pulse="#2f72e8",
            ink="#1a2b3d",
        ),
    ),
    "deep-ocean": ThemeChoice(
        id="deep-ocean",
        preview=ThemePreview(
            page="#0c1726",
            aside="#101c2e",
            surface="#15263c",
            soft="#1a3452",
            pulse="#5aa8ff",
            ink="#d8e4f2",
        ),
    ),
    "sandy-dawn": ThemeChoice(
        id="sandy-dawn",
        preview=ThemePreview(
            page="#faf5ee",
            aside="#f3ebe0",
            surface="#fffdfb",
            soft="#ebe5dc",
            pulse="#c9923a",
            ink="#352e26",
        ),
    ),
    "amber-night": ThemeChoice(
        id="amber-night",
        preview=ThemePreview(
            page="#13100c",
            aside="#181410",
            surface="#1f1a15",
            soft="#2a2622",
            pulse="#dbab55",
            ink="#ebe2d6",
        ),
    ),
    "green-meadow": ThemeChoice(
        id="green-meadow",
        preview=ThemePreview(
            page="#f4f8f4",
            aside="#e8f0ea",
            surface="#ffffff",
            soft="#dae7e3",
            pulse="#3d9470",
            ink="#1f3228",
        ),
    ),
    "northern-spruce": ThemeChoice(
        id="northern-spruce",
        preview=ThemePreview(
            page="#0e1612",
            aside="#121b16",
            surface="#18231e",
            soft="#1e322c",
            pulse="#52c295",
            ink="#d8e8de",
        ),
    ),
    "graphite-day": ThemeChoice(
        id="graphite-day",
        preview=ThemePreview(
            page="#f5f6f8",
            aside="#eceef3",
            surface="#ffffff",
            soft="#dde1e8",
            pulse="#5a6678",
            ink="#1e222a",
        ),
    ),
    "charcoal-dusk": ThemeChoice(
        id="charcoal-dusk",
        preview=ThemePreview(
            page="#0e1012",
            aside="#13161a",
            surface="#181c20",
            soft="#242a32",
            pulse="#9aa8b8",
            ink="#dce1e8",
        ),
    ),
    "berry-dawn": ThemeChoice(
        id="berry-dawn",
        preview=ThemePreview(
            page="#f8f5fb",
            aside="#f1ecf6",
            surface="#ffffff",
            soft="#e4e0ec",
            pulse="#9458c8",
            ink="#2e2438",
        ),
    ),
    "midnight-berry": ThemeChoice(
        id="midnight-berry",
        preview=ThemePreview(
            page="#120e16",
            aside="#17131c",
            surface="#1e1826",
            soft="#282238",
            pulse="#b07ddc",
            ink="#ebe3f2",
        ),
    ),
    "rose-dawn": ThemeChoice(
        id="rose-dawn",
        preview=ThemePreview(
            page="#fbf5f7",
            aside="#f6eef1",
            surface="#ffffff",
            soft="#eee4ea",
            pulse="#d45a82",
            ink="#3a2430",
        ),
    ),
    "rose-night": ThemeChoice(
        id="rose-night",
        preview=ThemePreview(
            page="#160e12",
            aside="#1c1218",
            surface="#1f151a",
            soft="#32242c",
            pulse="#e88aa8",
            ink="#f0e4ea",
        ),
    ),
}

DARK_THEME_IDS: frozenset[str] = frozenset(dark for _, dark in THEME_PAIRS)

THEME_CHOICES: tuple[ThemeChoice, ...] = tuple(
    _THEMES[light] for light, _ in THEME_PAIRS
) + tuple(_THEMES[dark] for _, dark in THEME_PAIRS)

DENSITY_CHOICES: tuple[AppearanceChoice, ...] = (
    AppearanceChoice(id="tight"),
    AppearanceChoice(id="balanced"),
    AppearanceChoice(id="airy"),
)

FONT_SIZE_CHOICES: tuple[AppearanceChoice, ...] = (
    AppearanceChoice(id="compact"),
    AppearanceChoice(id="natural"),
    AppearanceChoice(id="large"),
)

THEME_IDS: frozenset[str] = frozenset(t.id for t in THEME_CHOICES)
DENSITY_IDS: frozenset[str] = frozenset(c.id for c in DENSITY_CHOICES)
FONT_SIZE_IDS: frozenset[str] = frozenset(c.id for c in FONT_SIZE_CHOICES)


def theme_scheme(theme_id: str) -> str:
    return "dark" if theme_id in DARK_THEME_IDS else "light"
