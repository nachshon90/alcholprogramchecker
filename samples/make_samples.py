"""Generate test label artwork with known, deliberate defects.

These are synthetic labels, not real products. Each one exercises a specific
rule so the checker's behaviour can be demonstrated and regression-tested
without shipping anyone's copyrighted artwork.

Run:  python3 samples/make_samples.py
"""
import csv
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
DPI = 300
MM_PER_INCH = 25.4
PX_PER_MM = DPI / MM_PER_INCH          # 11.811 px per mm at 300 DPI
CAP_RATIO = 0.73                        # DejaVu Sans cap height / font size

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
REGULAR = FONT_DIR / "DejaVuSans.ttf"
BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"
SERIF_BOLD = FONT_DIR / "DejaVuSerif-Bold.ttf"

WARNING_PREFIX = "GOVERNMENT WARNING:"
WARNING_BODY = (
    "(1) According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a "
    "car or operate machinery, and may cause health problems."
)


def mm(value: float) -> int:
    return round(value * PX_PER_MM)


def font_for_cap_mm(cap_mm: float, path: Path = REGULAR) -> ImageFont.FreeTypeFont:
    """A font sized so capital letters measure `cap_mm` millimetres tall."""
    size = max(6, round((cap_mm * PX_PER_MM) / CAP_RATIO))
    return ImageFont.truetype(str(path), size)


def wrap(draw, text, font, max_width):
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def tracked_length(draw, text, font, tracking):
    """Width of `text` when each character is followed by `tracking` px."""
    if not text:
        return 0.0
    return draw.textlength(text, font=font) + tracking * (len(text) - 1)


def draw_tracked(draw, xy, text, font, fill, tracking):
    """Draw text with extra space between characters.

    27 CFR 16.22 imposes two limits at once: a minimum cap height and a
    maximum of 12 characters per inch. A normal-width face at 2 mm fails the
    second, so genuinely compliant artwork needs the type letter-spaced.
    """
    x, y = xy
    if not tracking:
        draw.text((x, y), text, font=font, fill=fill)
        return
    for character in text:
        draw.text((x, y), character, font=font, fill=fill)
        x += draw.textlength(character, font=font) + tracking


def warning_lines(draw, text_body, prefix, regular, heavy, width, tracking=0):
    """Lay the warning out, returning (lines, prefix_width).

    The first line carries the bold prefix, so it has less room than the
    rest. Returned as data so callers can measure the block before drawing.
    """
    prefix_width = tracked_length(draw, prefix + " ", heavy, tracking)
    first, remaining = [], text_body.split()
    while remaining:
        trial = " ".join(first + [remaining[0]])
        if tracked_length(draw, trial, regular, tracking) <= width - prefix_width:
            first.append(remaining.pop(0))
        else:
            break
    lines = [" ".join(first)]
    lines.extend(wrap_tracked(draw, " ".join(remaining), regular, width, tracking))
    return lines, prefix_width


def wrap_tracked(draw, text, font, max_width, tracking):
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if tracked_length(draw, trial, font, tracking) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def measure_warning(draw, cap_mm, width, caps=True, bold_prefix=True, tracking=0):
    """Height in pixels the warning block will occupy."""
    regular = font_for_cap_mm(cap_mm, REGULAR)
    heavy = font_for_cap_mm(cap_mm, BOLD if bold_prefix else REGULAR)
    body = WARNING_BODY.upper() if caps else WARNING_BODY
    lines, _ = warning_lines(draw, body, WARNING_PREFIX, regular, heavy, width,
                             tracking)
    return len(lines) * round(regular.size * 1.25)


def draw_warning(draw, x, y, width, cap_mm, caps=True, bold_prefix=True,
                 tracking=0):
    """Draw the Government Warning, returning the y position after it."""
    regular = font_for_cap_mm(cap_mm, REGULAR)
    heavy = font_for_cap_mm(cap_mm, BOLD if bold_prefix else REGULAR)
    body = WARNING_BODY.upper() if caps else WARNING_BODY
    lines, prefix_width = warning_lines(
        draw, body, WARNING_PREFIX, regular, heavy, width, tracking)
    line_height = round(regular.size * 1.25)

    draw_tracked(draw, (x, y), WARNING_PREFIX, heavy, (0, 0, 0), tracking)
    draw_tracked(draw, (x + prefix_width, y), lines[0], regular, (0, 0, 0),
                 tracking)
    y += line_height
    for line in lines[1:]:
        draw_tracked(draw, (x, y), line, regular, (0, 0, 0), tracking)
        y += line_height
    return y


