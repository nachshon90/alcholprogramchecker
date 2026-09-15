"""Batch checking: one CSV plus a folder or ZIP of label images.

The batch path exists so a reviewer can clear a stack of labels in one go
rather than one at a time. It reuses exactly the same checks as the single
label path - there is no second, looser rule set.

Nothing is retained. A ZIP is expanded into a temporary directory that is
deleted in a finally block whether or not the run succeeds.
"""
import csv
import io
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import config, security
from .application import ApplicationData, rows_from_csv
from .checker import LabelReport, Panel, check_label
from .findings import FAIL, PASS, UNKNOWN, WARN
from .rules import FIELD_LABELS, FIELD_ORDER

# A ZIP that expands to far more than it claims is a classic denial-of-service.
MAX_ZIP_ENTRIES = 2000
MAX_TOTAL_UNCOMPRESSED = 400 * 1024 * 1024


class BulkError(ValueError):
    """Raised when a batch cannot be started at all."""


@dataclass
class BulkSummary:
    reports: List[LabelReport] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    elapsed: float = 0.0

    def counts(self) -> Dict[str, int]:
        tally = {PASS: 0, FAIL: 0, WARN: 0, UNKNOWN: 0}
        for report in self.reports:
            key = UNKNOWN if report.error else report.overall
            tally[key] = tally.get(key, 0) + 1
        return tally

    @property
    def total(self) -> int:
        return len(self.reports)

    @property
    def passed(self) -> int:
        return self.counts()[PASS]

    @property
    def failed(self) -> int:
        return self.counts()[FAIL]

    @property
    def needs_attention(self) -> int:
        tally = self.counts()
        return tally[WARN] + tally[UNKNOWN]

    @property
    def average_seconds(self) -> float:
        return (self.elapsed / self.total) if self.total else 0.0


