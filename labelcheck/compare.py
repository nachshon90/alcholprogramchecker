"""Field-by-field comparison of label artwork against application data.

Each check answers three separate questions, because they need different
answers on screen:

  1. Does the regulation require this field at all for this product?
  2. Can we see it on the label?
  3. Does what we see agree with what was declared?

A field that is required and absent is a failure. A field that is present
but disagrees is a failure. A field we simply could not read is reported as
"cannot check" - never as a pass.
"""
from typing import List, Optional

from . import config
from .findings import Finding, FAIL, PASS, UNKNOWN, WARN
from .application import ApplicationData
from .ocr import OcrResult
from .rules import (
    ALCOHOL_CONTENT, BOTTLER_ADDRESS, BOTTLER_NAME, BRAND_NAME, CLASS_TYPE,
    COUNTRY_OF_ORIGIN, FIELD_LABELS, NET_CONTENTS, OPTIONAL,
    REQUIRED, SULFITE_DECLARATION, BeverageRules,
)
from .textnorm import (
    field_match_score, format_alcohol, format_ml, normalize, parse_alcohol,
    parse_net_contents, significant_tokens, token_coverage, tokens,
)

# US state names and postal codes, used to match an address without demanding
# that the whole street line appear on the artwork. Labels routinely print
# only "Frankfort, Kentucky" while the application carries a full address.
_STATES = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct",
    "delaware": "de", "florida": "fl", "georgia": "ga", "hawaii": "hi",
    "idaho": "id", "illinois": "il", "indiana": "in", "iowa": "ia",
    "kansas": "ks", "kentucky": "ky", "louisiana": "la", "maine": "me",
    "maryland": "md", "massachusetts": "ma", "michigan": "mi",
    "minnesota": "mn", "mississippi": "ms", "missouri": "mo",
    "montana": "mt", "nebraska": "ne", "nevada": "nv",
    "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm",
    "new york": "ny", "north carolina": "nc", "north dakota": "nd",
    "ohio": "oh", "oklahoma": "ok", "oregon": "or", "pennsylvania": "pa",
    "rhode island": "ri", "south carolina": "sc", "south dakota": "sd",
    "tennessee": "tn", "texas": "tx", "utah": "ut", "vermont": "vt",
    "virginia": "va", "washington": "wa", "west virginia": "wv",
    "wisconsin": "wi", "wyoming": "wy",
    "district of columbia": "dc", "puerto rico": "pr",
}
_STATE_CODES = set(_STATES.values())
# Words that carry no locating information in an address line.
_ADDRESS_NOISE = {
    "street", "st", "avenue", "ave", "road", "rd", "drive", "dr", "lane",
    "ln", "suite", "ste", "unit", "po", "box", "highway", "hwy", "blvd",
    "boulevard", "usa", "us", "united", "states",
}


def _missing_finding(field_key: str, bev_rules: BeverageRules,
                     expected: Optional[str]) -> Finding:
    """The finding for a field the application declares but we cannot see."""
    level = bev_rules.requirement(field_key)
    label = FIELD_LABELS[field_key]
    if level == REQUIRED:
        return Finding(
            field_key=field_key,
            title=f"{label} is missing from the label",
            status=FAIL,
            detail=(
                f"The {label.lower()} could not be found anywhere on this "
                f"label. {bev_rules.display_name} labels must show it. "
                "If it appears on another panel of the container, check that "
                "panel too."
            ),
            expected=expected,
            found="(not found on the label)",
            cite=bev_rules.authority,
        )
    return Finding(
        field_key=field_key,
        title=f"{label} is not visible on the label",
        status=WARN,
        detail=(
            f"The {label.lower()} was given in the application but could not "
            "be found on the label. It is not always required for this kind "
            "of drink, so please check whether it is needed here."
        ),
        expected=expected,
        found="(not found on the label)",
        cite=bev_rules.authority,
    )


