"""Orchestration: one label in, one report out, inside the time budget."""
import time
from dataclasses import dataclass, field
from typing import List, Optional

from . import compare, config, healthwarning
from .application import ApplicationData
from .findings import Finding, FAIL, PASS, SEVERITY_ORDER, UNKNOWN, WARN, worst
from .ocr import OcrResult, load_image, merge_results, read_label
from .rules import FIELD_LABELS, FIELD_ORDER, BeverageRules

# Overall verdict wording, kept short and unambiguous for on-screen reading.
VERDICT_TEXT = {
    PASS: "PASS - everything matches",
    FAIL: "PROBLEMS FOUND",
    WARN: "CHECK A FEW THINGS BY HAND",
    UNKNOWN: "COULD NOT CHECK EVERYTHING",
}


@dataclass
class FieldResult:
    """All findings for one label field, plus that field's overall verdict."""
    field_key: str
    label: str
    status: str
    findings: List[Finding] = field(default_factory=list)

    @property
    def status_word(self) -> str:
        from .findings import STATUS_WORDS
        return STATUS_WORDS.get(self.status, self.status.upper())


@dataclass
class LabelReport:
    reference: str = ""
    image_name: str = ""
    beverage_class: str = ""
    beverage_display: str = ""
    beverage_plain: str = ""
    authority: str = ""
    overall: str = UNKNOWN
    fields: List[FieldResult] = field(default_factory=list)
    elapsed: float = 0.0
    ocr_elapsed: float = 0.0
    ocr_passes: List[str] = field(default_factory=list)
    scale_source: str = "unknown"
    ocr_text: str = ""
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None
    # One entry per picture supplied, in the order they were given.
    image_names: List[str] = field(default_factory=list)
    # Index of the picture the Government Warning was found on, or None.
    warning_panel: Optional[int] = None

    @property
    def panel_count(self) -> int:
        return max(1, len(self.image_names))

    @property
    def warning_panel_label(self) -> Optional[str]:
        """Which picture carried the warning, when more than one was given."""
        if self.warning_panel is None or self.panel_count < 2:
            return None
        name = (self.image_names[self.warning_panel]
                if self.warning_panel < len(self.image_names) else "")
        position = "front" if self.warning_panel == 0 else "back"
        return f"picture {self.warning_panel + 1} ({position}){f' - {name}' if name else ''}"

    @property
    def verdict(self) -> str:
        if self.error:
            return "COULD NOT CHECK"
        return VERDICT_TEXT.get(self.overall, self.overall.upper())

    @property
    def within_budget(self) -> bool:
        return self.elapsed <= config.TIME_BUDGET_SECONDS

    def all_findings(self) -> List[Finding]:
        return [f for field_result in self.fields for f in field_result.findings]

    def counts(self) -> dict:
        tally = {PASS: 0, FAIL: 0, WARN: 0, UNKNOWN: 0}
        for finding in self.all_findings():
            tally[finding.status] = tally.get(finding.status, 0) + 1
        return tally

    def problem_fields(self) -> List[FieldResult]:
        return [f for f in self.fields if f.status in (FAIL, UNKNOWN, WARN)]


@dataclass
class Panel:
    """One picture of the container, with its own measured physical width."""
    data: bytes
    name: str = ""
    width_mm: Optional[float] = None


def _as_panels(images, app: ApplicationData, image_name: str) -> List["Panel"]:
    """Accept raw bytes, a single Panel, or a list of Panels."""
    if isinstance(images, (bytes, bytearray)):
        return [Panel(bytes(images), image_name, app.label_width_mm)]
    if isinstance(images, Panel):
        return [images]
    return [p for p in images if p is not None and p.data]


