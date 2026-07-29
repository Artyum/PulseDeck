from __future__ import annotations

from dataclasses import dataclass

THEME_STORAGE_KEY = "pulsedeck_theme"
DEFAULT_THEME = "morning-mist"


@dataclass(frozen=True, slots=True)
class ThemeChoice:
    id: str
    label: str
    description: str
    swatches: tuple[str, str, str]


THEME_CHOICES: tuple[ThemeChoice, ...] = (
    ThemeChoice(
        id="morning-mist",
        label="Poranna mgła",
        description="Krystaliczny błękit — domyślny wygląd PulseDeck.",
        swatches=("#f7f9fc", "#2f72e8", "#1a2b3d"),
    ),
    ThemeChoice(
        id="sandy-dawn",
        label="Piaskowy brzask",
        description="Ciepły piasek z miodowym bursztynem.",
        swatches=("#faf6f0", "#c9923a", "#352e26"),
    ),
    ThemeChoice(
        id="green-meadow",
        label="Zielona polana",
        description="Czysta zieleń szałwii, spokojny rytm pracy.",
        swatches=("#f5f8f5", "#3d9470", "#1f3228"),
    ),
    ThemeChoice(
        id="graphite-day",
        label="Grafitowy dzień",
        description="Neutralny grafit z kobaltowym akcentem.",
        swatches=("#f6f7f9", "#3d6fd9", "#1e222a"),
    ),
    ThemeChoice(
        id="deep-ocean",
        label="Głęboki ocean",
        description="Głębia szafiru z jasnym błękitem akcentu.",
        swatches=("#0e1a2b", "#5aa8ff", "#172840"),
    ),
    ThemeChoice(
        id="midnight-berry",
        label="Nocna borówka",
        description="Dojrzała jagoda z miękkim fioletem.",
        swatches=("#141018", "#b07ddc", "#201a29"),
    ),
    ThemeChoice(
        id="northern-spruce",
        label="Północny świerk",
        description="Ciemny mech z krystaliczną miętą.",
        swatches=("#101814", "#52c295", "#1a2520"),
    ),
    ThemeChoice(
        id="charcoal-dusk",
        label="Węglowy zmierzch",
        description="Czysty charcoal z lodowym cyanem.",
        swatches=("#101214", "#4ec4de", "#1a1e23"),
    ),
    ThemeChoice(
        id="amber-night",
        label="Bursztynowa noc",
        description="Espresso ze szampańskim złotem.",
        swatches=("#15120e", "#dbab55", "#211c17"),
    ),
)

THEME_IDS: frozenset[str] = frozenset(t.id for t in THEME_CHOICES)
