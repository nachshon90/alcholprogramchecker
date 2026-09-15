"""The application data a label is checked against.

Where this data comes from
--------------------------
Primary path (always available, no network): the operator enters the product
details on the check page, or supplies them as a CSV for a batch run. This is
the data of record that the artwork is compared against.

Optional path: a lookup against TTB's public label data on ttb.gov. It is
OFF by default and the tool is fully functional without it, because:

  1. TTB publishes that data as an HTML search form for people, not as a
     machine-readable API, so any client is screen-scraping and will break
     whenever the page markup changes.
  2. Outbound access to ttb.gov is blocked by the network egress proxy in
     this environment, which is normal for a government review network.

The lookup therefore fails cleanly with an explanation instead of hanging or
crashing, and it never blocks a check. See fetch_from_ttb() below.
"""
import csv
import io
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from . import config, rules
from .textnorm import parse_alcohol, parse_net_contents


class ApplicationDataError(ValueError):
    """Raised when supplied application data cannot be used."""


@dataclass
class ApplicationData:
    """One product's declared details."""
    brand_name: str = ""
    class_type: str = ""
    alcohol_content: str = ""
    net_contents: str = ""
    bottler_name: str = ""
    bottler_address: str = ""
    country_of_origin: str = ""
    beverage_class: str = ""
    is_import: bool = False
    contains_sulfites: Optional[bool] = None
    label_width_mm: Optional[float] = None
    reference: str = ""          # Operator's own reference, e.g. a serial number.
    image_path: str = ""         # Used by batch runs only.

    # --- Derived values ---------------------------------------------------
    def declared_abv(self) -> Optional[float]:
        """Alcohol by volume as a number, accepting proof as an input."""
        parsed = parse_alcohol(self.alcohol_content)
        if not parsed:
            return None
        # Prefer an explicit ABV statement over a proof statement.
        for entry in parsed:
            if entry["kind"] == "abv":
                return entry["abv"]
        return parsed[0]["abv"]

    def declared_ml(self) -> Optional[float]:
        parsed = parse_net_contents(self.net_contents)
        return parsed[0]["ml"] if parsed else None

    def resolved_class(self) -> str:
        return rules.resolve_class(
            self.beverage_class, self.class_type, self.declared_abv()
        )

    def rules(self) -> rules.BeverageRules:
        return rules.get_rules(self.resolved_class())

    def as_dict(self) -> dict:
        return asdict(self)


# Accepted CSV column names. Operators' spreadsheets vary, so several
# spellings map to each field rather than forcing one rigid header row.
_COLUMN_ALIASES: Dict[str, str] = {}


def _alias(target: str, *names: str):
    for name in names:
        _COLUMN_ALIASES[name] = target


_alias("image_path", "image", "image_path", "file", "filename", "file_name",
       "label", "label_image", "artwork", "image_file")
_alias("brand_name", "brand", "brand_name", "brandname", "brand name")
_alias("class_type", "class", "type", "class_type", "classtype",
       "class/type", "class_or_type", "fanciful_name", "product_class",
       "class type", "class and type")
_alias("alcohol_content", "abv", "alcohol", "alcohol_content", "alc",
       "alcohol_by_volume", "proof", "alcohol content", "alc_content")
_alias("net_contents", "net_contents", "net", "volume", "size",
       "net contents", "netcontents", "container_size", "fill")
_alias("bottler_name", "bottler", "bottler_name", "producer", "producer_name",
       "bottled_by", "importer", "importer_name", "company", "company_name",
       "bottler name", "name_and_address")
_alias("bottler_address", "address", "bottler_address", "producer_address",
       "bottler address", "city_state", "city_and_state")
_alias("country_of_origin", "country", "country_of_origin", "origin",
       "country of origin")
_alias("beverage_class", "beverage_class", "beverage_type", "commodity",
       "product_type", "beverage", "category")