def _undeclared_finding(field_key: str, bev_rules: BeverageRules) -> Optional[Finding]:
    """The finding for a required field the application left blank."""
    level = bev_rules.requirement(field_key)
    label = FIELD_LABELS[field_key]
    if level == REQUIRED:
        return Finding(
            field_key=field_key,
            title=f"No {label.lower()} was given to compare against",
            status=UNKNOWN,
            detail=(
                f"{bev_rules.display_name} labels must show the "
                f"{label.lower()}, but the application data did not include "
                "it, so there is nothing to compare the label against. Please "
                "fill this in and check again."
            ),
            cite=bev_rules.authority,
        )
    return None


def _text_field(field_key: str, expected: str, result: OcrResult,
                bev_rules: BeverageRules) -> List[Finding]:
    """Compare a free-text field such as brand name or class/type."""
    label = FIELD_LABELS[field_key]
    if not expected.strip():
        finding = _undeclared_finding(field_key, bev_rules)
        return [finding] if finding else []

    score = field_match_score(expected, result.text)
    if score >= config.MATCH_THRESHOLD:
        return [Finding(
            field_key=field_key,
            title=f"{label} matches",
            status=PASS,
            detail=f"The label shows the same {label.lower()} as the application.",
            expected=expected,
            found=_excerpt(expected, result.text),
            cite=bev_rules.authority,
        )]
    if score < config.PRESENCE_THRESHOLD:
        return [_missing_finding(field_key, bev_rules, expected)]
    return [Finding(
        field_key=field_key,
        title=f"{label} does not match",
        status=FAIL,
        detail=(
            f"The {label.lower()} on the label does not match the "
            f"application. The application says \"{expected}\". Please "
            "compare the two carefully - this may be a spelling difference "
            "or a different product."
        ),
        expected=expected,
        found=_excerpt(expected, result.text),
        cite=bev_rules.authority,
    )]


def _excerpt(expected: str, haystack: str, span: int = 60) -> str:
    """The most similar run of OCR text, so the operator can see what we read."""
    expected_tokens = significant_tokens(expected)
    if not expected_tokens:
        return (haystack[:span] + "...") if len(haystack) > span else haystack
    lines = [line for line in haystack.splitlines() if line.strip()]
    best_line, best_score = "", 0.0
    for line in lines:
        score = field_match_score(expected, line)
        if score > best_score:
            best_line, best_score = line, score
    if best_line:
        return best_line.strip()[:120]
    return (haystack[:span] + "...") if len(haystack) > span else haystack


def check_brand_name(app: ApplicationData, result: OcrResult,
                     bev_rules: BeverageRules) -> List[Finding]:
    return _text_field(BRAND_NAME, app.brand_name, result, bev_rules)


def check_class_type(app: ApplicationData, result: OcrResult,
                     bev_rules: BeverageRules) -> List[Finding]:
    return _text_field(CLASS_TYPE, app.class_type, result, bev_rules)


def check_bottler_name(app: ApplicationData, result: OcrResult,
                       bev_rules: BeverageRules) -> List[Finding]:
    return _text_field(BOTTLER_NAME, app.bottler_name, result, bev_rules)


