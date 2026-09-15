"""On-device OCR.

Uses Tesseract through pytesseract. Nothing leaves the machine: there is no
HTTP client in this module and no cloud vision service anywhere in the
project. If Tesseract is missing we fail loudly with install instructions
rather than silently degrading.

We ask Tesseract for word-level data rather than plain text because the
Government Warning type-size rule (27 CFR 16.22) is a geometric
requirement - we need each word's bounding box in original-image pixels.
"""
import io
import time
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageOps

try:
    import pytesseract
    from pytesseract import Output
except ImportError:  # pragma: no cover - dependency guard
    pytesseract = None
    Output = None

from . import config

# Pillow's own decompression-bomb guard, aligned with our configured limit.
Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS


class OcrUnavailable(RuntimeError):
    """Raised when the local Tesseract engine cannot be used."""


@dataclass
class Word:
    text: str
    conf: float
    left: int
    top: int
    width: int
    height: int
    line_key: Tuple[int, int, int]

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


@dataclass
class OcrResult:
    text: str
    words: List[Word] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0
    # Millimetres per pixel in the ORIGINAL image, when physical scale is
    # known. None means absolute type size cannot be verified.
    mm_per_px: Optional[float] = None
    scale_source: str = "unknown"
    elapsed: float = 0.0
    passes: List[str] = field(default_factory=list)
    truncated: bool = False

    def lines(self) -> List[List[Word]]:
        """Words grouped into text lines, in reading order."""
        grouped: Dict[Tuple[int, int, int], List[Word]] = {}
        for word in self.words:
            grouped.setdefault(word.line_key, []).append(word)
        ordered = []
        for key in sorted(grouped, key=lambda k: (
            min(w.top for w in grouped[k]), min(w.left for w in grouped[k])
        )):
            ordered.append(sorted(grouped[key], key=lambda w: w.left))
        return ordered

    def low_confidence_words(self) -> List[Word]:
        return [w for w in self.words if w.conf < config.LOW_CONFIDENCE]


def ensure_available() -> str:
    """Return the local Tesseract version, or raise with how to install it."""
    if pytesseract is None:
        raise OcrUnavailable(
            "The 'pytesseract' Python package is not installed. "
            "Run: pip install -r requirements.txt"
        )
    try:
        return str(pytesseract.get_tesseract_version())
    except Exception as exc:  # pragma: no cover - environment dependent
        raise OcrUnavailable(
            "The Tesseract OCR engine was not found on this computer. "
            "Install it with one of:\n"
            "  Ubuntu/Debian:  sudo apt-get install tesseract-ocr\n"
            "  macOS:          brew install tesseract\n"
            "  Windows:        https://github.com/UB-Mannheim/tesseract/wiki\n"
            f"Original error: {exc}"
        ) from exc


def load_image(data: bytes) -> Image.Image:
    """Decode bytes into an image, validating the format allowlist."""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Image.DecompressionBombError as exc:
        raise ValueError(
            "This image is unusually large and was rejected as a safety "
            "precaution. Please supply a normal label image."
        ) from exc
    except Exception as exc:
        raise ValueError(
            "That file could not be read as an image. Accepted types are "
            "PNG, JPEG, TIFF, BMP, WEBP and GIF."
        ) from exc

    if image.format and image.format.upper() not in config.ALLOWED_IMAGE_FORMATS:
        raise ValueError(
            f"Image format {image.format} is not accepted. Use PNG, JPEG, "
            "TIFF, BMP, WEBP or GIF."
        )
    return image


def _physical_scale(image: Image.Image,
                    label_width_mm: Optional[float]) -> Tuple[Optional[float], str]:
    """Millimetres per pixel of the original image, and how we know.

    Preference order: the operator's measured label width (authoritative),
    then the file's own DPI metadata (often absent or wrong), then nothing -
    in which case absolute type size is reported as unverifiable rather than
    guessed at.
    """
    if label_width_mm and label_width_mm > 0:
        return label_width_mm / image.width, "measured label width"

    dpi = image.info.get("dpi")
    if dpi:
        try:
            horizontal = float(dpi[0])
        except (TypeError, ValueError, IndexError):
            horizontal = 0.0
        # Treat the Pillow/JPEG default of 72 as "no real information": it is
        # what gets written when software has nothing better to record.
        if horizontal >= 96:
            return 25.4 / horizontal, f"image metadata ({horizontal:g} DPI)"
    return None, "unknown"


