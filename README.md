# Alcohol Label Compliance Checker

Checks a picture of an alcohol beverage label against the product details you
enter, and against the federal labelling rules in 27 CFR.

You type in your company and product information, add one or two pictures of
the label, and the tool reads them with on-device OCR and reports **match**,
**mismatch**, or **missing** for every required field. It pays particular
attention to the Government Health Warning, which has requirements about
wording, capitalisation and physical letter size.

Containers routinely split the mandatory information between a front and a
back label, so you can supply **up to two pictures** and they are checked
together as one container. One picture on its own is checked on its own.

It runs entirely on your own computer. There are no cloud services, no
accounts, and no outbound network calls.

---

## Quick start

**1. Install the OCR engine** (this is a normal program, not a Python package):

| System | Command |
| --- | --- |
| Ubuntu / Debian | `sudo apt-get install tesseract-ocr` |
| Red Hat / Fedora | `sudo dnf install tesseract` |
| macOS | `brew install tesseract` |
| Windows | <https://github.com/UB-Mannheim/tesseract/wiki> |

Check it worked: `tesseract --version`

**2. Install the Python packages and start the tool:**

```bash
pip install -r requirements.txt
python3 app.py
```

Or just `./run.sh`, which checks both dependencies for you first.

**3. Open <http://127.0.0.1:5000> in a web browser.**

---

## How to use it

### Checking one label

Fill in the form and upload the label picture. You get a result in about a
second.

**One or two pictures.** The first picture is required; the second is
optional. Use it when the product has a back label, which is where the
Government Warning and the bottler's address usually sit. Text is pooled
across both, so a field counts as present if it appears on either one. If a
product has everything on a single label, supply just the one picture.

The form asks for each **label's real width in millimetres**. This is optional
but strongly recommended: without it the tool cannot work out how big the
printed letters actually are, so it cannot check the health-warning type-size
rule. Measure the printed label with a ruler. Each picture has its own width
box, because front and back labels are often different sizes and one figure
would be wrong for the other. (If the image file records its own DPI, as
scanned artwork usually does, that is used automatically.)

### Checking many labels at once

Go to **Check many labels**:

1. Download the blank spreadsheet and fill in one row per product.
2. Put all the label pictures in one folder and ZIP it.
3. Upload both. You get an on-screen table and a results CSV.

The CSV needs a heading row and a column naming each image file. Column names
are flexible — `image`, `file`, `filename`, `label` and `artwork` all work,
as do `brand`/`brand_name`, `abv`/`alcohol_content`, and so on. Unrecognised
columns are ignored with a note rather than rejected, so you can feed in an
export that carries extra bookkeeping columns.

For a product with a back label, add its file name in an **`image_2`** column
(`back_image` and `back` also work) and, if you have it, the back label's
width in `label_width_mm_2`. Leave `image_2` empty for single-label products;
the row is then checked against its one picture.

A ready-made example is in `samples/`:

```bash
python3 samples/make_samples.py    # regenerate the test artwork
```

---

## What it checks

| Field | Required for | Authority |
| --- | --- | --- |
| Brand name | all | 27 CFR 4.32, 5.63, 7.63 |
| Class / type designation | all | 27 CFR 4.32, 5.63, 7.63 |
| Alcohol content | wine, spirits (conditional for malt beverages) | 27 CFR 4.36, 5.65, 7.65 |
| Net contents | all | 27 CFR 4.32, 5.63, 7.63 |
| Bottler / producer / importer name | all | 27 CFR 4.35, 5.66, 7.66 |
| Bottler / producer address | all | 27 CFR 4.35, 5.66, 7.66 |
| Country of origin | imports | 19 CFR 134 |
| Sulfite declaration | wine at 10ppm or more | 27 CFR 4.32(e) |
| Government Health Warning | everything at 0.5% ABV or more | 27 CFR Part 16 |

### Alcohol content tolerances

The tool does not demand an exact string match, because the regulations allow
a tolerance between the declared and actual strength:

| Beverage | Tolerance | Authority |
| --- | --- | --- |
| Distilled spirits | 0.15 percentage points | 27 CFR 5.65(a) |
| Malt beverages | 0.3 percentage points | 27 CFR 7.71 |
| Wine at or below 14% ABV | 1.5 percentage points | 27 CFR 4.36(b) |
| Wine above 14% ABV | 1.0 percentage point | 27 CFR 4.36(b) |