def check_alcohol_content(app: ApplicationData, result: OcrResult,
                          bev_rules: BeverageRules) -> List[Finding]:
    """Compare declared strength with the label, within the CFR tolerance."""
    label_key = FIELD_LABELS[ALCOHOL_CONTENT]
    declared = app.declared_abv()
    if declared is None:
        if app.alcohol_content.strip():
            return [Finding(
                field_key=ALCOHOL_CONTENT,
                title="Alcohol content in the application could not be read",
                status=UNKNOWN,
                detail=(
                    f"The application gives the alcohol content as "
                    f"\"{app.alcohol_content}\", which the tool could not "
                    "understand. Please write it like \"40% ABV\" or \"80 proof\"."
                ),
                expected=app.alcohol_content,
                cite=bev_rules.abv_tolerance_cite,
            )]
        finding = _undeclared_finding(ALCOHOL_CONTENT, bev_rules)
        return [finding] if finding else []

    candidates = parse_alcohol(result.text)
    if not candidates:
        return [_missing_finding(
            ALCOHOL_CONTENT, bev_rules, f"{declared:g}% ABV")]

    tolerance = bev_rules.abv_tolerance_for(declared)
    best = min(candidates, key=lambda entry: abs(entry["abv"] - declared))
    difference = abs(best["abv"] - declared)

    # A wine may not use the tolerance to cross the 14% tax-class boundary.
    crosses_tax_class = (
        bev_rules.key in {"wine", "cider", "sake", "mead"}
        and (declared > 14.0) != (best["abv"] > 14.0)
    )

    if difference <= tolerance + 1e-9 and not crosses_tax_class:
        note = ""
        if best["kind"] == "proof":
            note = " The label states proof, which matches the declared ABV."
        return [Finding(
            field_key=ALCOHOL_CONTENT,
            title="Alcohol content matches",
            status=PASS,
            detail=(
                f"The label shows {format_alcohol(best)} and the application "
                f"declares {declared:g}% ABV. That is within the allowed "
                f"difference of {tolerance:g} percentage points.{note}"
            ),
            expected=f"{declared:g}% ABV",
            found=format_alcohol(best),
            cite=bev_rules.abv_tolerance_cite,
        )]

    if crosses_tax_class:
        return [Finding(
            field_key=ALCOHOL_CONTENT,
            title="Alcohol content crosses the 14% tax class line",
            status=FAIL,
            detail=(
                f"The label shows {format_alcohol(best)} but the application "
                f"declares {declared:g}% ABV. One is above 14% and the other "
                "is at or below it. The allowed difference may never be used "
                "to move a wine across the 14% line, because the two sides "
                "are taxed differently."
            ),
            expected=f"{declared:g}% ABV",
            found=format_alcohol(best),
            cite="27 CFR 4.36(b)",
        )]

    return [Finding(
        field_key=ALCOHOL_CONTENT,
        title="Alcohol content does not match",
        status=FAIL,
        detail=(
            f"The label shows {format_alcohol(best)} but the application "
            f"declares {declared:g}% ABV. That is a difference of "
            f"{difference:.2f} percentage points, and only {tolerance:g} is "
            f"allowed for {bev_rules.display_name.lower()}."
        ),
        expected=f"{declared:g}% ABV",
        found=format_alcohol(best),
        cite=bev_rules.abv_tolerance_cite,
    )]


def check_net_contents(app: ApplicationData, result: OcrResult,
                       bev_rules: BeverageRules) -> List[Finding]:
    """Compare the stated fill, then test it against the standards of fill."""
    declared = app.declared_ml()
    if declared is None:
        if app.net_contents.strip():
            return [Finding(
                field_key=NET_CONTENTS,
                title="Net contents in the application could not be read",
                status=UNKNOWN,
                detail=(
                    f"The application gives the net contents as "
                    f"\"{app.net_contents}\", which the tool could not "
                    "understand. Please write it like \"750 mL\" or \"12 fl oz\"."
                ),
                expected=app.net_contents,
                cite=bev_rules.standards_cite,
            )]
        finding = _undeclared_finding(NET_CONTENTS, bev_rules)
        return [finding] if finding else []

    findings: List[Finding] = []
    candidates = parse_net_contents(result.text)
    if not candidates:
        findings.append(_missing_finding(
            NET_CONTENTS, bev_rules, format_ml(declared)))
    else:
        best = min(candidates, key=lambda entry: abs(entry["ml"] - declared))
        difference = abs(best["ml"] - declared)
        # Allow for rounding between metric and US customary statements: a
        # label may legitimately print "25.4 FL OZ" for a 750 mL bottle.
        allowed = max(1.0, declared * 0.015)
        if difference <= allowed:
            findings.append(Finding(
                field_key=NET_CONTENTS,
                title="Net contents match",
                status=PASS,
                detail=(
                    f"The label shows {best['source']} and the application "
                    f"declares {format_ml(declared)}. These agree."
                ),
                expected=format_ml(declared),
                found=best["source"],
                cite=bev_rules.authority,
            ))
        else:
            findings.append(Finding(
                field_key=NET_CONTENTS,
                title="Net contents do not match",
                status=FAIL,
                detail=(
                    f"The label shows {best['source']} (about "
                    f"{best['ml']:g} mL) but the application declares "
                    f"{format_ml(declared)}. These are different sizes."
                ),
                expected=format_ml(declared),
                found=best["source"],
                cite=bev_rules.authority,
            ))

    # Standards of fill. Reported as advisory, never as a hard failure: the
    # permitted sizes have been amended repeatedly and carry exemptions.
    if bev_rules.standards_of_fill_ml:
        nearest = min(bev_rules.standards_of_fill_ml,
                      key=lambda size: abs(size - declared))
        if abs(nearest - declared) > 1.0:
            findings.append(Finding(
                field_key=NET_CONTENTS,
                title="Container size is not a standard size",
                status=WARN,
                advisory=True,
                detail=(
                    f"{format_ml(declared)} is not one of the standard "
                    f"container sizes for {bev_rules.display_name.lower()}. "
                    f"The nearest standard size is {format_ml(nearest)}. "
                    "Standard sizes have changed in recent years and some "
                    "products are exempt, so please confirm this one."
                ),
                expected=f"a standard size, nearest is {format_ml(nearest)}",
                found=format_ml(declared),
                cite=bev_rules.standards_cite,
            ))
    return findings