_alias("is_import", "is_import", "import", "imported", "is_imported")
_alias("contains_sulfites", "contains_sulfites", "sulfites", "sulphites",
       "sulfite", "contains sulfites")
_alias("label_width_mm", "label_width_mm", "label_width", "width_mm",
       "label width mm", "physical_width_mm")
_alias("reference", "reference", "ref", "id", "serial", "serial_number",
       "ttb_id", "record", "row_id")

FIELD_NAMES = [
    "image_path", "brand_name", "class_type", "alcohol_content",
    "net_contents", "bottler_name", "bottler_address", "country_of_origin",
    "beverage_class", "is_import", "contains_sulfites", "label_width_mm",
    "reference",
]

_TRUE_WORDS = {"1", "true", "yes", "y", "t", "x", "import", "imported"}
_FALSE_WORDS = {"0", "false", "no", "n", "f", "", "domestic"}


def _to_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in _TRUE_WORDS:
        return True
    if text in _FALSE_WORDS:
        return False
    return None


def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if number > 0 else None


def normalize_header(name: str) -> Optional[str]:
    key = (name or "").strip().lower().replace("-", "_")
    key = " ".join(key.split())
    return _COLUMN_ALIASES.get(key) or _COLUMN_ALIASES.get(key.replace(" ", "_"))


def from_mapping(row: Dict[str, object]) -> ApplicationData:
    """Build application data from an already-normalised mapping."""
    data = ApplicationData()
    for name in FIELD_NAMES:
        if name not in row:
            continue
        value = row.get(name)
        if value is None:
            continue
        if name == "is_import":
            parsed_bool = _to_bool(str(value))
            data.is_import = bool(parsed_bool)
        elif name == "contains_sulfites":
            data.contains_sulfites = _to_bool(str(value))
        elif name == "label_width_mm":
            data.label_width_mm = _to_float(str(value))
        else:
            setattr(data, name, str(value).strip())

    # An explicit country of origin implies an imported product even when the
    # import column was left blank.
    if data.country_of_origin and not data.is_import:
        domestic = {"usa", "us", "united states", "united states of america",
                    "u s a", "america", "domestic"}
        if data.country_of_origin.strip().lower().replace(".", "") not in domestic:
            data.is_import = True
    return data


def rows_from_csv(text: str) -> Tuple[List[ApplicationData], List[str]]:
    """Parse a batch CSV. Returns (rows, warnings).

    Unknown columns are ignored rather than rejected, so an operator can
    hand us an export with extra bookkeeping columns.
    """
    warnings: List[str] = []
    # utf-8-sig tolerates the byte order mark Excel writes.
    stream = io.StringIO(text.lstrip("﻿"))
    try:
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames or []
    except csv.Error as exc:
        raise ApplicationDataError(f"That CSV file could not be read: {exc}") from exc

    if not fieldnames:
        raise ApplicationDataError(
            "That CSV file has no header row. The first line must name the "
            "columns, for example: image,brand_name,class_type,alcohol_content,"
            "net_contents,bottler_name,bottler_address"
        )

    mapping: Dict[str, str] = {}
    unknown: List[str] = []
    for name in fieldnames:
        target = normalize_header(name)
        if target:
            mapping[name] = target
        elif name and name.strip():
            unknown.append(name.strip())
    if unknown:
        warnings.append(
            "These columns were not recognised and were ignored: "
            + ", ".join(sorted(set(unknown)))
        )
    if "image_path" not in mapping.values():
        raise ApplicationDataError(
            "The CSV needs a column naming each label image file. Name it "
            "'image' (other accepted names: file, filename, label, artwork)."
        )

    rows: List[ApplicationData] = []
    for index, raw_row in enumerate(reader, start=2):
        if index - 1 > config.MAX_BATCH_ROWS:
            warnings.append(
                f"Only the first {config.MAX_BATCH_ROWS} rows were processed."
            )
            break
        if not any((value or "").strip() for value in raw_row.values()):
            continue
        normalized: Dict[str, object] = {}
        for source_name, target in mapping.items():
            normalized[target] = raw_row.get(source_name)
        record = from_mapping(normalized)
        if not record.reference:
            record.reference = f"row {index}"
        rows.append(record)

    if not rows:
        raise ApplicationDataError("That CSV file has a header but no data rows.")
    return rows, warnings