def _prepare(image: Image.Image) -> Tuple[Image.Image, float]:
    """Grayscale, contrast-normalise and rescale. Returns (image, scale)."""
    if image.mode in ("RGBA", "LA", "P"):
        # Flatten transparency onto white; label art is usually on white.
        background = Image.new("RGB", image.size, (255, 255, 255))
        converted = image.convert("RGBA")
        background.paste(converted, mask=converted.split()[-1])
        image = background
    prepared = image.convert("L")
    prepared = ImageOps.autocontrast(prepared, cutoff=1)

    longest = max(prepared.size)
    scale = 1.0
    if longest > config.MAX_OCR_DIMENSION:
        scale = config.MAX_OCR_DIMENSION / longest
    elif longest < config.MIN_OCR_DIMENSION:
        # Upscaling small artwork measurably improves recall on small print
        # such as the health warning.
        scale = min(config.MIN_OCR_DIMENSION / longest, 3.0)

    if scale != 1.0:
        new_size = (max(1, round(prepared.width * scale)),
                    max(1, round(prepared.height * scale)))
        prepared = prepared.resize(new_size, Image.LANCZOS)
    return prepared, scale


def _run_pass(prepared: Image.Image, psm: int, timeout: float) -> List[dict]:
    config_flags = f"--oem 1 --psm {psm} -c preserve_interword_spaces=1"
    data = pytesseract.image_to_data(
        prepared, output_type=Output.DICT, config=config_flags,
        timeout=max(0.5, timeout),
    )
    rows = []
    for index, raw_text in enumerate(data["text"]):
        text = (raw_text or "").strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][index])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < 0:
            continue
        rows.append({
            "text": text,
            "conf": conf,
            "left": data["left"][index],
            "top": data["top"][index],
            "width": data["width"][index],
            "height": data["height"][index],
            "line_key": (data["block_num"][index], data["par_num"][index],
                         data["line_num"][index]),
        })
    return rows