def make_label(path: Path, *, width_mm, height_mm, brand, brand_cap_mm,
               class_type, alcohol, net_contents, bottler, address,
               extra_lines=(), warning_cap_mm=2.2, include_warning=True,
               warning_caps=True, bold_prefix=True, warning_tracking_mm=0.7,
               background=(255, 255, 255)):
    width = mm(width_mm)
    margin = mm(5)
    inner = width - 2 * margin

    # Measure first, then size the canvas, so the warning can never be
    # cropped off the bottom of the artwork.
    scratch = ImageDraw.Draw(Image.new("RGB", (width, 10), background))
    tracking = warning_tracking_mm * PX_PER_MM
    warning_height = (
        measure_warning(scratch, warning_cap_mm, inner, warning_caps,
                        bold_prefix, tracking)
        if include_warning else 0
    )

    def render(canvas_height, draw_content=True):
        image = Image.new("RGB", (width, canvas_height), background)
        draw = ImageDraw.Draw(image)
        y = mm(7)
        brand_font = font_for_cap_mm(brand_cap_mm, SERIF_BOLD)
        for line in wrap(draw, brand.upper(), brand_font, inner):
            line_width = draw.textlength(line, font=brand_font)
            if draw_content:
                draw.text(((width - line_width) / 2, y), line,
                          font=brand_font, fill=(20, 20, 20))
            y += round(brand_font.size * 1.15)

        y += mm(2)
        class_font = font_for_cap_mm(3.0, REGULAR)
        for line in wrap(draw, class_type.upper(), class_font, inner):
            line_width = draw.textlength(line, font=class_font)
            if draw_content:
                draw.text(((width - line_width) / 2, y), line,
                          font=class_font, fill=(40, 40, 40))
            y += round(class_font.size * 1.2)

        y += mm(3)
        detail_font = font_for_cap_mm(2.4, REGULAR)
        for line in [alcohol, net_contents] + list(extra_lines):
            if not line:
                continue
            line_width = draw.textlength(line, font=detail_font)
            if draw_content:
                draw.text(((width - line_width) / 2, y), line,
                          font=detail_font, fill=(40, 40, 40))
            y += round(detail_font.size * 1.35)

        y += mm(2)
        small_font = font_for_cap_mm(2.0, REGULAR)
        for line in [bottler, address]:
            if not line:
                continue
            line_width = draw.textlength(line, font=small_font)
            if draw_content:
                draw.text(((width - line_width) / 2, y), line,
                          font=small_font, fill=(40, 40, 40))
            y += round(small_font.size * 1.3)
        return image, draw, y

    # Pass one measures where the body text ends; pass two draws for real.
    _, _, content_bottom = render(mm(height_mm), draw_content=False)
    needed = content_bottom + mm(4) + warning_height + mm(4)
    height = max(mm(height_mm), needed)
    image, draw, content_bottom = render(height)

    if include_warning:
        warning_y = max(content_bottom + mm(4),
                        height - mm(4) - warning_height)
        draw_warning(draw, margin, warning_y, inner, warning_cap_mm,
                     caps=warning_caps, bold_prefix=bold_prefix,
                     tracking=tracking)

    image.save(path, dpi=(DPI, DPI))
    return path


