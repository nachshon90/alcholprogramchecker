"""The Government Warning check - 27 CFR Part 16.

This is the strictest check in the tool, and deliberately so. The warning is
mandatory on every alcoholic beverage at or above 0.5% alcohol by volume
sold in the United States, and it has requirements that go beyond wording:

  16.21  Exact statement text. The words "GOVERNMENT WARNING" must be in
         capital letters and bold type. The statement must be separate and
         apart from all other information.
  16.22  Minimum type size, by container volume:
             237 mL (8 fl oz) or less ......... 1 mm
             over 237 mL up to 3 L ............ 2 mm
             over 3 L ......................... 3 mm
         and no more than 12 characters per inch.

Type size is a physical measurement, so it can only be verified when the
physical scale of the artwork is known. Where it is not, this module reports
"cannot check" rather than guessing - a false pass on a legibility rule is
worse than an honest unknown.
"""
import re
from typing import List, Optional, Tuple

from . import config
from .findings import Finding, FAIL, PASS, UNKNOWN, WARN
from .ocr import OcrResult, Word
from .rules import HEALTH_WARNING
from .textnorm import best_window_similarity, normalize

# The statement exactly as 27 CFR 16.21 prescribes it.
PREFIX = "GOVERNMENT WARNING:"
PART_ONE = (
    "(1) According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects."
)
PART_TWO = (
    "(2) Consumption of alcoholic beverages impairs your ability to drive a "
    "car or operate machinery, and may cause health problems."
)
FULL_STATEMENT = f"{PREFIX} {PART_ONE} {PART_TWO}"

SEGMENTS = [
    ("prefix", PREFIX, "the words GOVERNMENT WARNING"),
    ("part_one", PART_ONE, "part (1), the pregnancy warning"),
    ("part_two", PART_TWO, "part (2), the driving and machinery warning"),
]

# Minimum type size in millimetres, keyed by container volume in millilitres.
SIZE_TIERS = [
    (237.0, 1.0, "containers of 237 mL (8 fl oz) or less"),
    (3000.0, 2.0, "containers over 237 mL and up to 3 L"),
    (float("inf"), 3.0, "containers over 3 L"),
]
MAX_CHARS_PER_INCH = 12.0
MM_PER_INCH = 25.4

# Distinctive vocabulary used to find the warning among all the OCR lines.
_WARNING_VOCAB = set(normalize(FULL_STATEMENT).split())
_ANCHOR_WORDS = {"government", "warning", "surgeon", "pregnancy", "machinery"}


def required_mm(volume_ml: Optional[float]) -> Tuple[float, str, bool]:
    """Minimum type height for a container. Returns (mm, description, assumed)."""
    if volume_ml is None or volume_ml <= 0:
        # Most retail containers fall in the middle tier; say so out loud
        # rather than silently picking it.
        return 2.0, SIZE_TIERS[1][2], True
    for ceiling, minimum, description in SIZE_TIERS:
        if volume_ml <= ceiling:
            return minimum, description, False
    return 3.0, SIZE_TIERS[-1][2], False


def _line_is_warning(words: List[Word]) -> bool:
    """True when an OCR line looks like part of the Government Warning."""
    texts = [normalize(w.text) for w in words]
    texts = [t for t in texts if t]
    if not texts:
        return False
    if any(t in _ANCHOR_WORDS for t in texts):
        return True
    if len(texts) < 3:
        return False
    hits = sum(1 for t in texts if t in _WARNING_VOCAB)
    return hits / len(texts) >= 0.6


def locate_warning(result: OcrResult) -> List[List[Word]]:
    """The OCR lines that make up the warning, in reading order."""
    return [line for line in result.lines() if _line_is_warning(line)]