def _run_banded_pass(prepared: Image.Image, psm: int, timeout: float,
                     bands: int = 2, overlap: float = 0.15) -> List[dict]:
    """OCR the image in overlapping horizontal bands.

    Tesseract sizes its noise filter against the dominant text on the page.
    On label artwork a very large brand name can therefore suppress the much
    smaller mandatory print - the alcohol content and net contents simply do
    not appear in the results, even though they are perfectly legible in
    isolation. Splitting the image into bands puts text of a similar size
    together in each pass and recovers it.

    Bands overlap so that a line falling on a boundary is still read whole in
    one of them. Duplicate readings are harmless: matching is fuzzy, and
    repeated lines are collapsed for display.
    """
    height = prepared.height
    step = max(1, height // bands)
    margin = int(step * overlap)
    collected: List[dict] = []
    deadline = time.monotonic() + timeout

    for index in range(bands):
        remaining = deadline - time.monotonic()
        if remaining <= 0.3:
            break
        top = max(0, index * step - margin)
        bottom = min(height, (index + 1) * step + margin)
        if bottom - top < 20:
            continue
        band = prepared.crop((0, top, prepared.width, bottom))
        try:
            rows = _run_pass(band, psm, remaining)
        except Exception:
            continue
        # Band coordinates are relative to the crop; shift them back.
        for row in rows:
            row["top"] += top
            row["line_key"] = (row["line_key"][0] + 500 * (index + 1),
                               row["line_key"][1], row["line_key"][2])
        collected.extend(rows)
    return collected


def _rows_to_words(rows: List[dict], scale: float, psm: int) -> List[Word]:
    inverse = 1.0 / scale if scale else 1.0
    words = []
    for row in rows:
        words.append(Word(
            text=row["text"],
            conf=row["conf"],
            left=round(row["left"] * inverse),
            top=round(row["top"] * inverse),
            width=round(row["width"] * inverse),
            height=round(row["height"] * inverse),
            # Namespace the line key by pass so two passes never merge lines.
            line_key=(psm * 1000 + row["line_key"][0],
                      row["line_key"][1], row["line_key"][2]),
        ))
    return words


def _joined_text(words: List[Word]) -> str:
    """Words assembled into lines, in reading order, without repeats.

    Several passes read the same artwork, so the same line often appears more
    than once. Duplicates do no harm to matching, but they make the "what the
    computer read" panel confusing, so identical lines are collapsed.
    """
    grouped: Dict[Tuple[int, int, int], List[Word]] = {}
    for word in words:
        grouped.setdefault(word.line_key, []).append(word)
    lines = []
    seen = set()
    for key in sorted(grouped, key=lambda k: (
        min(w.top for w in grouped[k]), min(w.left for w in grouped[k])
    )):
        ordered = sorted(grouped[key], key=lambda w: w.left)
        text = " ".join(w.text for w in ordered)
        fingerprint = " ".join(text.split()).lower()
        if fingerprint and fingerprint in seen:
            continue
        seen.add(fingerprint)
        lines.append(text)
    return "\n".join(lines)


def read_label(data: bytes, label_width_mm: Optional[float] = None,
               deadline: Optional[float] = None) -> OcrResult:
    """OCR a label image, staying inside the time budget.

    A first sparse-text pass handles scattered display type (brand, class,
    net contents). If that pass does not turn up the Government Warning and
    there is time left, a second block-text pass is run, because the warning
    is a dense paragraph that a sparse model can miss. Results are merged.
    """
    ensure_available()
    started = time.monotonic()
    if deadline is None:
        deadline = started + config.OCR_BUDGET_SECONDS

    image = load_image(data)
    original_size = image.size
    mm_per_px, scale_source = _physical_scale(image, label_width_mm)
    prepared, scale = _prepare(image)

    words: List[Word] = []
    passes: List[str] = []
    truncated = False

    remaining = deadline - time.monotonic()
    rows = _run_pass(prepared, 11, remaining)
    words.extend(_rows_to_words(rows, scale, 11))
    passes.append("sparse text (psm 11)")

    # Banded pass: recovers smaller mandatory print that a dominant brand
    # name can hide from the whole-image pass. See _run_banded_pass.
    remaining = deadline - time.monotonic()
    if remaining > 0.8:
        band_rows = _run_banded_pass(prepared, 11, min(remaining - 0.3, 1.5))
        if band_rows:
            words.extend(_rows_to_words(band_rows, scale, 13))
            passes.append("banded sparse text")

    text_so_far = _joined_text(words).lower()
    needs_second_pass = "government" not in text_so_far or "surgeon" not in text_so_far
    remaining = deadline - time.monotonic()
    if needs_second_pass and remaining > 0.8:
        try:
            rows = _run_pass(prepared, 6, remaining)
            words.extend(_rows_to_words(rows, scale, 6))
            passes.append("block text (psm 6)")
        except Exception:
            # A timeout or engine hiccup on the optional pass must not lose
            # the results we already have.
            truncated = True
    elif needs_second_pass:
        truncated = True

    return OcrResult(
        text=_joined_text(words),
        words=words,
        image_width=original_size[0],
        image_height=original_size[1],
        mm_per_px=mm_per_px,
        scale_source=scale_source,
        elapsed=time.monotonic() - started,
        passes=passes,
        truncated=truncated,
    )


def merge_results(results: List[OcrResult]) -> OcrResult:
    """Combine several panels into one result for text comparison.

    A container's mandatory information is often split across a front and a
    back label, so a field is "on the label" if it appears on any panel. This
    merges the text for that purpose.

    Geometry deliberately does NOT survive the merge: `mm_per_px` is cleared,
    because two panels can be photographed at different scales and a single
    conversion factor would be wrong for at least one of them. Any check that
    measures physical size must run against an individual panel instead.
    """
    if not results:
        return OcrResult(text="")
    if len(results) == 1:
        return results[0]

    words: List[Word] = []
    for index, result in enumerate(results):
        for word in result.words:
            # Namespace each panel's line keys so lines from different
            # pictures can never be grouped into one another.
            block, paragraph, line = word.line_key
            words.append(replace(
                word, line_key=(100_000 * (index + 1) + block, paragraph, line)))

    passes: List[str] = []
    for index, result in enumerate(results, start=1):
        for name in result.passes:
            passes.append(f"picture {index}: {name}")

    return OcrResult(
        text="\n".join(r.text for r in results if r.text),
        words=words,
        image_width=max(r.image_width for r in results),
        image_height=max(r.image_height for r in results),
        mm_per_px=None,
        scale_source="varies by picture",
        elapsed=sum(r.elapsed for r in results),
        passes=passes,
        truncated=any(r.truncated for r in results),
    )