SPECS = [
    dict(
        name="01_bourbon_compliant.png", reference="SKU-1001",
        width_mm=95, height_mm=110, brand="Old Bridge", brand_cap_mm=9,
        class_type="Kentucky Straight Bourbon Whiskey", alcohol="45% ALC/VOL (90 PROOF)",
        net_contents="750 mL", bottler="Old Bridge Distillery",
        address="Frankfort, Kentucky", warning_cap_mm=2.2,
        app=dict(brand_name="Old Bridge", class_type="Kentucky Straight Bourbon Whiskey",
                 alcohol_content="45% ABV", net_contents="750 mL",
                 bottler_name="Old Bridge Distillery",
                 bottler_address="Frankfort, Kentucky",
                 beverage_class="distilled_spirits", label_width_mm=95),
    ),
    dict(
        name="02_wine_abv_mismatch.png", reference="SKU-1002",
        width_mm=100, height_mm=110, brand="Mountain Creek", brand_cap_mm=8,
        class_type="Cabernet Sauvignon", alcohol="ALC. 15.8% BY VOL",
        net_contents="750 mL", bottler="Mountain Creek Vineyards",
        address="Napa, California", extra_lines=("CONTAINS SULFITES",),
        warning_cap_mm=2.1,
        app=dict(brand_name="Mountain Creek", class_type="Cabernet Sauvignon",
                 alcohol_content="13.5% ABV", net_contents="750 mL",
                 bottler_name="Mountain Creek Vineyards",
                 bottler_address="Napa, California", beverage_class="wine",
                 contains_sulfites="yes", label_width_mm=100),
    ),
    dict(
        name="03_beer_tiny_warning.png", reference="SKU-1003",
        width_mm=90, height_mm=100, brand="Harbor Light", brand_cap_mm=8,
        class_type="India Pale Ale", alcohol="6.2% ALC/VOL",
        net_contents="12 FL OZ", bottler="Harbor Light Brewing Co.",
        address="Portland, Maine", warning_cap_mm=1.1,
        warning_tracking_mm=0.0,
        app=dict(brand_name="Harbor Light", class_type="India Pale Ale",
                 alcohol_content="6.2% ABV", net_contents="12 fl oz",
                 bottler_name="Harbor Light Brewing Co.",
                 bottler_address="Portland, Maine",
                 beverage_class="malt_beverage", label_width_mm=90),
    ),
    dict(
        name="04_wine_no_warning.png", reference="SKU-1004",
        width_mm=100, height_mm=95, brand="Silver Hollow", brand_cap_mm=8,
        class_type="Chardonnay", alcohol="ALC. 13.0% BY VOL",
        net_contents="750 mL", bottler="Silver Hollow Cellars",
        address="Sonoma, California", include_warning=False,
        app=dict(brand_name="Silver Hollow", class_type="Chardonnay",
                 alcohol_content="13.0% ABV", net_contents="750 mL",
                 bottler_name="Silver Hollow Cellars",
                 bottler_address="Sonoma, California", beverage_class="wine",
                 contains_sulfites="yes", label_width_mm=100),
    ),
    dict(
        name="05_imported_gin_no_origin.png", reference="SKU-1005",
        width_mm=95, height_mm=110, brand="Thistle Row", brand_cap_mm=8,
        class_type="London Dry Gin", alcohol="47% ALC/VOL",
        net_contents="700 mL", bottler="Thistle Row Distillers",
        address="Edinburgh", warning_cap_mm=2.3,
        app=dict(brand_name="Thistle Row", class_type="London Dry Gin",
                 alcohol_content="47% ABV", net_contents="700 mL",
                 bottler_name="Thistle Row Distillers",
                 bottler_address="Edinburgh", country_of_origin="Scotland",
                 is_import="yes", beverage_class="distilled_spirits",
                 label_width_mm=95),
    ),
    dict(
        name="06_cider_lowercase_warning.png", reference="SKU-1006",
        width_mm=90, height_mm=100, brand="Windfall Orchard", brand_cap_mm=7,
        class_type="Hard Cider", alcohol="6.9% ALC/VOL",
        net_contents="500 mL", bottler="Windfall Orchard Cider Works",
        address="Burlington, Vermont", warning_cap_mm=2.1, warning_caps=False,
        # Lower-case glyphs are narrower, so this needs wider spacing to stay
        # inside the 12-characters-per-inch limit. Keeping it compliant on
        # spacing isolates the capitals finding in the demo.
        warning_tracking_mm=1.15,
        app=dict(brand_name="Windfall Orchard", class_type="Hard Cider",
                 alcohol_content="6.9% ABV", net_contents="500 mL",
                 bottler_name="Windfall Orchard Cider Works",
                 bottler_address="Burlington, Vermont", beverage_class="cider",
                 label_width_mm=90),
    ),
]


# Front-and-back pairs. Real containers routinely split the mandatory
# information across two labels: branding on the front, and the bottler's
# name, address and the Government Warning on the back. Neither panel is
# compliant alone; together they are.
PAIRS = [
    dict(
        reference="SKU-1007",
        front=dict(
            name="07_whiskey_front.png", width_mm=95, height_mm=105,
            brand="Ironwood Bend", brand_cap_mm=9,
            class_type="Tennessee Whiskey", alcohol="43% ALC/VOL",
            net_contents="750 mL", bottler="", address="",
            include_warning=False,
        ),
        back=dict(
            name="07_whiskey_back.png", width_mm=95, height_mm=95,
            brand="", brand_cap_mm=6, class_type="", alcohol="",
            net_contents="", bottler="Ironwood Bend Distilling Co.",
            address="Nashville, Tennessee", warning_cap_mm=2.2,
        ),
        app=dict(
            brand_name="Ironwood Bend", class_type="Tennessee Whiskey",
            alcohol_content="43% ABV", net_contents="750 mL",
            bottler_name="Ironwood Bend Distilling Co.",
            bottler_address="Nashville, Tennessee",
            beverage_class="distilled_spirits",
            label_width_mm=95, label_width_mm_2=95,
        ),
    ),
]


def main():
    out_dir = HERE / "labels"
    out_dir.mkdir(exist_ok=True)
    rows = []
    for spec in SPECS:
        spec = dict(spec)
        name = spec.pop("name")
        reference = spec.pop("reference")
        app = spec.pop("app")
        path = make_label(out_dir / name, **spec)
        print(f"wrote {path.relative_to(HERE.parent)}")
        rows.append({"image": f"labels/{name}", "reference": reference, **app})

    for pair in PAIRS:
        entry = {"reference": pair["reference"], **pair["app"]}
        for side in ("front", "back"):
            spec = dict(pair[side])
            name = spec.pop("name")
            make_label(out_dir / name, **spec)
            print(f"wrote {(out_dir / name).relative_to(HERE.parent)}")
            entry["image" if side == "front" else "image_2"] = f"labels/{name}"
        rows.append(entry)

    columns = ["image", "image_2", "reference", "brand_name", "class_type",
               "alcohol_content", "net_contents", "bottler_name",
               "bottler_address", "country_of_origin", "beverage_class",
               "is_import", "contains_sulfites", "label_width_mm",
               "label_width_mm_2"]
    csv_path = HERE / "sample_batch.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in columns})
    print(f"wrote {csv_path.relative_to(HERE.parent)}")


if __name__ == "__main__":
    sys.exit(main())
