"""Text normalisation, fuzzy matching and unit parsing.

OCR of stylised label artwork is noisy: serifs get read as punctuation,
zeros become letter O, and decorative kerning inserts spaces mid-word. Every
comparison in this tool therefore runs through normalisation first, and uses
windowed fuzzy matching rather than equality.

Standard library only - difflib gives us sequence similarity with no third
party dependency and no network access.
"""
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, List, Optional

# --- Unit conversions ------------------------------------------------------
ML_PER_FL_OZ = 29.5735295625
ML_PER_PINT = 473.176473
ML_PER_QUART = 946.352946
ML_PER_GALLON = 3785.411784

# Characters OCR commonly substitutes inside numbers.
_DIGIT_FIXES = str.maketrans({
    "O": "0", "o": "0", "Q": "0", "D": "0",
    "l": "1", "I": "1", "|": "1", "i": "1",
    "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "G": "6",
})

_PUNCT_RE = re.compile(r"[^\w\s%./-]+", re.UNICODE)
_WS_RE = re.compile(r"\s+")

# Words that carry no distinguishing information when matching company names.
_COMPANY_STOPWORDS = {
    "the", "and", "co", "company", "inc", "incorporated", "llc", "llp", "lp",
    "ltd", "limited", "corp", "corporation", "gmbh", "sa", "sas", "spa",
    "srl", "bv", "nv", "ag", "pty", "plc", "of",
}


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize(value: Optional[str]) -> str:
    """Case-fold, strip accents and punctuation, collapse whitespace."""
    if not value:
        return ""
    text = strip_accents(str(value))
    text = text.replace("&", " and ")
    text = _PUNCT_RE.sub(" ", text)
    text = text.replace("-", " ").replace("/", " ").replace(".", " ")
    text = _WS_RE.sub(" ", text)
    return text.strip().lower()


def tokens(value: Optional[str]) -> List[str]:
    normalized = normalize(value)
    return normalized.split() if normalized else []


def significant_tokens(value: Optional[str]) -> List[str]:
    """Tokens with corporate boilerplate removed, for company-name matching."""
    return [t for t in tokens(value) if t not in _COMPANY_STOPWORDS]


