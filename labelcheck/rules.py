"""TTB labelling rules, organised by beverage class.

Citations are to 27 CFR (Alcohol, Tobacco Products and Firearms). They are
included so a reviewer can audit every decision this tool makes against the
regulation itself.

Scope note: standards of fill and the mandatory-field matrix have been
amended several times (notably T.D. TTB-165, 2020). Values below are held in
data, not code, so they can be re-verified and edited without touching
logic. Anything driven by them is reported as an advisory finding, never as
a hard failure, precisely because they move.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# --- Field identifiers -----------------------------------------------------
BRAND_NAME = "brand_name"
CLASS_TYPE = "class_type"
ALCOHOL_CONTENT = "alcohol_content"
NET_CONTENTS = "net_contents"
BOTTLER_NAME = "bottler_name"
BOTTLER_ADDRESS = "bottler_address"
COUNTRY_OF_ORIGIN = "country_of_origin"
SULFITE_DECLARATION = "sulfite_declaration"
HEALTH_WARNING = "health_warning"

FIELD_LABELS = {
    BRAND_NAME: "Brand name",
    CLASS_TYPE: "Class / type",
    ALCOHOL_CONTENT: "Alcohol content",
    NET_CONTENTS: "Net contents",
    BOTTLER_NAME: "Bottler / producer name",
    BOTTLER_ADDRESS: "Bottler / producer address",
    COUNTRY_OF_ORIGIN: "Country of origin",
    SULFITE_DECLARATION: "Sulfite declaration",
    HEALTH_WARNING: "Government Health Warning",
}

# Presentation order on screen and in the results CSV.
FIELD_ORDER = [
    BRAND_NAME, CLASS_TYPE, ALCOHOL_CONTENT, NET_CONTENTS,
    BOTTLER_NAME, BOTTLER_ADDRESS, COUNTRY_OF_ORIGIN,
    SULFITE_DECLARATION, HEALTH_WARNING,
]

# --- Requirement levels ----------------------------------------------------
REQUIRED = "required"        # CFR-mandatory: absence is a failure.
CONDITIONAL = "conditional"  # Mandatory only in some cases; absence is a warning.
OPTIONAL = "optional"        # Not mandatory; checked only if the application declares it.
NOT_APPLICABLE = "n/a"


@dataclass(frozen=True)
class BeverageRules:
    """The rule set for one TTB product class."""
    key: str
    display_name: str
    # Human-readable, plain-English description shown in the UI.
    plain_name: str
    authority: str
    # Percentage-point tolerance between label and application ABV.
    abv_tolerance: float
    abv_tolerance_cite: str
    # Tolerance varies by strength for wine; see abv_tolerance_for().
    abv_tolerance_high: Optional[float] = None
    abv_high_threshold: Optional[float] = None
    # Standards of fill in millilitres. Empty list == no prescribed standard.
    standards_of_fill_ml: List[float] = field(default_factory=list)
    standards_cite: str = ""
    requirements: Dict[str, str] = field(default_factory=dict)
    # True when the Federal Alcohol Administration Act labelling rules
    # apply. False means the product sits outside the FAA Act and is
    # labelled under FDA rules instead.
    faa_act_covered: bool = True
    notes: str = ""

    def abv_tolerance_for(self, abv: Optional[float]) -> float:
        """Tolerance in percentage points, which for wine depends on strength."""
        if (
            self.abv_tolerance_high is not None
            and self.abv_high_threshold is not None
            and abv is not None
            and abv > self.abv_high_threshold
        ):
            return self.abv_tolerance_high
        return self.abv_tolerance

    def requirement(self, field_key: str) -> str:
        return self.requirements.get(field_key, OPTIONAL)


# Standards of fill, in millilitres.
# 27 CFR 5.203 (distilled spirits) and 4.72 (wine), as amended by
# T.D. TTB-165 (2020). Re-verify against the current eCFR before relying on
# these for a real submission; mismatches are reported as advisory.
_SPIRITS_FILL = [
    1800, 1750, 1000, 945, 900, 750, 720, 700, 500, 375, 355, 200, 100, 50,
]
_WINE_FILL = [
    3000, 1500, 1000, 750, 720, 700, 620, 600, 568, 500, 375, 355,
    250, 200, 187, 100, 50,
]

# Mandatory-field matrix per class.
_MALT_REQS = {
    BRAND_NAME: REQUIRED,          # 27 CFR 7.63(a)
    CLASS_TYPE: REQUIRED,          # 27 CFR 7.63(b)
    NET_CONTENTS: REQUIRED,        # 27 CFR 7.63(d)
    BOTTLER_NAME: REQUIRED,        # 27 CFR 7.66
    BOTTLER_ADDRESS: REQUIRED,     # 27 CFR 7.66
    ALCOHOL_CONTENT: CONDITIONAL,  # 27 CFR 7.65 - optional federally, but
                                   # mandatory in several States, and must be
                                   # accurate whenever it does appear.
    COUNTRY_OF_ORIGIN: CONDITIONAL,  # Imports only (19 CFR 134).
    SULFITE_DECLARATION: CONDITIONAL,  # If 10ppm or more.
    HEALTH_WARNING: REQUIRED,      # 27 CFR 16.21
}

_WINE_REQS = {
    BRAND_NAME: REQUIRED,          # 27 CFR 4.32(a)(1)
    CLASS_TYPE: REQUIRED,          # 27 CFR 4.32(a)(2)
    ALCOHOL_CONTENT: REQUIRED,     # 27 CFR 4.32(a)(3), 4.36
    NET_CONTENTS: REQUIRED,        # 27 CFR 4.32(a)(4)
    BOTTLER_NAME: REQUIRED,        # 27 CFR 4.35
    BOTTLER_ADDRESS: REQUIRED,     # 27 CFR 4.35
    COUNTRY_OF_ORIGIN: CONDITIONAL,
    SULFITE_DECLARATION: REQUIRED,  # 27 CFR 4.32(e) - "CONTAINS SULFITES"
                                    # whenever sulphur dioxide is 10ppm or more,
                                    # which covers nearly all commercial wine.
    HEALTH_WARNING: REQUIRED,
}

_SPIRITS_REQS = {
    BRAND_NAME: REQUIRED,          # 27 CFR 5.63(a)
    CLASS_TYPE: REQUIRED,          # 27 CFR 5.63(b), 5.141
    ALCOHOL_CONTENT: REQUIRED,     # 27 CFR 5.63(c), 5.65
    NET_CONTENTS: REQUIRED,        # 27 CFR 5.63(d)
    BOTTLER_NAME: REQUIRED,        # 27 CFR 5.66
    BOTTLER_ADDRESS: REQUIRED,     # 27 CFR 5.66
    COUNTRY_OF_ORIGIN: CONDITIONAL,
    SULFITE_DECLARATION: OPTIONAL,
    HEALTH_WARNING: REQUIRED,
}

# Products under 7% ABV that are not "malt beverages" fall outside the FAA
# Act, so FDA labelling rules apply instead. The health warning still
# applies, because 27 CFR Part 16 reaches every beverage at or above
# 0.5% ABV regardless of which agency governs the rest of the label.
_FDA_REQS = {
    BRAND_NAME: REQUIRED,
    CLASS_TYPE: REQUIRED,
    ALCOHOL_CONTENT: CONDITIONAL,
    NET_CONTENTS: REQUIRED,        # 21 CFR 101.105
    BOTTLER_NAME: REQUIRED,        # 21 CFR 101.5
    BOTTLER_ADDRESS: REQUIRED,
    COUNTRY_OF_ORIGIN: CONDITIONAL,
    SULFITE_DECLARATION: CONDITIONAL,
    HEALTH_WARNING: REQUIRED,      # 27 CFR 16.21 still applies.
}

RULES: Dict[str, BeverageRules] = {
    "malt_beverage": BeverageRules(
        key="malt_beverage",
        display_name="Malt beverage",
        plain_name="Beer or other malt beverage",
        authority="27 CFR Part 7",
        abv_tolerance=0.3,
        abv_tolerance_cite="27 CFR 7.71",
        standards_of_fill_ml=[],
        standards_cite="No federal standard of fill for malt beverages",
        requirements=_MALT_REQS,
        notes="Covers beer, ale, porter, stout, lager and flavoured malt beverages.",
    ),
    "wine": BeverageRules(
        key="wine",
        display_name="Wine",
        plain_name="Wine",
        authority="27 CFR Part 4",
        abv_tolerance=1.5,
        abv_tolerance_high=1.0,
        abv_high_threshold=14.0,
        abv_tolerance_cite="27 CFR 4.36(b)",
        standards_of_fill_ml=_WINE_FILL,
        standards_cite="27 CFR 4.72",
        requirements=_WINE_REQS,
        notes=(
            "Tolerance is 1.5 percentage points at or below 14% ABV and 1.0 "
            "above it, and may never be used to move a wine across the 14% "
            "tax-class line."
        ),
    ),
    "distilled_spirits": BeverageRules(
        key="distilled_spirits",
        display_name="Distilled spirits",
        plain_name="Liquor or spirits",
        authority="27 CFR Part 5",
        abv_tolerance=0.15,
        abv_tolerance_cite="27 CFR 5.65(a)",
        standards_of_fill_ml=_SPIRITS_FILL,
        standards_cite="27 CFR 5.203",
        requirements=_SPIRITS_REQS,
        notes="Covers whisky, vodka, gin, rum, brandy, tequila, cordials and liqueurs.",
    ),
    "cider": BeverageRules(
        key="cider",
        display_name="Hard cider",
        plain_name="Hard cider",
        authority="27 CFR Part 4 (wine) at or above 7% ABV",
        abv_tolerance=1.5,
        abv_tolerance_high=1.0,
        abv_high_threshold=14.0,
        abv_tolerance_cite="27 CFR 4.36(b)",
        standards_of_fill_ml=_WINE_FILL,
        standards_cite="27 CFR 4.72",
        requirements=_WINE_REQS,
        notes=(
            "Cider at or above 7% ABV is labelled as wine. Below 7% ABV it "
            "leaves the FAA Act and is labelled under FDA rules, though the "
            "health warning still applies."
        ),
    ),
    "sake": BeverageRules(
        key="sake",
        display_name="Sake",
        plain_name="Sake (rice wine)",
        authority="27 CFR Part 4",
        abv_tolerance=1.5,
        abv_tolerance_high=1.0,
        abv_high_threshold=14.0,
        abv_tolerance_cite="27 CFR 4.36(b)",
        standards_of_fill_ml=_WINE_FILL,
        standards_cite="27 CFR 4.72",
        requirements=_WINE_REQS,
        notes="Sake is taxed and labelled as wine.",
    ),
    "mead": BeverageRules(
        key="mead",
        display_name="Mead / honey wine",
        plain_name="Mead (honey wine)",
        authority="27 CFR Part 4",
        abv_tolerance=1.5,
        abv_tolerance_high=1.0,
        abv_high_threshold=14.0,
        abv_tolerance_cite="27 CFR 4.36(b)",
        standards_of_fill_ml=_WINE_FILL,
        standards_cite="27 CFR 4.72",
        requirements=_WINE_REQS,
        notes="Honey wine is labelled as wine under Part 4.",
    ),
    "fda_regulated": BeverageRules(
        key="fda_regulated",
        display_name="Non-FAA Act beverage (FDA-labelled)",
        plain_name="Other alcoholic drink (under 7% alcohol)",
        authority="21 CFR Part 101; 27 CFR Part 16 for the health warning",
        abv_tolerance=0.3,
        abv_tolerance_cite="FDA labelling practice",
        standards_of_fill_ml=[],
        standards_cite="No federal standard of fill",
        requirements=_FDA_REQS,
        faa_act_covered=False,
        notes=(
            "These products are labelled under FDA rules, but the "
            "Government Warning is still mandatory at or above 0.5% ABV."
        ),
    ),
}

DEFAULT_CLASS = "distilled_spirits"

# Keywords used to infer the class from the application's class/type text
# when the operator has not stated it outright. Longer, more specific terms
# are matched first so that "apple wine" does not become plain "wine".
_CLASS_KEYWORDS = [
    ("cider", ["hard cider", "cider", "cyder", "perry"]),
    ("sake", ["sake", "saké", "junmai", "ginjo", "nihonshu"]),
    ("mead", ["mead", "honey wine", "melomel", "braggot"]),
    ("malt_beverage", [
        "malt beverage", "flavored malt", "beer", "ale", "lager", "stout",
        "porter", "pilsner", "pilsener", "ipa", "india pale", "hard seltzer",
        "bock", "saison", "hefeweizen", "kolsch", "gose", "wheat beer",
    ]),
    ("distilled_spirits", [
        "distilled spirits", "neutral spirits", "whisky", "whiskey", "bourbon",
        "rye", "scotch", "vodka", "gin", "rum", "brandy", "cognac", "armagnac",
        "tequila", "mezcal", "liqueur", "cordial", "schnapps", "absinthe",
        "grappa", "aquavit", "akvavit", "soju", "shochu", "baijiu", "pisco",
    ]),
    ("wine", [
        "wine", "champagne", "sparkling", "prosecco", "cava", "port", "sherry",
        "madeira", "vermouth", "chardonnay", "cabernet", "merlot", "pinot",
        "riesling", "sauvignon", "zinfandel", "syrah", "shiraz", "malbec",
        "tempranillo", "sangiovese", "moscato", "rose", "rosé",
    ]),
]

# Words an operator might type for the class instead of the internal key.
_CLASS_ALIASES = {
    "beer": "malt_beverage", "malt": "malt_beverage",
    "malt beverage": "malt_beverage", "maltbeverage": "malt_beverage",
    "spirits": "distilled_spirits", "spirit": "distilled_spirits",
    "liquor": "distilled_spirits", "distilled": "distilled_spirits",
    "distilled spirit": "distilled_spirits",
    "distilled spirits": "distilled_spirits",
    "hard cider": "cider", "wine": "wine", "cider": "cider",
    "sake": "sake", "mead": "mead", "other": "fda_regulated",
    "fda": "fda_regulated", "non-alcoholic": "fda_regulated",
}


def resolve_class(stated: Optional[str], class_type_text: Optional[str] = None,
                  abv: Optional[float] = None) -> str:
    """Pick the rule set for a product.

    Uses the operator's stated class when given, otherwise infers it from the
    class/type designation. Low-alcohol cider is redirected to the FDA rule
    set, since it falls outside the FAA Act.
    """
    key = None
    if stated:
        cleaned = stated.strip().lower().replace("_", " ")
        if cleaned.replace(" ", "_") in RULES:
            key = cleaned.replace(" ", "_")
        elif cleaned in _CLASS_ALIASES:
            key = _CLASS_ALIASES[cleaned]

    if key is None and class_type_text:
        haystack = class_type_text.lower()
        for candidate, words in _CLASS_KEYWORDS:
            if any(word in haystack for word in words):
                key = candidate
                break

    if key is None:
        key = DEFAULT_CLASS

    # Cider below 7% ABV is not a Part 4 wine and not a malt beverage; it is
    # labelled under FDA rules while still carrying the health warning.
    if key == "cider" and abv is not None and abv < 7.0:
        return "fda_regulated"
    return key


def get_rules(key: str) -> BeverageRules:
    return RULES.get(key, RULES[DEFAULT_CLASS])


def class_choices():
    """(key, label) pairs for the UI dropdown, in plain English."""
    return [(k, RULES[k].plain_name) for k in [
        "malt_beverage", "wine", "distilled_spirits",
        "cider", "sake", "mead", "fda_regulated",
    ]]
