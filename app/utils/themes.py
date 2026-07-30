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


THEME_CHOICES: tuple[ThemeChoice, ...] = (
    ThemeChoice(
        id="morning-mist",
        swatches=(
            "linear-gradient(135deg, #f7fafd 0%, #d8e6f7 48%, #2f72e8 100%)",
            "#2f72e8",
            "#1a2b3d",
        ),
    ),
    ThemeChoice(
        id="sandy-dawn",
        swatches=(
            "linear-gradient(135deg, #fbf7f0 0%, #ecc694 48%, #c9923a 100%)",
            "#c9923a",
            "#352e26",
        ),
    ),
    ThemeChoice(
        id="green-meadow",
        swatches=(
            "linear-gradient(135deg, #f6faf6 0%, #a8d6ba 48%, #3d9470 100%)",
            "#3d9470",
            "#1f3228",
        ),
    ),
    ThemeChoice(
        id="graphite-day",
        swatches=(
            "linear-gradient(135deg, #f7f8fa 0%, #b0c4e4 48%, #3d6fd9 100%)",
            "#3d6fd9",
            "#1e222a",
        ),
    ),
    ThemeChoice(
        id="deep-ocean",
        swatches=(
            "linear-gradient(135deg, #0c1726 0%, #1a3452 48%, #5aa8ff 100%)",
            "#5aa8ff",
            "#15263c",
        ),
    ),
    ThemeChoice(
        id="midnight-berry",
        swatches=(
            "linear-gradient(135deg, #120e16 0%, #322846 48%, #b07ddc 100%)",
            "#b07ddc",
            "#1e1826",
        ),
    ),
    ThemeChoice(
        id="northern-spruce",
        swatches=(
            "linear-gradient(135deg, #0e1612 0%, #1e3830 48%, #52c295 100%)",
            "#52c295",
            "#18231e",
        ),
    ),
    ThemeChoice(
        id="charcoal-dusk",
        swatches=(
            "linear-gradient(135deg, #0e1012 0%, #1e2e36 48%, #4ec4de 100%)",
            "#4ec4de",
            "#181c20",
        ),
    ),
    ThemeChoice(
        id="amber-night",
        swatches=(
            "linear-gradient(135deg, #13100c 0%, #3a3222 48%, #dbab55 100%)",
            "#dbab55",
            "#1f1a15",
        ),
    ),
)

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