def check_label(images, app: ApplicationData, image_name: str = "",
                deadline: Optional[float] = None) -> LabelReport:
    """Check a container's label artwork against its application data.

    `images` may be the bytes of a single picture, or a list of Panels when
    the mandatory information is split across a front and a back label. Text
    is pooled across every picture, so a field counts as present if it
    appears on any panel. Physical measurements stay per-panel, because two
    pictures can be taken at different scales.
    """
    started = time.monotonic()
    if deadline is None:
        deadline = started + config.TIME_BUDGET_SECONDS

    panels = _as_panels(images, app, image_name)
    bev_rules: BeverageRules = app.rules()
    report = LabelReport(
        reference=app.reference,
        image_name=", ".join(p.name for p in panels if p.name) or image_name,
        image_names=[p.name for p in panels],
        beverage_class=bev_rules.key,
        beverage_display=bev_rules.display_name,
        beverage_plain=bev_rules.plain_name,
        authority=bev_rules.authority,
    )

    if not panels:
        report.error = "No label picture was supplied."
        report.overall = UNKNOWN
        report.elapsed = time.monotonic() - started
        return report

    # --- Read every panel, sharing the OCR budget fairly between them ------
    ocr_deadline = min(deadline, started + config.OCR_BUDGET_SECONDS)
    scans: List[tuple] = []          # (OcrResult, PIL image)
    results: List[OcrResult] = []

    for index, panel in enumerate(panels):
        try:
            image = load_image(panel.data)
        except ValueError as exc:
            if index == 0:
                report.error = str(exc)
                report.overall = UNKNOWN
                report.elapsed = time.monotonic() - started
                return report
            # A bad second picture must not throw away a good first one.
            report.notes.append(
                f"Picture {index + 1} could not be read and was skipped: {exc}")
            continue

        now = time.monotonic()
        share = (ocr_deadline - now) / max(1, len(panels) - index)
        try:
            result = read_label(
                panel.data,
                label_width_mm=panel.width_mm,
                deadline=now + max(0.5, share),
            )
        except Exception as exc:
            if index == 0:
                report.error = str(exc)
                report.overall = UNKNOWN
                report.elapsed = time.monotonic() - started
                return report
            report.notes.append(
                f"Picture {index + 1} could not be read and was skipped: "
                f"{type(exc).__name__}")
            continue

        scans.append((result, image))
        results.append(result)

    if not results:
        report.error = "None of the supplied pictures could be read."
        report.overall = UNKNOWN
        report.elapsed = time.monotonic() - started
        return report

    combined = merge_results(results)
    report.ocr_elapsed = combined.elapsed
    report.ocr_passes = combined.passes
    report.scale_source = (results[0].scale_source if len(results) == 1
                           else combined.scale_source)
    report.ocr_text = combined.text

    if combined.truncated:
        report.notes.append(
            "Reading the pictures took longer than expected, so part of the "
            "check may be incomplete. Please look over the results carefully."
        )
    if not combined.text.strip():
        report.error = (
            "No text could be read from "
            + ("this image" if len(results) == 1 else "these images")
            + ". They may be blurry, very low resolution, or not labels. Try "
            "a sharper picture taken straight on."
        )
        report.overall = UNKNOWN
        report.elapsed = time.monotonic() - started
        return report

    low_confidence = combined.low_confidence_words()
    if len(low_confidence) > max(8, len(combined.words) * 0.35):
        report.notes.append(
            "Much of the text was hard to read. A sharper or larger picture "
            "will give a more reliable result."
        )

    # Volume drives the health-warning type-size tier: prefer the declared
    # figure, fall back to what the label itself states.
    volume_ml = app.declared_ml()
    if volume_ml is None:
        from .textnorm import parse_net_contents
        label_volumes = parse_net_contents(combined.text)
        if label_volumes:
            volume_ml = label_volumes[0]["ml"]

    grouped: dict = {}

    def collect(findings: List[Finding]):
        for finding in findings:
            grouped.setdefault(finding.field_key, []).append(finding)

    # Text fields are checked against the pooled text of every panel.
    collect(compare.check_brand_name(app, combined, bev_rules))
    collect(compare.check_class_type(app, combined, bev_rules))
    collect(compare.check_alcohol_content(app, combined, bev_rules))
    collect(compare.check_net_contents(app, combined, bev_rules))
    collect(compare.check_bottler_name(app, combined, bev_rules))
    collect(compare.check_bottler_address(app, combined, bev_rules))
    collect(compare.check_country_of_origin(app, combined, bev_rules))
    collect(compare.check_sulfites(app, combined, bev_rules))

    # The warning is measured on whichever panel actually carries it.
    warning_findings, warning_panel = healthwarning.check_panels(
        scans, volume_ml=volume_ml)
    report.warning_panel = warning_panel
    collect(warning_findings)

    for field_key in FIELD_ORDER:
        findings = grouped.get(field_key)
        if not findings:
            continue
        findings.sort(key=lambda f: SEVERITY_ORDER.get(f.status, 9))
        report.fields.append(FieldResult(
            field_key=field_key,
            label=FIELD_LABELS[field_key],
            status=worst(findings),
            findings=findings,
        ))

    # Advisory findings (house style, shifting standards of fill) must never
    # be the sole reason a label is reported as failing.
    binding = [f.status for f in report.all_findings() if not f.advisory]
    report.overall = (
        min(binding, key=lambda s: SEVERITY_ORDER.get(s, 9)) if binding else UNKNOWN
    )

    report.elapsed = time.monotonic() - started
    if not report.within_budget:
        report.notes.append(
            f"This check took {report.elapsed:.1f} seconds, longer than the "
            f"{config.TIME_BUDGET_SECONDS:g}-second target."
        )
    return report