Proof and ABV are treated as equivalent, so a label reading `90 PROOF`
correctly matches a declaration of `45% ABV`.

One special case is handled explicitly: **the wine tolerance may never be used
to cross the 14% line**, because the two sides are taxed differently. A label
at 14.4% against a declaration of 13.9% is inside the 1.5-point tolerance but
is still reported as a failure.

### Beverage types

Different products are governed by different Parts of 27 CFR, so the tool
picks a rule set per product. It can be chosen on the form, or inferred from
the class/type designation.

- **Malt beverage** — beer, ale, lager, stout, porter, IPA, flavoured malt
  beverages (Part 7)
- **Wine** — still, sparkling, fortified (Part 4)
- **Distilled spirits** — whisky, vodka, gin, rum, brandy, tequila, liqueurs
  (Part 5)
- **Hard cider** — Part 4 at or above 7% ABV
- **Sake** and **mead** — labelled as wine under Part 4
- **Other beverages under 7% ABV** — these fall outside the Federal Alcohol
  Administration Act, so FDA labelling rules apply instead. The tool still
  requires the Government Warning, because 27 CFR Part 16 reaches every
  beverage at or above 0.5% ABV regardless of which agency governs the rest
  of the label.

Cider is the interesting case: the same product is checked under Part 4 at
8% ABV and under FDA rules at 5% ABV. The tool switches automatically.

### The Government Health Warning

This is the strictest check, and it is deliberately more than a text search.
When two pictures are supplied, the tool finds whichever panel actually
carries the warning and measures **that** panel — letter height and character
density are physical measurements, so they cannot be taken from pooled text.
The result page says which picture it used.

The required statement is:

> **GOVERNMENT WARNING:** (1) According to the Surgeon General, women should
> not drink alcoholic beverages during pregnancy because of the risk of birth
> defects. (2) Consumption of alcoholic beverages impairs your ability to
> drive a car or operate machinery, and may cause health problems.

The tool checks:

1. **Presence and exact wording**, segment by segment, so it can report
   *which* part is missing rather than just "the warning is wrong".
2. **`GOVERNMENT WARNING` in capital letters** — required by 27 CFR 16.21.
   Failing this is a hard failure.
3. **Minimum letter height** — 27 CFR 16.22(a): 1 mm on containers of 237 mL
   or less, 2 mm up to 3 L, 3 mm above that. Measured from the capital
   letters of `GOVERNMENT WARNING`, which must be capitals and so give a
   clean cap-height reading.
4. **No more than 12 characters per inch** — 27 CFR 16.22(b).
5. **Bold type** on `GOVERNMENT WARNING` — reported as an advisory hint from
   ink density, because bold is not reliably detectable from an image.

---

## Design decisions

These are the judgement calls worth knowing about before relying on the tool.

### No cloud APIs, and outbound access really is blocked

OCR runs locally through Tesseract. Nothing in this project sends an image or
a company detail anywhere. The only module that can open a socket at all is
the optional TTB lookup described below, and it is off by default.

This was verified rather than assumed: fetching `https://www.ttb.gov/` from
the build environment returns `EGRESS_BLOCKED` from the network proxy. Any
design that depended on a live ttb.gov call would not run here.

### Where application data comes from

The tool compares artwork against **the details you enter**, on the form or in
a batch CSV. That is the data of record, and it is the path that always works.

`labelcheck/application.py` also contains `fetch_from_ttb()`, an optional
lookup against TTB's public label data. It is **disabled by default** because:

1. TTB publishes that data as an HTML search form for people, not as a
   machine-readable API. Any client is screen-scraping, and breaks whenever
   the page markup changes.
2. Outbound access to ttb.gov is firewalled on normal review networks, as
   above.

It fails with a plain explanation rather than hanging, and never blocks a
check. Enable it with `LABELCHECK_ENABLE_TTB_LOOKUP=1` if you have a network
path to ttb.gov. The HTML parsing is isolated in one small function so that a
TTB page redesign breaks exactly one place.

### Letter size needs physical scale, so unknown is reported as unknown

Type size is a physical measurement in millimetres, but an image is just
pixels. Converting between them needs to know how big the label really is.
The tool takes that from your measured label width, or failing that from the
image's DPI metadata.