def check_bottler_address(app: ApplicationData, result: OcrResult,
                          bev_rules: BeverageRules) -> List[Finding]:
    """Match the place of business, tolerating a shortened label address."""
    expected = app.bottler_address.strip()
    if not expected:
        finding = _undeclared_finding(BOTTLER_ADDRESS, bev_rules)
        return [finding] if finding else []

    full_score = field_match_score(expected, result.text)

    # Labels usually print only city and state, so score those separately.
    ocr_tokens = set(tokens(result.text))
    address_tokens = [
        t for t in tokens(expected)
        if t not in _ADDRESS_NOISE and not t.isdigit()
    ]
    place_tokens = [t for t in address_tokens if t in _STATES or t in _STATE_CODES]
    # Treat any non-noise word as a possible city name.
    city_tokens = [t for t in address_tokens if t not in _STATES
                   and t not in _STATE_CODES and len(t) > 2]

    def present(token: str) -> bool:
        if token in ocr_tokens:
            return True
        # Accept the postal abbreviation for a spelled-out state, and vice versa.
        if token in _STATES and _STATES[token] in ocr_tokens:
            return True
        if token in _STATE_CODES:
            for name, code in _STATES.items():
                if code == token and name in " ".join(ocr_tokens):
                    return True
        return False

    city_found = any(present(t) for t in city_tokens) if city_tokens else False
    state_found = any(present(t) for t in place_tokens) if place_tokens else False

    if full_score >= config.MATCH_THRESHOLD or (city_found and state_found):
        return [Finding(
            field_key=BOTTLER_ADDRESS,
            title="Bottler / producer address matches",
            status=PASS,
            detail=(
                "The place of business on the label agrees with the "
                "application. Labels often show only the city and state, "
                "which is allowed."
            ),
            expected=expected,
            found=_excerpt(expected, result.text),
            cite=bev_rules.authority,
        )]

    if city_found or state_found or full_score >= config.PRESENCE_THRESHOLD:
        return [Finding(
            field_key=BOTTLER_ADDRESS,
            title="Bottler / producer address only partly matches",
            status=FAIL,
            detail=(
                f"Only part of the address could be matched. The application "
                f"says \"{expected}\". Please compare the address on the "
                "label with the application by eye."
            ),
            expected=expected,
            found=_excerpt(expected, result.text),
            cite=bev_rules.authority,
        )]
    return [_missing_finding(BOTTLER_ADDRESS, bev_rules, expected)]


