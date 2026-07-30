from __future__ import annotations

from dataclasses import dataclass

THEME_STORAGE_KEY = "pulsedeck_theme"
DEFAULT_THEME = "morning-mist"

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
    ThemeChoice(id="morning-mist", swatches=("#f7f9fc", "#2f72e8", "#1a2b3d")),
    ThemeChoice(id="sandy-dawn", swatches=("#faf6f0", "#c9923a", "#352e26")),
    ThemeChoice(id="green-meadow", swatches=("#f5f8f5", "#3d9470", "#1f3228")),
    ThemeChoice(id="graphite-day", swatches=("#f6f7f9", "#3d6fd9", "#1e222a")),
    ThemeChoice(id="deep-ocean", swatches=("#0e1a2b", "#5aa8ff", "#172840")),
    ThemeChoice(id="midnight-berry", swatches=("#141018", "#b07ddc", "#201a29")),
    ThemeChoice(id="northern-spruce", swatches=("#101814", "#52c295", "#1a2520")),
    ThemeChoice(id="charcoal-dusk", swatches=("#101214", "#4ec4de", "#1a1e23")),
    ThemeChoice(id="amber-night", swatches=("#15120e", "#dbab55", "#211c17")),
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