When neither is available it reports **"cannot check"** and tells you what to
supply. It does not guess. A false pass on a legibility rule is worse than an
honest unknown, so no check in this tool ever reports success on evidence it
does not have.

### About the ALL CAPS requirement

You asked for the whole warning in capitals. 27 CFR 16.21 requires only the
words **GOVERNMENT WARNING** to be capitalised and bold — the rest of the
statement is not required to be in capitals.

Both are implemented, and kept apart:

- `GOVERNMENT WARNING` not in capitals is a **hard failure**, because it is
  the law.
- The whole statement not in capitals is an **advisory** finding, labelled
  `ADVICE ONLY` on screen and clearly marked as house style rather than a
  legal problem.

Advisory findings never cause a label to be reported as failing. This keeps
the tool's legal output defensible while still flagging what you asked for.
Turn the house-style check off with `LABELCHECK_FULL_CAPS=0`.

### Standards of fill are advisory

Permitted container sizes (27 CFR 4.72 and 5.203) have been amended several
times, most recently by T.D. TTB-165 in 2020, and carry exemptions. They live
in data rather than code in `labelcheck/rules.py`, and a non-standard size is
reported as advisory so it never hard-fails a label on a rule that may have
moved. Re-verify the lists against the current eCFR before relying on them.

### Two pictures, pooled text but separate geometry

Text is pooled across panels, because a field is "on the label" if it appears
anywhere on the container. Geometry is not pooled: `merge_results()`
deliberately clears the millimetres-per-pixel figure, since two pictures can
be taken at different scales and a single conversion would be wrong for at
least one of them. Anything that measures physical size therefore runs
against one panel.

A picture that fails to load is handled by position: if the first is
unreadable the check stops and says so, but a bad *second* picture is noted
and skipped rather than throwing away a good first one.

### Large brand names can hide the small print

Tesseract sizes its noise filter against the dominant text on the page. On
label artwork, a very large brand name can push the much smaller mandatory
print below that threshold, so the alcohol content and net contents simply do
not appear in the results — even though they are perfectly legible when
cropped out and read on their own. This was not theoretical: it happened on
the front label of the front/back sample pair.

Neither contrast adjustment, upscaling, nor Tesseract's own noise-filter
settings fixed it reliably. What does work is reading the image again in two
overlapping horizontal bands, which puts text of a similar size together in
each pass. That banded pass runs whenever the time budget allows, and costs
about 0.3s. Repeated readings are harmless — matching is fuzzy — and
identical lines are collapsed before the text is shown to the user.

### OCR is noisy, so matching is fuzzy

Label artwork uses display type, letter spacing, foil and curved surfaces.
Exact string comparison would produce constant false mismatches. Instead the
tool normalises text (case, accents, punctuation), then scores with a sliding
window and a token-coverage measure, so a correct brand name buried in 400
words of OCR still matches, and decorative `B R O O K L Y N` letter spacing
still matches `BROOKLYN`.

Numeric readings are anchored so a longer number cannot be truncated into a
plausible one — `150%` is rejected rather than read as `50%`, and `100% AGAVE`
on a tequila label is not mistaken for an alcohol content.

### Confidence and honesty

Every check has four possible answers, not two: **match**, **problem**,
**check by hand**, and **cannot check**. Fields the application left blank are
reported as "nothing to compare against" rather than quietly skipped.

---

## Performance

The requirement was 5 seconds or less. Measured on the sample labels:

| | Time |
| --- | --- |
| One picture, full HTTP round trip | **0.5 – 1.5 s** |
| Two pictures (front and back) | **~2.2 s** |
| Batch of 7 rows (8 pictures) | **~10 s total**, ~1.4 s a row |

How the budget is held:

- Images are downscaled to 2000px on the long edge before OCR, and small
  images are upscaled to at least 1000px to help with small print.
- A sparse-text pass handles display type, then a banded pass recovers small
  print a dominant brand name would otherwise hide. A third block-text pass
  runs **only** if the health warning has still not been found, since a dense
  paragraph can be missed by a sparse model.
- With two pictures, the OCR budget is shared between them: each panel is
  given a fair share of the time left, so a slow first picture cannot starve
  the second.