def template_csv() -> str:
    """A ready-to-fill CSV template for batch checks."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "image", "reference", "brand_name", "class_type", "alcohol_content",
        "net_contents", "bottler_name", "bottler_address",
        "country_of_origin", "beverage_class", "is_import",
        "contains_sulfites", "label_width_mm",
    ])
    writer.writerow([
        "bourbon.png", "SKU-1001", "Old Bridge", "Kentucky Straight Bourbon Whisky",
        "45% ABV", "750 mL", "Old Bridge Distillery",
        "Frankfort, Kentucky", "", "distilled_spirits", "no", "", "95",
    ])
    return buffer.getvalue()


# --- Optional TTB.gov lookup ----------------------------------------------
def fetch_from_ttb(reference: str) -> ApplicationData:
    """Look up application data on ttb.gov. Disabled by default.

    Raises ApplicationDataError with a plain explanation whenever the lookup
    is unavailable, which is the normal case on a firewalled network. The
    caller treats that as "use the operator-supplied data" and carries on.
    """
    if not config.ENABLE_TTB_LOOKUP:
        raise ApplicationDataError(
            "The ttb.gov lookup is switched off. Product details are taken "
            "from what you type in, or from your CSV file. To switch the "
            "lookup on, set LABELCHECK_ENABLE_TTB_LOOKUP=1 - but note that "
            "it needs outbound internet access to ttb.gov, which is blocked "
            "on most review networks."
        )

    # Imported lazily so the project has no hard dependency on an HTTP client
    # and cannot make a network call unless this path is deliberately taken.
    try:
        import urllib.error
        import urllib.parse
        import urllib.request
    except ImportError as exc:  # pragma: no cover
        raise ApplicationDataError("No HTTP client is available.") from exc

    url = f"{config.TTB_PUBLIC_REGISTRY_URL}?ttbid={urllib.parse.quote(reference)}"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "label-checker"})
        with urllib.request.urlopen(request, timeout=config.TTB_LOOKUP_TIMEOUT) as response:
            body = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise ApplicationDataError(
            "Could not reach ttb.gov. This is expected on a firewalled "
            "network. Please enter the product details by hand or use a CSV "
            f"file. Technical detail: {type(exc).__name__}"
        ) from exc

    record = _parse_ttb_html(body)
    if record is None:
        raise ApplicationDataError(
            f"No usable record was found on ttb.gov for reference '{reference}'."
        )
    record.reference = reference
    return record


def _parse_ttb_html(body: str) -> Optional[ApplicationData]:
    """Pull product details out of a TTB public registry results page.

    TTB serves this data as a human-facing HTML table with no stable ids, so
    this parser is intentionally conservative: it returns None rather than
    guessing when the markup does not look like what it expects. It is
    isolated here so that a TTB page redesign breaks exactly one function.
    """
    import html
    import re

    text = re.sub(r"<[^>]+>", "\n", body)
    text = html.unescape(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    wanted = {
        "brand name": "brand_name",
        "fanciful name": "class_type",
        "class/type": "class_type",
        "class/type description": "class_type",
        "alcohol content": "alcohol_content",
        "net contents": "net_contents",
        "applicant": "bottler_name",
        "origin": "country_of_origin",
    }
    collected: Dict[str, str] = {}
    for index, line in enumerate(lines[:-1]):
        key = line.rstrip(":").strip().lower()
        target = wanted.get(key)
        if target and target not in collected:
            value = lines[index + 1].strip()
            if value and not value.endswith(":"):
                collected[target] = value

    if "brand_name" not in collected:
        return None
    return from_mapping(collected)
