"""Orchestration: one label in, one report out, inside the time budget."""
import time
from dataclasses import dataclass, field
from typing import List, Optional

from . import compare, config, healthwarning
from .application import ApplicationData
from .findings import Finding, FAIL, PASS, SEVERITY_ORDER, UNKNOWN, WARN, worst
from .ocr import OcrResult, load_image, read_label
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


def check_label(image_bytes: bytes, app: ApplicationData,
                image_name: str = "", deadline: Optional[float] = None) -> LabelReport:
    """Check one label image against one set of application data."""
    started = time.monotonic()
    if deadline is None:
        deadline = started + config.TIME_BUDGET_SECONDS

    bev_rules: BeverageRules = app.rules()
    report = LabelReport(
        reference=app.reference,
        image_name=image_name,
        beverage_class=bev_rules.key,
        beverage_display=bev_rules.display_name,
        beverage_plain=bev_rules.plain_name,
        authority=bev_rules.authority,
    )

    try:
        image = load_image(image_bytes)
    except ValueError as exc:
        report.error = str(exc)
        report.overall = UNKNOWN
        report.elapsed = time.monotonic() - started
        return report

    try:
        ocr_deadline = min(deadline, started + config.OCR_BUDGET_SECONDS)
        result: OcrResult = read_label(
            image_bytes,
            label_width_mm=app.label_width_mm,
            deadline=ocr_deadline,
        )
    except Exception as exc:
        report.error = str(exc)
        report.overall = UNKNOWN
        report.elapsed = time.monotonic() - started
        return report

    report.ocr_elapsed = result.elapsed
    report.ocr_passes = result.passes
    report.scale_source = result.scale_source
    report.ocr_text = result.text

    if result.truncated:
        report.notes.append(
            "Reading the image took longer than expected, so part of the "
            "check may be incomplete. Please look over the results carefully."
        )
    if not result.text.strip():
        report.error = (
            "No text could be read from this image. It may be blurry, very "
            "low resolution, or not a label. Try a sharper picture taken "
            "straight on."
        )
        report.overall = UNKNOWN
        report.elapsed = time.monotonic() - started
        return report

    low_confidence = result.low_confidence_words()
    if len(low_confidence) > max(8, len(result.words) * 0.35):
        report.notes.append(
            "Much of the text on this image was hard to read. A sharper or "
            "larger picture will give a more reliable result."
        )

    # Volume drives the health-warning type-size tier: prefer the declared
    # figure, fall back to what the label itself states.
    volume_ml = app.declared_ml()
    if volume_ml is None:
        from .textnorm import parse_net_contents
        label_volumes = parse_net_contents(result.text)
        if label_volumes:
            volume_ml = label_volumes[0]["ml"]

    grouped: dict = {}

    def collect(findings: List[Finding]):
        for finding in findings:
            grouped.setdefault(finding.field_key, []).append(finding)

    collect(compare.check_brand_name(app, result, bev_rules))
    collect(compare.check_class_type(app, result, bev_rules))
    collect(compare.check_alcohol_content(app, result, bev_rules))
    collect(compare.check_net_contents(app, result, bev_rules))
    collect(compare.check_bottler_name(app, result, bev_rules))
    collect(compare.check_bottler_address(app, result, bev_rules))
    collect(compare.check_country_of_origin(app, result, bev_rules))
    collect(compare.check_sulfites(app, result, bev_rules))
    collect(healthwarning.check(result, volume_ml=volume_ml, image=image))

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