- Every OCR call carries a deadline. If time runs out, results gathered so far
  are kept and the report says the check may be incomplete, rather than
  failing outright.

The budget is configurable with `LABELCHECK_TIME_BUDGET`. A check that exceeds
it is flagged in the result.

---

## Security and privacy

The approach is to not hold sensitive data in the first place.

- **No storage.** Label images and company details live in memory for the
  seconds a check takes. There is no database, no uploads folder, and no
  logging of label content — only timings and counts.
- **No accounts, sessions or cookies.** There is no session secret to leak and
  no login state to steal.
- **Batch results** are held in memory for 10 minutes at a random URL, and
  deleted the moment they are downloaded. ZIP extraction goes to a temporary
  directory removed in a `finally` block on every path.
- **Uploads are validated**: extension allowlist, format allowlist, size cap
  (25 MB), and a decompression-bomb guard. Images are decoded before use.
- **Path traversal and zip-slip** are blocked — every path from a CSV or ZIP
  is resolved and confirmed to sit inside the batch folder. Symlink entries
  are skipped.
- **CSV formula injection** is neutralised in exported results, since the
  values come from OCR of an untrusted image and would otherwise execute when
  opened in Excel.
- **Response headers** set a strict Content-Security-Policy (no third-party
  anything), `nosniff`, `DENY` framing, `no-referrer`, and `no-store`.
- **Binds to 127.0.0.1** by default, and runs with the debugger off.

If you put this on a shared address, put it behind a real WSGI server
(`waitress` or `gunicorn`) and an authenticating reverse proxy. It is built as
a single-user local tool.

---

## Testing

```bash
python3 -m unittest discover -s tests -v
```

78 tests. The unit tests are pure and fast; the integration tests drive the
real OCR engine over `samples/labels/`, which contain deliberate defects:

| Sample | Defect it exercises |
| --- | --- |
| `01_bourbon_compliant.png` | none — must pass cleanly |
| `02_wine_abv_mismatch.png` | 15.8% on label vs 13.5% declared, crossing the 14% tax line |
| `03_beer_tiny_warning.png` | health warning at 1.1 mm, below the 2 mm minimum |
| `04_wine_no_warning.png` | no health warning and no sulfite declaration |
| `05_imported_gin_no_origin.png` | imported, but no country of origin on the label |
| `06_cider_lowercase_warning.png` | warning not in capitals; also 6.9% cider, so FDA rules |
| `07_whiskey_front.png` + `07_whiskey_back.png` | a front/back pair: neither panel is compliant alone, both together are |

The integration tests skip themselves with a clear message if Tesseract is not
installed, and one test asserts every sample is checked inside the 5-second
budget.

---

## Layout

```
app.py                     Flask routes and server startup
run.sh                     Dependency check, then start
labelcheck/
  config.py                Limits, time budgets, feature flags
  rules.py                 Per-beverage CFR rules, tolerances, field matrix
  ocr.py                   On-device Tesseract, word boxes, physical scale
  textnorm.py              Normalisation, fuzzy matching, unit parsing
  healthwarning.py         27 CFR Part 16 checks
  compare.py               Field-by-field comparison
  checker.py               Orchestration and time budget
  application.py           Application data, CSV loading, optional TTB lookup
  bulk.py                  Batch runner and results export
  security.py              Upload validation, path confinement, CSV safety
  findings.py              One finding: check, verdict, plain-English text
templates/  static/        Large-type, high-contrast interface
samples/make_samples.py    Generates the test artwork
tests/                     Unit and integration tests
```

---

## Limitations

Worth being straight about:

- **It reads up to two pictures.** A container with mandatory information on a
  third panel (a neck label, or a side panel) is not fully covered. Check the
  remaining panel by eye, or supply a composite image.
- **Bold detection is a hint**, not a determination.
- **"Separate and apart"** (27 CFR 16.21) and contrasting-background rules
  are judgement calls a person must make.
- **Not every rule is covered.** Age statements for young whisky, commodity
  statements, appellations, varietal rules, allergen and aspartame
  declarations, and state-level requirements are out of scope.
- **OCR is imperfect** on curved bottles, foil, and low-contrast artwork. The
  result page shows exactly what was read so you can see when this happens.

This tool is a checking aid. It is not an official determination, and it does
not replace review by a qualified person.