def _cap_height_mm(lines: List[List[Word]], mm_per_px: float) -> Optional[float]:
    """Measure capital-letter height from the words that must be capitals.

    Word bounding boxes of mixed-case text include descenders, which
    overstates type size. The words "GOVERNMENT" and "WARNING" are required
    to be capitals, so they give a clean cap-height measurement. We fall
    back to all-caps words without descenders elsewhere in the statement.
    """
    candidates: List[int] = []
    for line in lines:
        for word in line:
            stripped = re.sub(r"[^A-Za-z]", "", word.text)
            if not stripped:
                continue
            if stripped.upper() in {"GOVERNMENT", "WARNING"}:
                candidates.append(word.height)
    if not candidates:
        for line in lines:
            for word in line:
                stripped = re.sub(r"[^A-Za-z]", "", word.text)
                if len(stripped) >= 3 and stripped.isupper():
                    candidates.append(word.height)
    if not candidates:
        return None
    candidates.sort()
    median = candidates[len(candidates) // 2]
    return median * mm_per_px


def _max_chars_per_inch(lines: List[List[Word]], mm_per_px: float) -> Optional[float]:
    """Densest line in the warning, in characters per inch."""
    densities = []
    for line in lines:
        if len(line) < 3:
            continue
        left = min(w.left for w in line)
        right = max(w.right for w in line)
        width_px = right - left
        if width_px <= 0:
            continue
        characters = sum(len(w.text) for w in line) + (len(line) - 1)
        width_inches = (width_px * mm_per_px) / MM_PER_INCH
        if width_inches <= 0:
            continue
        densities.append(characters / width_inches)
    return max(densities) if densities else None


def _ink_density(image, words: List[Word]) -> Optional[float]:
    """Fraction of dark pixels inside a set of word boxes.

    Used only as a bold-type hint. Bold glyphs lay down more ink per unit
    area than regular ones at the same size.
    """
    if image is None or not words:
        return None
    try:
        gray = image.convert("L")
    except Exception:
        return None
    dark = 0
    total = 0
    for word in words:
        box = (max(0, word.left), max(0, word.top),
               min(gray.width, word.right), min(gray.height, word.bottom))
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        crop = gray.crop(box)
        area = crop.width * crop.height
        if area <= 0:
            continue
        # A histogram counts the dark pixels without materialising them.
        histogram = crop.histogram()
        total += area
        dark += sum(histogram[:128])
    if total == 0:
        return None
    return dark / total


def check(result: OcrResult, volume_ml: Optional[float] = None,
          image=None) -> List[Finding]:
    """Run every Government Warning check and return the findings."""
    findings: List[Finding] = []
    lines = locate_warning(result)
    warning_words = [w for line in lines for w in line]
    found_text = "\n".join(" ".join(w.text for w in line) for line in lines)

    # --- 1. Is it there at all? -------------------------------------------
    overall_similarity = best_window_similarity(FULL_STATEMENT, result.text)
    if not lines and overall_similarity < 0.45:
        findings.append(Finding(
            field_key=HEALTH_WARNING,
            title="Government Health Warning is missing",
            status=FAIL,
            detail=(
                "The Government Health Warning could not be found anywhere on "
                "this label. Every alcoholic drink of 0.5% alcohol or more "
                "must carry it. If the warning is on another panel of the "
                "container, please check that panel as well."
            ),
            expected=FULL_STATEMENT,
            found="(nothing found)",
            cite="27 CFR 16.21",
        ))
        return findings

    # --- 2. Is the wording right, segment by segment? ---------------------
    missing_segments = []
    for key, segment_text, plain_name in SEGMENTS:
        score = best_window_similarity(segment_text, result.text)
        if score < 0.72:
            missing_segments.append((plain_name, score))

    if missing_segments:
        names = "; ".join(name for name, _ in missing_segments)
        findings.append(Finding(
            field_key=HEALTH_WARNING,
            title="Government Health Warning wording is wrong or incomplete",
            status=FAIL,
            detail=(
                f"This part of the warning is missing or does not match the "
                f"wording the law requires: {names}. The warning must be "
                "printed word for word."
            ),
            expected=FULL_STATEMENT,
            found=found_text or "(not readable)",
            cite="27 CFR 16.21",
        ))
    else:
        findings.append(Finding(
            field_key=HEALTH_WARNING,
            title="Government Health Warning wording is correct",
            status=PASS,
            detail=(
                "All three parts of the warning are present and match the "
                "required wording."
            ),
            expected=FULL_STATEMENT,
            found=found_text,
            cite="27 CFR 16.21",
        ))

    # --- 3. "GOVERNMENT WARNING" must be in capital letters ---------------
    prefix_words = [
        w for w in warning_words
        if re.sub(r"[^A-Za-z]", "", w.text).upper() in {"GOVERNMENT", "WARNING"}
    ]
    if not prefix_words:
        findings.append(Finding(
            field_key=HEALTH_WARNING,
            title="Cannot check capital letters on GOVERNMENT WARNING",
            status=UNKNOWN,
            detail=(
                "The words GOVERNMENT WARNING could not be read clearly "
                "enough to confirm they are in capital letters. Please check "
                "this by eye."
            ),
            cite="27 CFR 16.21",
        ))
    else:
        lowercase = [w.text for w in prefix_words
                     if re.sub(r"[^A-Za-z]", "", w.text)
                     != re.sub(r"[^A-Za-z]", "", w.text).upper()]
        if lowercase:
            findings.append(Finding(
                field_key=HEALTH_WARNING,
                title="GOVERNMENT WARNING is not in capital letters",
                status=FAIL,
                detail=(
                    "The words GOVERNMENT WARNING must be printed in capital "
                    f"letters. On this label they read: {' '.join(lowercase)}."
                ),
                expected="GOVERNMENT WARNING",
                found=" ".join(w.text for w in prefix_words),
                cite="27 CFR 16.21",
            ))
        else:
            findings.append(Finding(
                field_key=HEALTH_WARNING,
                title="GOVERNMENT WARNING is in capital letters",
                status=PASS,
                detail="The words GOVERNMENT WARNING are in capital letters, as required.",
                found=" ".join(w.text for w in prefix_words),
                cite="27 CFR 16.21",
            ))

    # --- 4. House-style check: whole statement in capitals -----------------
    if config.REQUIRE_FULL_CAPS_WARNING and warning_words:
        body = [w for w in warning_words if w not in prefix_words]
        lower_body = [
            w.text for w in body
            if len(re.sub(r"[^A-Za-z]", "", w.text)) >= 3
            and re.sub(r"[^A-Za-z]", "", w.text)
            != re.sub(r"[^A-Za-z]", "", w.text).upper()
        ]
        if lower_body:
            findings.append(Finding(
                field_key=HEALTH_WARNING,
                title="Warning is not entirely in capital letters (house style)",
                status=WARN,
                advisory=True,
                detail=(
                    "Your house style asks for the whole warning in capital "
                    "letters. Some words here are in small letters, for "
                    f"example: {', '.join(lower_body[:6])}. Note that federal "
                    "law only requires the words GOVERNMENT WARNING to be in "
                    "capitals, so this is a style preference, not a legal "
                    "problem."
                ),
                cite="House style (27 CFR 16.21 requires capitals only on GOVERNMENT WARNING)",
            ))
        else:
            findings.append(Finding(
                field_key=HEALTH_WARNING,
                title="Whole warning is in capital letters (house style)",
                status=PASS,
                advisory=True,
                detail="The entire warning is printed in capital letters.",
            ))

    # --- 5. Type size: is it big enough? ----------------------------------
    minimum_mm, tier_description, assumed_tier = required_mm(volume_ml)
    if result.mm_per_px is None:
        findings.append(Finding(
            field_key=HEALTH_WARNING,
            title="Cannot check how big the warning letters are",
            status=UNKNOWN,
            detail=(
                "To check letter height the tool needs to know the real-world "
                "size of the label. Type the label's width in millimetres in "
                "the box on the check page, or supply an image that records "
                "its DPI. Without it, letter height cannot be measured - "
                f"this container needs letters at least {minimum_mm:g} mm tall."
            ),
            cite="27 CFR 16.22",
        ))
    else:
        measured_mm = _cap_height_mm(lines, result.mm_per_px)
        if measured_mm is None:
            findings.append(Finding(
                field_key=HEALTH_WARNING,
                title="Cannot measure the warning letters",
                status=UNKNOWN,
                detail=(
                    "The warning text could not be measured reliably. Please "
                    "check letter height by eye: this container needs letters "
                    f"at least {minimum_mm:g} mm tall."
                ),
                cite="27 CFR 16.22",
            ))
        else:
            assumption = (
                " The container size was not given, so the tool assumed a "
                "normal bottle."
            ) if assumed_tier else ""
            if measured_mm + 0.05 < minimum_mm:
                findings.append(Finding(
                    field_key=HEALTH_WARNING,
                    title="Government Health Warning letters are too small",
                    status=FAIL,
                    detail=(
                        f"The warning letters measure about {measured_mm:.2f} mm "
                        f"tall. The law requires at least {minimum_mm:g} mm for "
                        f"{tier_description}.{assumption}"
                    ),
                    expected=f"at least {minimum_mm:g} mm tall",
                    found=f"about {measured_mm:.2f} mm tall",
                    cite="27 CFR 16.22(a)",
                ))
            else:
                findings.append(Finding(
                    field_key=HEALTH_WARNING,
                    title="Government Health Warning letters are big enough",
                    status=PASS,
                    detail=(
                        f"The warning letters measure about {measured_mm:.2f} mm "
                        f"tall, meeting the {minimum_mm:g} mm minimum for "
                        f"{tier_description}.{assumption}"
                    ),
                    expected=f"at least {minimum_mm:g} mm tall",
                    found=f"about {measured_mm:.2f} mm tall",
                    cite="27 CFR 16.22(a)",
                ))

        # --- 6. No more than 12 characters per inch -----------------------
        density = _max_chars_per_inch(lines, result.mm_per_px)
        if density is not None:
            if density > MAX_CHARS_PER_INCH + 0.5:
                findings.append(Finding(
                    field_key=HEALTH_WARNING,
                    title="Warning text is squeezed too tightly",
                    status=FAIL,
                    detail=(
                        f"The warning is printed at about {density:.1f} characters "
                        f"per inch. The law allows no more than "
                        f"{MAX_CHARS_PER_INCH:g}. The text needs more spacing."
                    ),
                    expected=f"no more than {MAX_CHARS_PER_INCH:g} characters per inch",
                    found=f"about {density:.1f} characters per inch",
                    cite="27 CFR 16.22(b)",
                ))
            else:
                findings.append(Finding(
                    field_key=HEALTH_WARNING,
                    title="Warning text spacing is acceptable",
                    status=PASS,
                    detail=(
                        f"The warning is printed at about {density:.1f} characters "
                        f"per inch, within the limit of {MAX_CHARS_PER_INCH:g}."
                    ),
                    cite="27 CFR 16.22(b)",
                ))

    # --- 7. Bold type hint -------------------------------------------------
    if image is not None and prefix_words:
        body_words = [w for w in warning_words if w not in prefix_words]
        prefix_ink = _ink_density(image, prefix_words)
        body_ink = _ink_density(image, body_words)
        if prefix_ink is not None and body_ink is not None and body_ink > 0:
            ratio = prefix_ink / body_ink
            if ratio < 1.08:
                findings.append(Finding(
                    field_key=HEALTH_WARNING,
                    title="GOVERNMENT WARNING may not be in bold type",
                    status=WARN,
                    detail=(
                        "The words GOVERNMENT WARNING must be in bold type. "
                        "They do not look noticeably heavier than the rest of "
                        "the warning, but this is hard to judge from an image. "
                        "Please confirm by eye."
                    ),
                    cite="27 CFR 16.21",
                ))

    return findings


def check_panels(scans, volume_ml: Optional[float] = None):
    """Check the Government Warning across every supplied panel.

    The warning only ever appears on one panel, but which one varies - on
    many containers it is on the back. Running the check against merged text
    would be wrong, because type size and character density are physical
    measurements that need one panel's own scale.

    So we find the panel actually carrying the warning and measure that one.
    Returns (findings, index of the panel used, or None if not found).

    `scans` is a sequence of (OcrResult, PIL image or None) pairs.
    """
    if not scans:
        return [], None

    best_index = None
    best_evidence = 0
    for index, (result, _image) in enumerate(scans):
        evidence = sum(len(line) for line in locate_warning(result))
        if evidence > best_evidence:
            best_evidence = evidence
            best_index = index

    if best_index is None:
        # Not on any panel. Report against the merged text so the message is
        # about the whole container rather than one picture of it.
        from .ocr import merge_results
        merged = merge_results([result for result, _ in scans])
        return check(merged, volume_ml=volume_ml, image=None), None

    result, image = scans[best_index]
    return check(result, volume_ml=volume_ml, image=image), best_index