def extract_zip(data: bytes, destination: Path) -> List[str]:
    """Safely expand an uploaded ZIP. Returns warnings."""
    warnings: List[str] = []
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise BulkError("That file is not a valid ZIP file.") from exc

    entries = archive.infolist()
    if len(entries) > MAX_ZIP_ENTRIES:
        raise BulkError(
            f"That ZIP holds more than {MAX_ZIP_ENTRIES} files, which is more "
            "than this tool will open at once."
        )
    declared_total = sum(entry.file_size for entry in entries)
    if declared_total > MAX_TOTAL_UNCOMPRESSED:
        raise BulkError(
            "That ZIP expands to more than 400 MB, which is more than this "
            "tool will open at once."
        )

    for entry in entries:
        if entry.is_dir():
            continue
        # Refuse anything that tries to escape the extraction folder, and
        # anything that is not a plain file.
        if (entry.external_attr >> 28) == 0xA:  # symbolic link
            warnings.append(f"Skipped a shortcut inside the ZIP: {entry.filename}")
            continue
        try:
            target = security.resolve_within(destination, entry.filename)
        except ValueError:
            warnings.append(f"Skipped an unsafe path inside the ZIP: {entry.filename}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(entry) as source, target.open("wb") as sink:
            shutil.copyfileobj(source, sink, length=64 * 1024)
    return warnings


def _find_image(base_dir: Path, named: str) -> Optional[Path]:
    """Locate the image a CSV row names, tolerating small path differences.

    Operators zip up a folder, so paths in the CSV often carry a leading
    directory that is not in the archive, or vice versa. We try the exact
    path first, then fall back to matching on file name alone.
    """
    try:
        exact = security.resolve_within(base_dir, named)
    except ValueError:
        return None
    if exact.is_file():
        return exact

    wanted = Path(named.replace("\\", "/")).name.lower()
    if not wanted:
        return None
    for candidate in base_dir.rglob("*"):
        if candidate.is_file() and candidate.name.lower() == wanted:
            return candidate
    return None


def run_batch(csv_text: str, image_root: Path) -> BulkSummary:
    """Check every row of a batch CSV against images under `image_root`."""
    started = time.monotonic()
    rows, warnings = rows_from_csv(csv_text)
    summary = BulkSummary(warnings=list(warnings))

    for app in rows:
        report = _check_row(app, image_root)
        summary.reports.append(report)

    summary.elapsed = time.monotonic() - started
    return summary


def _check_row(app: ApplicationData, image_root: Path) -> LabelReport:
    """Check one row, turning any failure into a reported error, not a crash.

    A row may name one picture or two (a front and a back label). A single
    unreadable file must not abandon the rest of the batch.
    """
    entries = app.panels()
    display_name = security.safe_display_name(app.image_path, "(no file named)")
    if not entries:
        return _error_report(app, display_name,
                             "This row does not name a label image file.")

    panels: List[Panel] = []
    problems: List[str] = []

    for position, (named, width_mm) in enumerate(entries, start=1):
        label = security.safe_display_name(named, f"picture {position}")
        where = "" if len(entries) == 1 else f"Picture {position}: "

        if not security.has_allowed_suffix(named):
            problems.append(
                f"{where}'{label}' is not an image type the tool accepts. Use "
                "PNG, JPEG, TIFF, BMP, WEBP or GIF.")
            continue

        path = _find_image(image_root, named)
        if path is None:
            problems.append(
                f"{where}'{label}' could not be found. Check that the file "
                "name in the CSV matches the file you supplied.")
            continue

        try:
            if path.stat().st_size > config.MAX_UPLOAD_BYTES:
                problems.append(
                    f"{where}'{label}' is larger than the "
                    f"{config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")
                continue
            panels.append(Panel(path.read_bytes(), label, width_mm))
        except OSError as exc:
            problems.append(f"{where}'{label}' could not be read: {exc.strerror}")

    if not panels:
        return _error_report(app, display_name, " ".join(problems)
                             or "No label picture could be read for this row.")

    try:
        report = check_label(panels, app)
    except Exception as exc:  # pragma: no cover - last-resort guard
        return _error_report(app, display_name,
                             f"This label could not be checked: {type(exc).__name__}")

    # A missing second picture is worth saying, but must not hide the result
    # obtained from the picture that did load.
    for problem in problems:
        report.notes.append(problem)
    return report


def _error_report(app: ApplicationData, image_name: str, message: str) -> LabelReport:
    bev_rules = app.rules()
    return LabelReport(
        reference=app.reference,
        image_name=image_name,
        beverage_class=bev_rules.key,
        beverage_display=bev_rules.display_name,
        beverage_plain=bev_rules.plain_name,
        authority=bev_rules.authority,
        overall=UNKNOWN,
        error=message,
    )


# --- Results export --------------------------------------------------------
RESULT_COLUMNS = (
    ["reference", "image", "image_2", "pictures_checked", "beverage_type",
     "overall_result", "seconds"]
    + [FIELD_LABELS[key] for key in FIELD_ORDER]
    + ["problems", "notes"]
)


def results_csv(summary: BulkSummary) -> str:
    """Render batch results as a CSV, safe to open in a spreadsheet."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(RESULT_COLUMNS)

    for report in summary.reports:
        by_field = {f.field_key: f for f in report.fields}
        problems = "; ".join(
            f"{f.title}" for f in report.all_findings()
            if f.status in (FAIL, WARN, UNKNOWN)
        )
        names = report.image_names or [report.image_name]
        row = [
            report.reference,
            names[0] if names else "",
            names[1] if len(names) > 1 else "",
            len(names),
            report.beverage_display,
            "COULD NOT CHECK" if report.error else report.verdict,
            f"{report.elapsed:.2f}",
        ]
        for key in FIELD_ORDER:
            field_result = by_field.get(key)
            row.append(field_result.status_word if field_result else "not checked")
        row.append(report.error or problems)
        row.append(" ".join(report.notes))
        writer.writerow([security.csv_safe(cell) for cell in row])
    return buffer.getvalue()


def run_uploaded_batch(csv_text: str, zip_bytes: Optional[bytes] = None,
                       folder: Optional[str] = None) -> BulkSummary:
    """Run a batch from an uploaded ZIP, or from a folder on this computer.

    Any temporary extraction is removed before returning, on every path.
    """
    if zip_bytes:
        temp_dir = Path(tempfile.mkdtemp(prefix="labelcheck-"))
        try:
            zip_warnings = extract_zip(zip_bytes, temp_dir)
            summary = run_batch(csv_text, temp_dir)
            summary.warnings = zip_warnings + summary.warnings
            return summary
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    if folder:
        root = Path(folder).expanduser()
        if not root.is_dir():
            raise BulkError(
                f"The folder '{folder}' could not be found on this computer.")
        return run_batch(csv_text, root)

    raise BulkError(
        "Please supply the label images, either as a ZIP file or as a folder "
        "on this computer.")
