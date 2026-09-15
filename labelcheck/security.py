"""Security hygiene helpers.

Design position: the safest way to protect sensitive data is not to hold it.
This tool keeps label artwork and company details in memory for the seconds
it takes to check them, then drops them. Nothing is written to a database,
no uploads directory is kept, and nothing is logged beyond timings and
counts.
"""
import os
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Optional

from . import config

# Response headers applied to every page. This is a local single-user tool,
# but a locked-down default costs nothing and prevents an accidental exposure
# if someone ever puts it behind a shared address.
SECURITY_HEADERS = {
    # No third-party scripts, styles, fonts or frames. Everything is served
    # from this app, so the policy can be this tight.
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; object-src 'none'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    # Results contain commercial product data; keep them out of shared caches.
    "Cache-Control": "no-store, max-age=0",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_display_name(name: Optional[str], fallback: str = "label image") -> str:
    """A filename safe to echo back into HTML and CSV.

    Uploaded filenames are attacker-controlled. We never use them to touch
    the filesystem; this only makes them safe to show.
    """
    if not name:
        return fallback
    cleaned = unicodedata.normalize("NFKD", str(name))
    cleaned = os.path.basename(cleaned.replace("\\", "/"))
    cleaned = _SAFE_NAME_RE.sub("_", cleaned).strip("._-")
    return cleaned[:120] or fallback


def has_allowed_suffix(name: str) -> bool:
    return Path(name).suffix.lower() in config.ALLOWED_IMAGE_SUFFIXES


def resolve_within(base_dir: Path, candidate: str) -> Path:
    """Resolve `candidate` under `base_dir`, refusing to escape it.

    Batch CSVs name image files. Those names come from a file the operator
    was given, so they are untrusted: "../../etc/passwd" and absolute paths
    must not resolve outside the batch folder. This also covers zip-slip,
    since extracted entries are resolved through here.
    """
    base = base_dir.resolve()
    raw = (candidate or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("No image file was named.")
    # Drop any leading slash or drive letter so the path is always relative.
    raw = re.sub(r"^[A-Za-z]:", "", raw).lstrip("/")
    target = (base / raw).resolve()
    if target != base and base not in target.parents:
        raise ValueError(
            f"The file name '{candidate}' points outside the batch folder and "
            "was refused."
        )
    return target


def read_limited(stream, limit: int = None) -> bytes:
    """Read at most `limit` bytes, so a huge upload cannot exhaust memory."""
    limit = limit or config.MAX_UPLOAD_BYTES
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(
            f"That file is larger than the {limit // (1024 * 1024)} MB limit."
        )
    return data


# Characters that make a spreadsheet treat a CSV cell as a formula.
_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value) -> str:
    """Neutralise CSV formula injection in exported results.

    Values in our output come from OCR of an uploaded image, so a crafted
    label reading "=cmd|'/c calc'!A1" would otherwise execute when the
    results CSV is opened in Excel.
    """
    text = "" if value is None else str(value)
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    if text.startswith(_CSV_INJECTION_PREFIXES):
        return "'" + text
    return text


def scrub(paths: Iterable[Path]) -> None:
    """Best-effort deletion of temporary files."""
    for path in paths:
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass
