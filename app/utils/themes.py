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


@dataclass(frozen=True, slots=True)
class ThemeChoice:
    id: str
    swatches: tuple[str, str, str]


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
        swatches=(
            "linear-gradient(135deg, #f7fafd 0%, #d8e6f7 48%, #2f72e8 100%)",
            "#2f72e8",
            "#1a2b3d",
        ),
    ),
    "deep-ocean": ThemeChoice(
        id="deep-ocean",
        swatches=(
            "linear-gradient(135deg, #0c1726 0%, #1a3452 48%, #5aa8ff 100%)",
            "#5aa8ff",
            "#15263c",
        ),
    ),
    "sandy-dawn": ThemeChoice(
        id="sandy-dawn",
        swatches=(
            "linear-gradient(135deg, #fbf7f0 0%, #ecc694 48%, #c9923a 100%)",
            "#c9923a",
            "#352e26",
        ),
    ),
    "amber-night": ThemeChoice(
        id="amber-night",
        swatches=(
            "linear-gradient(135deg, #13100c 0%, #3a3222 48%, #dbab55 100%)",
            "#dbab55",
            "#1f1a15",
        ),
    ),
    "green-meadow": ThemeChoice(
        id="green-meadow",
        swatches=(
            "linear-gradient(135deg, #f6faf6 0%, #a8d6ba 48%, #3d9470 100%)",
            "#3d9470",
            "#1f3228",
        ),
    ),
    "northern-spruce": ThemeChoice(
        id="northern-spruce",
        swatches=(
            "linear-gradient(135deg, #0e1612 0%, #1e3830 48%, #52c295 100%)",
            "#52c295",
            "#18231e",
        ),
    ),
    "graphite-day": ThemeChoice(
        id="graphite-day",
        swatches=(
            "linear-gradient(135deg, #f7f8fa 0%, #b0c4e4 48%, #3d6fd9 100%)",
            "#3d6fd9",
            "#1e222a",
        ),
    ),
    "charcoal-dusk": ThemeChoice(
        id="charcoal-dusk",
        swatches=(
            "linear-gradient(135deg, #0e1012 0%, #1e2e36 48%, #4ec4de 100%)",
            "#4ec4de",
            "#181c20",
        ),
    ),
    "berry-dawn": ThemeChoice(
        id="berry-dawn",
        swatches=(
            "linear-gradient(135deg, #faf7fd 0%, #e0d4f0 48%, #9458c8 100%)",
            "#9458c8",
            "#2e2438",
        ),
    ),
    "midnight-berry": ThemeChoice(
        id="midnight-berry",
        swatches=(
            "linear-gradient(135deg, #120e16 0%, #322846 48%, #b07ddc 100%)",
            "#b07ddc",
            "#1e1826",
        ),
    ),
    "rose-dawn": ThemeChoice(
        id="rose-dawn",
        swatches=(
            "linear-gradient(135deg, #fdf7f9 0%, #f0c8d4 48%, #d45a82 100%)",
            "#d45a82",
            "#3a2430",
        ),
    ),
    "rose-night": ThemeChoice(
        id="rose-night",
        swatches=(
            "linear-gradient(135deg, #160e12 0%, #3a2430 48%, #e88aa8 100%)",
            "#e88aa8",
            "#1f151a",
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
