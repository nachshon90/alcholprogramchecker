"""A single finding: one check, one verdict, in plain English."""
from dataclasses import dataclass, field
from typing import List, Optional

PASS = "pass"        # Checked and compliant.
FAIL = "fail"        # Checked and non-compliant. Blocks approval.
WARN = "warn"        # Advisory: verify by hand.
UNKNOWN = "unknown"  # Could not be checked; needs a human.

# Ranked worst-first, for sorting and for the overall verdict.
SEVERITY_ORDER = {FAIL: 0, UNKNOWN: 1, WARN: 2, PASS: 3}

STATUS_WORDS = {
    PASS: "MATCH",
    FAIL: "PROBLEM",
    WARN: "CHECK BY HAND",
    UNKNOWN: "CANNOT CHECK",
}


@dataclass
class Finding:
    field_key: str
    title: str
    status: str
    detail: str                      # Plain-English explanation.
    expected: Optional[str] = None   # What the application says.
    found: Optional[str] = None      # What the label appears to say.
    cite: Optional[str] = None       # Governing regulation.
    advisory: bool = False           # True when this is house style, not law.

    @property
    def status_word(self) -> str:
        return STATUS_WORDS.get(self.status, self.status.upper())

    def as_dict(self) -> dict:
        return {
            "field": self.field_key, "title": self.title,
            "status": self.status, "status_word": self.status_word,
            "detail": self.detail, "expected": self.expected,
            "found": self.found, "cite": self.cite, "advisory": self.advisory,
        }


def worst(findings: List[Finding]) -> str:
    """The overall verdict for a group of findings."""
    if not findings:
        return UNKNOWN
    return min((f.status for f in findings), key=lambda s: SEVERITY_ORDER.get(s, 9))