def similarity(a: str, b: str) -> float:
    """Similarity of two already-normalised strings, from 0.0 to 1.0."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def best_window_similarity(needle: str, haystack: str) -> float:
    """Best similarity between `needle` and any same-length run of `haystack`.

    Whole-text similarity is useless here: a correct three-word brand name
    inside 400 words of OCR scores near zero. Instead we slide a window of
    roughly the needle's length across the haystack and keep the best score.
    """
    needle_n = normalize(needle)
    hay_n = normalize(haystack)
    if not needle_n or not hay_n:
        return 0.0
    if needle_n in hay_n:
        return 1.0

    needle_words = needle_n.split()
    hay_words = hay_n.split()
    if not needle_words or not hay_words:
        return 0.0

    span = len(needle_words)
    best = similarity(needle_n, hay_n)
    # Try windows a little shorter and longer than the needle, so a dropped
    # or hallucinated OCR word does not sink an otherwise good match.
    for width in {max(1, span - 1), span, span + 1}:
        if width > len(hay_words):
            continue
        for start in range(0, len(hay_words) - width + 1):
            window = " ".join(hay_words[start:start + width])
            score = similarity(needle_n, window)
            if score > best:
                best = score
                if best >= 0.999:
                    return best
    return best


def token_coverage(needle: str, haystack: str) -> float:
    """Fraction of the needle's significant words that appear in the haystack.

    Complements windowed similarity: it catches the case where a label
    reorders or line-breaks a company name, which shifts character
    positions but keeps every word.
    """
    needle_tokens = significant_tokens(needle)
    if not needle_tokens:
        return 0.0
    hay_words = tokens(haystack)
    if not hay_words:
        return 0.0
    hay_joined = " ".join(hay_words)
    found = 0
    for token in needle_tokens:
        if token in hay_words:
            found += 1
        elif len(token) > 3 and any(
            similarity(token, w) >= 0.85 for w in hay_words
        ):
            found += 1
        elif len(token) > 5 and token in hay_joined.replace(" ", ""):
            # Handles decorative letter-spacing: "B R O O K" -> "brook".
            found += 1
    return found / len(needle_tokens)


def field_match_score(expected: str, ocr_text: str) -> float:
    """Combined score used for free-text label fields."""
    return max(
        best_window_similarity(expected, ocr_text),
        token_coverage(expected, ocr_text),
    )


def fix_ocr_digits(value: str) -> str:
    """Repair letter-for-digit confusions inside an otherwise numeric token."""
    return value.translate(_DIGIT_FIXES)


def _to_float(raw: str) -> Optional[str]:
    cleaned = fix_ocr_digits(raw.strip())
    # European decimal comma, and OCR reading "." as ",".
    cleaned = re.sub(r"(?<=\d),(?=\d)", ".", cleaned)
    cleaned = re.sub(r"[^\d.]", "", cleaned)
    if not cleaned or cleaned.count(".") > 1:
        return None
    return cleaned


# --- Alcohol content -------------------------------------------------------
_ALC_CONTEXT = re.compile(
    r"alc|abv|vol|alcohol|proof|proof|grad", re.IGNORECASE
)
_PERCENT_RE = re.compile(
    r"(?<![\d.])(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:%|percent|per cent)",
    re.IGNORECASE,
)
_PERCENT_LOOSE_RE = re.compile(
    r"(?:alc(?:ohol)?\.?\s*(?:by\s*vol(?:ume)?)?|abv)\s*[:. ]?\s*"
    r"(?<![\d.])(\d{1,2}(?:[.,]\d{1,2})?)\b",
    re.IGNORECASE,
)
_PROOF_RE = re.compile(
    r"(?<![\d.])(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:°\s*)?proof|proof\s*[:. ]?\s*"
    r"(?<![\d.])(\d{1,3}(?:[.,]\d{1,2})?)",
    re.IGNORECASE,
)


def parse_alcohol(text: Optional[str]) -> List[Dict]:
    """Extract every alcohol-strength statement found in `text`.

    Returns dicts of {kind: 'abv'|'proof', value: float, abv: float,
    source: str}. `abv` is always populated, with proof halved, so callers
    can compare a proof-only label against an ABV-only application.
    """
    if not text:
        return []
    results: List[Dict] = []
    seen = set()

    def add(kind: str, raw: str, source: str):
        as_float = _to_float(raw)
        if as_float is None:
            return
        try:
            value = float(as_float)
        except ValueError:
            return
        abv = value / 2.0 if kind == "proof" else value
        # Reject impossible readings rather than reporting a false mismatch.
        if kind == "abv" and not (0.0 <= value <= 100.0):
            return
        if kind == "proof" and not (0.0 <= value <= 200.0):
            return
        key = (kind, round(value, 2))
        if key in seen:
            return
        seen.add(key)
        results.append({"kind": kind, "value": value, "abv": abv,
                        "source": source.strip()})

    for match in _PROOF_RE.finditer(text):
        raw = match.group(1) or match.group(2)
        if raw:
            add("proof", raw, match.group(0))

    for match in _PERCENT_RE.finditer(text):
        window = text[max(0, match.start() - 40):match.end() + 40]
        if _ALC_CONTEXT.search(window):
            add("abv", match.group(1), match.group(0))
        else:
            # A bare percentage with no alcohol context nearby is still worth
            # keeping as a weak candidate (some labels print just "13.5%").
            add("abv", match.group(1), match.group(0))

    for match in _PERCENT_LOOSE_RE.finditer(text):
        add("abv", match.group(1), match.group(0))

    return results


def format_alcohol(entry: Dict) -> str:
    if entry["kind"] == "proof":
        return f"{entry['value']:g} proof ({entry['abv']:g}% ABV)"
    return f"{entry['value']:g}% ABV"


# --- Net contents ----------------------------------------------------------
_UNIT_TO_ML = {
    "ml": 1.0, "milliliter": 1.0, "millilitre": 1.0, "milliliters": 1.0,
    "millilitres": 1.0, "cc": 1.0,
    "l": 1000.0, "liter": 1000.0, "litre": 1000.0, "liters": 1000.0,
    "litres": 1000.0, "lt": 1000.0,
    "cl": 10.0, "centiliter": 10.0, "centilitre": 10.0,
    "dl": 100.0,
    "floz": ML_PER_FL_OZ, "flozs": ML_PER_FL_OZ, "fluidounce": ML_PER_FL_OZ,
    "fluidounces": ML_PER_FL_OZ, "oz": ML_PER_FL_OZ, "ozs": ML_PER_FL_OZ,
    "ounce": ML_PER_FL_OZ, "ounces": ML_PER_FL_OZ,
    "pt": ML_PER_PINT, "pint": ML_PER_PINT, "pints": ML_PER_PINT,
    "qt": ML_PER_QUART, "quart": ML_PER_QUART, "quarts": ML_PER_QUART,
    "gal": ML_PER_GALLON, "gallon": ML_PER_GALLON, "gallons": ML_PER_GALLON,
}

# Matches "750 ML", "1.75 L", "12 FL. OZ.", "25.4 FLOZ", "1 PT 9 FL OZ".
_QTY_RE = re.compile(
    r"(\d{1,4}(?:[.,]\d{1,3})?)\s*"
    r"(fl\.?\s*oz|fluid\s*ounces?|ounces?|oz|ml|milli ?lit(?:er|re)s?|"
    r"cl|centilit(?:er|re)s?|dl|lit(?:er|re)s?|l|lt|pints?|pt|quarts?|qt|"
    r"gallons?|gal|cc)\b\.?",
    re.IGNORECASE,
)


def _unit_key(raw: str) -> str:
    return re.sub(r"[^a-z]", "", raw.lower())


def parse_net_contents(text: Optional[str]) -> List[Dict]:
    """Extract every net-contents statement, normalised to millilitres.

    Handles compound US statements such as "1 PT 9 FL OZ" by summing
    adjacent quantities that sit within a few characters of each other.
    """
    if not text:
        return []
    raw_matches = []
    for match in _QTY_RE.finditer(text):
        as_float = _to_float(match.group(1))
        if as_float is None:
            continue
        try:
            quantity = float(as_float)
        except ValueError:
            continue
        unit = _unit_key(match.group(2))
        factor = _UNIT_TO_ML.get(unit)
        if factor is None or quantity <= 0:
            continue
        raw_matches.append({
            "ml": quantity * factor,
            "quantity": quantity,
            "unit": unit,
            "source": match.group(0).strip(),
            "start": match.start(),
            "end": match.end(),
        })

    # Merge compound imperial statements: "1 PT 9 FL OZ" is one quantity.
    merged: List[Dict] = []
    index = 0
    while index < len(raw_matches):
        current = dict(raw_matches[index])
        step = index + 1
        while (
            step < len(raw_matches)
            and raw_matches[step]["start"] - current["end"] <= 2
            and current["unit"] in {"pt", "pint", "pints", "qt", "quart",
                                    "quarts", "gal", "gallon", "gallons"}
            and raw_matches[step]["unit"] in {"floz", "oz", "ounce", "ounces"}
        ):
            current["ml"] += raw_matches[step]["ml"]
            current["source"] += " " + raw_matches[step]["source"]
            current["end"] = raw_matches[step]["end"]
            step += 1
        merged.append(current)
        index = step

    for entry in merged:
        entry.pop("start", None)
        entry.pop("end", None)
        entry["ml"] = round(entry["ml"], 3)
    return merged


def format_ml(millilitres: float) -> str:
    """Render a millilitre value the way a label would."""
    if millilitres >= 1000 and abs(millilitres / 1000 - round(millilitres / 1000, 2)) < 1e-9:
        return f"{millilitres / 1000:g} L ({millilitres:g} mL)"
    return f"{millilitres:g} mL"