def check_country_of_origin(app: ApplicationData, result: OcrResult,
                            bev_rules: BeverageRules) -> List[Finding]:
    """Required for imported products only."""
    expected = app.country_of_origin.strip()
    if not app.is_import and not expected:
        return [Finding(
            field_key=COUNTRY_OF_ORIGIN,
            title="Country of origin not required",
            status=PASS,
            detail=(
                "This product was not marked as imported, so no country of "
                "origin statement is needed."
            ),
            cite="19 CFR 134",
        )]
    if not expected:
        return [Finding(
            field_key=COUNTRY_OF_ORIGIN,
            title="No country of origin was given to compare against",
            status=UNKNOWN,
            detail=(
                "This product is marked as imported, so the label must name "
                "the country it came from, but the application did not say "
                "which country. Please fill this in and check again."
            ),
            cite="19 CFR 134",
        )]

    # Presence is judged on whether the country's own words appear, because
    # a partial character-similarity score against unrelated label text
    # would otherwise be misreported as a mismatch rather than an absence.
    coverage = token_coverage(expected, result.text)
    score = max(field_match_score(expected, result.text), coverage)
    if coverage >= 0.5 or score >= config.MATCH_THRESHOLD:
        return [Finding(
            field_key=COUNTRY_OF_ORIGIN,
            title="Country of origin matches",
            status=PASS,
            detail=f"The label names {expected}, matching the application.",
            expected=expected,
            found=_excerpt(expected, result.text),
            cite="19 CFR 134",
        )]
    if coverage < 0.5:
        return [Finding(
            field_key=COUNTRY_OF_ORIGIN,
            title="Country of origin is missing from the label",
            status=FAIL,
            detail=(
                f"This is an imported product, so the label must say that it "
                f"is a product of {expected}. That statement could not be "
                "found."
            ),
            expected=expected,
            found="(not found on the label)",
            cite="19 CFR 134",
        )]
    return [Finding(
        field_key=COUNTRY_OF_ORIGIN,
        title="Country of origin does not match",
        status=FAIL,
        detail=(
            f"The application says the product comes from {expected}, but "
            "the label appears to say something else."
        ),
        expected=expected,
        found=_excerpt(expected, result.text),
        cite="19 CFR 134",
    )]


def check_sulfites(app: ApplicationData, result: OcrResult,
                   bev_rules: BeverageRules) -> List[Finding]:
    """Wine must declare sulfites at 10 parts per million or more."""
    level = bev_rules.requirement(SULFITE_DECLARATION)
    if level == OPTIONAL and app.contains_sulfites is not True:
        return []
    if app.contains_sulfites is False:
        return [Finding(
            field_key=SULFITE_DECLARATION,
            title="Sulfite declaration not required",
            status=PASS,
            detail=(
                "The application states this product is below 10 parts per "
                "million of sulfur dioxide, so no sulfite statement is needed."
            ),
            cite="27 CFR 4.32(e)",
        )]

    normalized = normalize(result.text)
    present = "contains sulfites" in normalized or "contains sulphites" in normalized
    if present:
        return [Finding(
            field_key=SULFITE_DECLARATION,
            title="Sulfite declaration is present",
            status=PASS,
            detail="The label carries the words CONTAINS SULFITES.",
            expected="CONTAINS SULFITES",
            found="CONTAINS SULFITES",
            cite="27 CFR 4.32(e)",
        )]

    if level == REQUIRED and app.contains_sulfites is not False:
        return [Finding(
            field_key=SULFITE_DECLARATION,
            title="Sulfite declaration is missing",
            status=FAIL if app.contains_sulfites else WARN,
            detail=(
                "The words CONTAINS SULFITES could not be found on this "
                "label. Wine must carry this statement whenever it holds 10 "
                "parts per million or more of sulfur dioxide, which covers "
                "almost all wine sold commercially. If this wine is below "
                "that level, tick the sulfites box as 'no'."
            ),
            expected="CONTAINS SULFITES",
            found="(not found on the label)",
            cite="27 CFR 4.32(e)",
        )]
    return []
