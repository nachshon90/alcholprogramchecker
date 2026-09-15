"""Runtime configuration.

Everything here is local-only by design. No cloud services, no telemetry,
no outbound calls unless the operator explicitly turns on the TTB lookup.
"""
import os


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _num(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


# --- Performance -----------------------------------------------------------
# Hard budget for a single label. The requirement is "results in 5 seconds
# or less", so OCR is given a slightly smaller slice to leave room for
# parsing, comparison and rendering.
TIME_BUDGET_SECONDS = _num("LABELCHECK_TIME_BUDGET", 5.0)
OCR_BUDGET_SECONDS = _num("LABELCHECK_OCR_BUDGET", 3.5)

# Images are downscaled before OCR. Tesseract gains nothing from more than
# ~2000px on the long edge for label artwork, and it costs real time.
MAX_OCR_DIMENSION = int(_num("LABELCHECK_MAX_DIM", 2000))
# Small images are upscaled instead: tiny text OCRs poorly below ~1000px.
MIN_OCR_DIMENSION = int(_num("LABELCHECK_MIN_DIM", 1000))

# --- Uploads / security ----------------------------------------------------
MAX_UPLOAD_BYTES = int(_num("LABELCHECK_MAX_UPLOAD", 25 * 1024 * 1024))
MAX_BATCH_ROWS = int(_num("LABELCHECK_MAX_BATCH_ROWS", 500))
# Guard against decompression bombs (a 100MP image from a 40KB file).
MAX_IMAGE_PIXELS = int(_num("LABELCHECK_MAX_PIXELS", 60_000_000))
ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "TIFF", "BMP", "WEBP", "GIF"}
ALLOWED_IMAGE_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif",
}

# --- Compliance policy -----------------------------------------------------
# 27 CFR 16.21 requires only the words "GOVERNMENT WARNING" to be in capital
# letters and bold. It does NOT require the rest of the statement to be all
# caps. Operators who want the stricter house style (whole statement in
# capitals) leave this on; findings it raises are reported as advisory, and
# clearly labelled as house style rather than as a federal requirement.
REQUIRE_FULL_CAPS_WARNING = _flag("LABELCHECK_FULL_CAPS", True)

# Fuzzy-match threshold for text fields. OCR of stylised label artwork is
# noisy, so an exact string compare would produce constant false mismatches.
MATCH_THRESHOLD = _num("LABELCHECK_MATCH_THRESHOLD", 0.86)
# Below this, we report "not found on label" rather than "mismatch".
PRESENCE_THRESHOLD = _num("LABELCHECK_PRESENCE_THRESHOLD", 0.55)
# OCR words below this confidence are kept but flagged as low-confidence.
LOW_CONFIDENCE = _num("LABELCHECK_LOW_CONFIDENCE", 45.0)

# --- Optional TTB.gov lookup -----------------------------------------------
# OFF by default, and the tool is fully functional without it. See
# labelcheck/application.py and the README section "Where application data
# comes from": TTB publishes its public label data as an HTML search form
# rather than a machine-readable API, and outbound access is normally
# firewalled in the review environment. Application data is therefore
# supplied by the operator (web form or CSV) as the primary path.
ENABLE_TTB_LOOKUP = _flag("LABELCHECK_ENABLE_TTB_LOOKUP", False)
TTB_PUBLIC_REGISTRY_URL = "https://ttbonline.gov/colasonline/publicSearchColasBasic.do"
TTB_LOOKUP_TIMEOUT = _num("LABELCHECK_TTB_TIMEOUT", 4.0)
