<div align="center">

# Alcohol Label Compliance Checker

Checks a photo of an alcohol beverage label against the application details and the federal labeling rules in 27 CFR, right in your browser.

### [▶ Open the live checker](https://nachshon90.github.io/alcholprogramchecker/)

**Public URL:** https://nachshon90.github.io/alcholprogramchecker/

[![Tests](https://github.com/nachshon90/alcholprogramchecker/actions/workflows/tests.yml/badge.svg)](https://github.com/nachshon90/alcholprogramchecker/actions/workflows/tests.yml)
[![Deploy](https://github.com/nachshon90/alcholprogramchecker/actions/workflows/pages.yml/badge.svg)](https://github.com/nachshon90/alcholprogramchecker/actions/workflows/pages.yml)

[Try it](#try-it-in-two-minutes) · [What it checks](#what-it-checks) · [Run it locally](#run-it-locally) · [How it works](#how-it-works) · [Hosting](#hosting) · [Limitations](#limitations)

</div>


## At a glance

- **Label vs. application:** reads the label with OCR and checks every required field against the product details you enter.
- **Rules by beverage type:** applies the 27 CFR alcohol tolerances, treats proof and ABV as equivalent, and enforces the 14% wine tax line.
- **Strict on the Government Warning:** exact wording, capital letters, and physical letter size and spacing.
- **Front and back labels:** add up to two photos per product, checked together as one container.
- **Batch mode:** check a whole spreadsheet of products and their photos at once.
- **Plain-English verdicts:** every check returns **match**, **problem**, **check by hand**, or **cannot check**, in a large-type, high-contrast interface.
- **Private by design:** OCR runs on your own device. No cloud services, no accounts, and no network calls while checking.

``
```

---

## Try it in two minutes

The repo includes seven sample labels in [`samples/labels/`](samples/labels/), each built with a deliberate defect, and their matching application data in [`samples/sample_batch.csv`](samples/sample_batch.csv).

**Check all the samples at once**

1. Download this repo (**Code → Download ZIP**) and unzip it.
2. Open the [live checker](https://nachshon90.github.io/alcholprogramchecker/) and select **Check many labels**.
3. Choose `samples/sample_batch.csv`, then select every picture in `samples/labels/` together.
4. Compare your results with the table below.

**Or check a single label:** upload one picture on the home page, enter its details from the CSV, and type in the label width from the table.

| Sample picture | Label width (mm) | Expected result | What it tests |
| --- | --- | --- | --- |
| `01_bourbon_compliant.png` | 95 | ✅ Pass | A fully compliant label |
| `02_wine_abv_mismatch.png` | 100 | ❌ Alcohol content | 15.8% on the label vs. 13.5% declared, crossing the 14% tax line |
| `03_beer_tiny_warning.png` | 90 | ❌ Warning too small | Warning letters are 1.1 mm tall; a 12 fl oz container needs 2 mm |
| `04_wine_no_warning.png` | 100 | ❌ Warning and sulfites missing | No health warning and no sulfite declaration |
| `05_imported_gin_no_origin.png` | 95 | ❌ Country of origin missing | An imported product with no country of origin |
| `06_cider_lowercase_warning.png` | 90 | ❌ Warning not in capitals | Also a 6.9% cider, so FDA rules apply instead of Part 4 |
| `07_whiskey_front.png` + `07_whiskey_back.png` | 95 and 95 | ✅ Pass, warning found on picture 2 | Neither panel is compliant alone; together they are |

> [!NOTE]
> The first visit downloads the OCR engine and English model (about 7 MB). After that your browser caches them, and each check takes about 3–4 seconds.

---

## What it checks

### Required fields

| Field | Required for | Authority |
| --- | --- | --- |
| Brand name | All products | 27 CFR 4.32, 5.63, 7.63 |
| Class / type designation | All products | 27 CFR 4.32, 5.63, 7.63 |
| Alcohol content | Wine and spirits (conditional for malt beverages) | 27 CFR 4.36, 5.65, 7.65 |
| Net contents | All products | 27 CFR 4.32, 5.63, 7.63 |
| Bottler, producer, or importer name | All products | 27 CFR 4.35, 5.66, 7.66 |
| Bottler or producer address | All products | 27 CFR 4.35, 5.66, 7.66 |
| Country of origin | Imports | 19 CFR 134 |
| Sulfite declaration | Wine with 10 ppm or more | 27 CFR 4.32(e) |
| Government Health Warning | Everything at 0.5% ABV or more | 27 CFR Part 16 |

Fields left blank on the application are reported as "nothing to compare against," never silently skipped.

### Alcohol content tolerances

Labels don't need to match the declared strength exactly, because the regulations allow a tolerance:

| Beverage | Allowed difference | Authority |
| --- | --- | --- |
| Distilled spirits | 0.15 percentage points | 27 CFR 5.65(a) |
| Malt beverages | 0.3 percentage points | 27 CFR 7.71 |
| Wine at or below 14% ABV | 1.5 percentage points | 27 CFR 4.36(b) |
| Wine above 14% ABV | 1.0 percentage point | 27 CFR 4.36(b) |

Proof and ABV are interchangeable, so a label reading `90 PROOF` matches a declared `45% ABV`.

**The wine tolerance can never cross the 14% line**, because wine on each side of it is taxed differently. A label reading 14.4% against a declared 13.9% is inside the 1.5-point tolerance but still fails.

### Beverage types

The tool applies the right rule set for each product, chosen on the form or inferred from the class/type designation.

| Beverage | Covers | Rules applied |
| --- | --- | --- |
| Malt beverage | Beer, ale, lager, stout, porter, IPA, flavored malt beverages | 27 CFR Part 7 |
| Wine | Still, sparkling, and fortified wine; sake and mead | 27 CFR Part 4 |
| Distilled spirits | Whisky, vodka, gin, rum, brandy, tequila, liqueurs | 27 CFR Part 5 |
| Hard cider | At 7% ABV or more | 27 CFR Part 4 |
| Other beverages | Under 7% ABV, such as lower-strength cider | FDA labeling rules, plus the Government Warning |

Beverages under 7% ABV fall outside the Federal Alcohol Administration Act, so FDA rules govern most of the label. The Government Warning is still required, because 27 CFR Part 16 covers every beverage at 0.5% ABV or more. Cider switches automatically: the same product is checked under Part 4 at 8% ABV and under FDA rules at 5%.

### The Government Health Warning

This is the strictest check, and it goes well beyond a text search. The required statement (27 CFR 16.21) is:

> **GOVERNMENT WARNING:** (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.

| Check | Rule | If it fails |
| --- | --- | --- |
| Statement is present with exact wording, checked segment by segment | 27 CFR 16.21 | Problem, naming the part that's missing or different |
| `GOVERNMENT WARNING` is in capital letters | 27 CFR 16.22(a)(2) | Problem (hard failure) |
| Letter height is at least 1 mm (237 mL or less), 2 mm (over 237 mL up to 3 L), or 3 mm (over 3 L) | 27 CFR 16.22(b) | Problem |
| No more than 40, 25, or 12 characters per inch for those same size tiers | 27 CFR 16.22(a)(4) | Problem |
| `GOVERNMENT WARNING` is in bold | 27 CFR 16.22(a)(2) | Advisory hint only, since bold can't be reliably detected in a photo |
| The entire statement is in capitals | House style, not law | `ADVICE ONLY`; never fails a label |

Letter height and spacing are physical measurements, so they need the label's real width or the image's DPI. Without either, those checks report "cannot check." Height is measured from the capital letters of `GOVERNMENT WARNING`, which gives a clean reading. When two pictures are supplied, the tool measures whichever panel actually carries the warning, and the results page says which one it used.

---

## Using the checker

### Check one label

1. Enter the product details from the application.
2. Upload the label picture. If the product has a back label (usually where the warning and bottler address are), add it as the second picture.
3. Enter each label's real width in millimeters, measured with a ruler.
4. Run the check. Results appear in seconds.

Text is pooled across both pictures, so a field counts as present if it appears on either one.

> [!TIP]
> **Enter the label width.** It's optional, but without it the tool can't convert pixels to millimeters, so it can't check the warning's type size. Each picture has its own width box because front and back labels are often different sizes. Scanned artwork that records its own DPI is measured automatically.

### Check many labels

1. Open **Check many labels** and download the blank spreadsheet. Fill in one row per product.
2. Gather the label pictures. In the browser build, select them all at once. In the Python app, upload them as a ZIP or point the folder box at the folder that holds them.
3. Submit. Pictures are matched to rows by file name, and you get a results table plus a downloadable results file.

The spreadsheet needs a header row, and column names are flexible:

| Column | Accepted names |
| --- | --- |
| Front label picture | `image`, `file`, `filename`, `label`, `artwork` |
| Back label picture (optional) | `image_2`, `back_image`, `back` |
| Label widths in mm | `label_width_mm`, and `label_width_mm_2` for the back label |
| Brand name | `brand`, `brand_name` |
| Alcohol content | `abv`, `alcohol_content` |

Other fields accept similar variations. Unrecognized columns are ignored with a note rather than rejected, so spreadsheet exports with extra bookkeeping columns work fine. Leave `image_2` blank for single-label products. [`samples/sample_batch.csv`](samples/sample_batch.csv) is a complete example, and `python3 samples/make_samples.py` regenerates the sample artwork.

---

## Run it locally

Two builds share the same compliance rules:

| | Browser build (`web/`) | Python app |
| --- | --- | --- |
| **Runs** | Entirely in your browser (Tesseract compiled to WebAssembly) | On a local server (native Tesseract) |
| **Speed** | About 3–4 s per label | About 0.5–1.5 s per label |
| **Install** | Nothing | Python 3 and Tesseract |
| **Best for** | A public link with zero setup | The fastest checks and the batch CSV tooling |

The rules exist twice, in `labelcheck/` (Python) and `web/js/` (JavaScript). To keep the two from quietly disagreeing, `tests/parity.mjs` runs the same inputs through both and fails CI on any difference. Python is the reference implementation, with the larger test suite.

### Option 1: Browser build (no install)

```bash
git clone https://github.com/nachshon90/alcholprogramchecker.git
cd alcholprogramchecker/web
python3 -m http.server 8099
```

Then open [http://127.0.0.1:8099](http://127.0.0.1:8099). No Tesseract or Python packages needed.

### Option 2: Python app (fastest)

**1. Install the Tesseract OCR engine.** It's a regular program, not a Python package.

| System | Command |
| --- | --- |
| Ubuntu / Debian | `sudo apt-get install tesseract-ocr` |
| Red Hat / Fedora | `sudo dnf install tesseract` |
| macOS | `brew install tesseract` |
| Windows | [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki) |

Confirm it worked with `tesseract --version`.

**2. Install, test, and start the app.**

```bash
git clone https://github.com/nachshon90/alcholprogramchecker.git
cd alcholprogramchecker
pip3 install -r requirements.txt
python3 -m unittest discover -s tests   # 119 tests, including real OCR on the samples
./run.sh                                # Windows: python app.py
```

**3. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.**

`run.sh` checks both dependencies before starting. If Tesseract is missing, the app still starts, but every page explains how to install it. It never silently returns a wrong answer.

---

## How it works

**Built with:** Python, Flask, and Pillow · Tesseract OCR through pytesseract · Waitress for hosted mode · tesseract.js (Tesseract compiled to WebAssembly) for the browser build · GitHub Actions and GitHub Pages

### Performance

The requirement was 5 seconds or less per label. Measured on the sample labels with the Python app:

| Scenario | Time |
| --- | --- |
| One picture, full HTTP round trip | 0.5–1.5 s |
| Front and back pictures | About 2.2 s |
| Batch of 7 rows (8 pictures) | About 10 s total, about 1.4 s per row |

The browser build takes about 3–4 s per label, still inside the budget. The budget is configurable with `LABELCHECK_TIME_BUDGET`, and any check that exceeds it is flagged in the result.

<details>
<summary><b>How the time budget is held</b></summary>

- **Right-sized images.** Pictures are scaled down to 2000 px on the long edge, and small ones are scaled up to at least 1000 px to help with small print.
- **OCR in passes.** A sparse-text pass handles display type, then a banded pass recovers small print. A third, block-text pass runs only if the health warning still hasn't been found.
- **Fair sharing.** With two pictures, each gets a fair share of the remaining time, so a slow first picture can't starve the second.
- **Deadlines on every OCR call.** If time runs out, results gathered so far are kept and the report says the check may be incomplete, rather than failing outright.

</details>

### Design decisions and assumptions

- **No cloud APIs, and that's verified.** OCR runs locally with Tesseract, and nothing sends an image or company detail anywhere. Outbound access really is blocked in the build environment: fetching `https://www.ttb.gov/` returns `EGRESS_BLOCKED`.
- **Application data is what you enter.** The form or batch CSV is the data of record. An optional TTB lookup (`fetch_from_ttb()` in `labelcheck/application.py`) is off by default, because TTB publishes label data as a search page for people rather than an API, and review networks usually block ttb.gov. If you enable it with `LABELCHECK_ENABLE_TTB_LOOKUP=1`, it fails with a plain explanation and never blocks a check.
- **Unknown is reported as unknown.** Letter size needs physical scale, taken from your measured label width or the image's DPI. Without either, the tool says "cannot check" and what to supply, because a false pass on a legibility rule is worse than an honest unknown.
- **Law and house style are kept apart.** The request was for the whole warning in capitals, but 27 CFR 16.22(a)(2) only requires `GOVERNMENT WARNING` in capitals and bold. So a lowercase `GOVERNMENT WARNING` is a hard failure, while a lowercase statement body is `ADVICE ONLY` and never fails a label. Turn that advisory off with `LABELCHECK_FULL_CAPS=0`.
- **Standards of fill are advisory.** Permitted container sizes (27 CFR 4.72 and 5.203) have been amended several times, most recently by T.D. TTB-165 in 2020, and carry exemptions. They're stored as data in `labelcheck/rules.py`, a non-standard size is advisory only, and the lists should be re-verified against the current eCFR before relying on them.
- **Two pictures: pooled text, separate measurements.** Text is pooled because a field counts if it appears anywhere on the container. Size checks run on a single panel, because two photos can be taken at different scales. If the first picture can't be read the check stops; a bad second picture is noted and skipped.
- **Banded OCR recovers hidden small print.** On the front label of the front/back sample pair, a very large brand name made Tesseract filter out the small alcohol content and net contents text. Re-reading the image in two overlapping horizontal bands fixed it where contrast tweaks, upscaling, and Tesseract's own settings didn't, at a cost of about 0.3 s.
- **Fuzzy matching for noisy OCR.** Text is normalized (case, accents, punctuation) and scored with a sliding window and token coverage, so a brand name buried in 400 words of OCR still matches and `B R O O K L Y N` matches `BROOKLYN`. Numbers are anchored, so `150%` isn't read as `50%` and `100% AGAVE` isn't mistaken for an alcohol content.
- **Four answers, not two.** Every check returns match, problem, check by hand, or cannot check, instead of a simple pass or fail.

---

## Security and privacy

The approach is simple: don't hold sensitive data in the first place. The browser build goes further, with no cookies, no storage, and no network requests while checking, so label pictures never leave the device.

| Area | Protection |
| --- | --- |
| Storage | None. Images and company details live in memory only for the seconds a check takes. No database, no uploads folder, and no logging of label content (only timings and counts). |
| Accounts | No accounts, sessions, or cookies, so there's no session secret to leak and no login to steal. |
| Batch results | Held in memory for 10 minutes at a random URL and deleted as soon as they're downloaded. ZIP extraction uses a temporary folder that's removed on every path. |
| Uploads | Extension and format allowlists, a 25 MB size cap, and a decompression-bomb guard. Images are decoded before use. |
| File paths | Path traversal and zip-slip are blocked. Every path from a CSV or ZIP must resolve inside the batch folder, and symlinks are skipped. |
| CSV exports | Formula injection is neutralized, since exported values come from OCR of untrusted images. |
| HTTP headers | Strict Content-Security-Policy, `nosniff`, `DENY` framing, `no-referrer`, and `no-store`. |
| Network | Binds to `127.0.0.1` by default, with the debugger off. |

---

## Hosting

**For a public link, use the browser build.** It's free on any static host and keeps pictures on the visitor's device. The live link at the top of this page is published this way.

- **GitHub Pages:** `.github/workflows/pages.yml` publishes `web/` on every push to `main`. Turn it on once under **Settings → Pages → Source: GitHub Actions**.
- **Render, Netlify, Cloudflare Pages, or GitLab Pages:** set the publish directory to `web`, with no build command. `render.yaml` already declares the static service.

Vendored libraries and their licenses are listed in [`web/vendor/README.md`](web/vendor/README.md).

### Hosting the Python app

A static host can't run the Python app, since static hosting only serves files. It needs a host that runs a server.

> [!CAUTION]
> **Hosting the Python app weakens the privacy guarantee.** Label pictures and company details travel to a server you don't control. They're still never written to disk and are discarded after each check, and the hosted pages say so in their footer instead of repeating the local-only promise.

The production entry point, `wsgi.py`, adds safeguards that local runs don't need:

- **Password required.** It refuses to start without `LABELCHECK_PASSWORD`, or with one shorter than 12 characters.
- **Every page is protected** with HTTP Basic auth, compared in constant time. Only `/healthz` stays open, for host health checks.
- **Rate limiting** per address, 40 checks per 5 minutes by default, since OCR is CPU-heavy.
- **HSTS** over HTTPS, and `LABELCHECK_BEHIND_PROXY=1` reads the real client address and scheme from the proxy in front.
- **Waitress** serves the app instead of the Flask development server.

| Host | Cost | Notes |
| --- | --- | --- |
| Hugging Face Spaces | Free | Runs Docker on real CPU cores with no code changes. The easiest free option. |
| Google Cloud Run | Free tier | Scales to zero, so it costs nothing when idle. Needs a Google Cloud account. |
| Render | From about $7/month | Blueprint included. The free instance has roughly a tenth of a core, so checks are slow and it sleeps when idle. |
| Your own machine | Free | Fastest and fully private. |

> [!WARNING]
> **Run exactly one instance with one process.** Batch results live in that process's memory for 10 minutes so downloads don't re-run the batch. With several workers, a download can land on one that never saw the results and return "expired." Waitress handles concurrency with threads in a single process, so don't put it behind multi-worker gunicorn, and keep `numInstances: 1`.
>
> **Give it at least 512 MB of memory.** OCR on a large image needs a few hundred megabytes, and a 256 MB instance will be killed mid-check.

<details>
<summary><b>Deploy to Hugging Face Spaces</b></summary>

1. Create a Space at [huggingface.co/new-space](https://huggingface.co/new-space) and choose **Docker → Blank** as the SDK.
2. In the Space's **Settings → Variables and secrets**, add the secret `LABELCHECK_PASSWORD` with a long random value. The app won't start without it.
3. Run `./deploy/huggingface/publish.sh <your-hf-username>`.

The script exports the committed files, swaps in the Space's own README (its YAML header configures the Space), and pushes without storing or echoing your token. Your URL will be `https://<username>-alcohol-label-checker.hf.space`, and the first build takes a few minutes while Tesseract installs.

</details>

<details>
<summary><b>Deploy to Google Cloud Run</b></summary>

Create the password secret first:

```bash
printf '%s' 'choose-a-long-random-password' \
  | gcloud secrets create labelcheck-password --data-file=-
```

Then deploy:

```bash
gcloud run deploy alcohol-label-checker \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --max-instances 1 \
  --set-env-vars LABELCHECK_BEHIND_PROXY=1 \
  --set-secrets LABELCHECK_PASSWORD=labelcheck-password:latest
```

`--allow-unauthenticated` only refers to Google's IAM layer; the app's own password still applies. Keep `--max-instances 1`.

</details>

<details>
<summary><b>Deploy to Render</b></summary>

1. Push the repository to GitHub.
2. In Render, choose **New → Blueprint** and point it at the repository. `render.yaml` describes the setup.
3. Set `LABELCHECK_PASSWORD` in the dashboard to a long random value. It's marked `sync: false`, so the password is never committed.
4. Deploy.

To try Render's free instance first, change `plan: starter` to `plan: free` in `render.yaml`. Expect slow checks and a cold start of up to a minute.

</details>

<details>
<summary><b>Deploy to any Docker host</b></summary>

```bash
docker build -t label-checker .
docker run -p 8080:8080 \
  -e LABELCHECK_PASSWORD="choose-a-long-random-password" \
  -e LABELCHECK_BEHIND_PROXY=1 \
  label-checker
```

The `Dockerfile` installs the Tesseract engine itself. That's the usual reason naive deployments fail: a plain Python buildpack installs the `pytesseract` wrapper with nothing for it to wrap. The image runs as an unprivileged user and includes a health check. CI builds it on every push and confirms it refuses to start without a password, requires the password when one is set, and passes a known-good label through OCR inside the container.

</details>

<details>
<summary><b>All environment variables</b></summary>

| Variable | Default | Purpose |
| --- | --- | --- |
| `LABELCHECK_PASSWORD` | *(none)* | Required for hosting. Turns on all the safeguards above. |
| `LABELCHECK_BEHIND_PROXY` | off | Trust `X-Forwarded-*` headers from the proxy in front. |
| `PORT` | 8080 | Port to listen on. Most hosts set this for you. |
| `LABELCHECK_THREADS` | 4 | Concurrent requests served. |
| `LABELCHECK_RATE_MAX` | 40 | Checks allowed per address per window. |
| `LABELCHECK_RATE_WINDOW` | 300 | Rate-limit window, in seconds. |
| `LABELCHECK_TIME_BUDGET` | 5.0 | Seconds allowed per label. |
| `LABELCHECK_FULL_CAPS` | on | Set to `0` to turn off the whole-statement capitals advisory. |
| `LABELCHECK_ENABLE_TTB_LOOKUP` | off | Set to `1` to enable the optional TTB lookup. |

</details>

Hosted mode has no user accounts, audit log, or per-user separation: everyone with the password shares one service. That suits a small review team, but not handling other companies' confidential artwork at scale. For that, run local copies.

---

## Testing

```bash
python3 -m unittest discover -s tests -v   # 119 Python tests
node tests/parity.mjs                      # Python and JavaScript must agree
node tests/browser.mjs                     # drives the real page in Chromium
```

All of these run in CI. The Python suite runs on every push and pull request against Python 3.9 and 3.12 (`.github/workflows/tests.yml`) with the real Tesseract engine installed, and CI fails if Tesseract is missing, so OCR tests can't silently skip and report a hollow green check. Locally, the integration tests skip with a clear message when Tesseract isn't installed. One test also asserts that every sample is checked within the 5-second budget.

<details>
<summary><b>What the tests cover</b></summary>

| Suite | What it covers |
| --- | --- |
| Unit | Parsing, tolerances, classification, path confinement, CSV safety |
| Integration | The real OCR engine run over `samples/labels/` |
| Web (`tests/test_web.py`) | Every route, template, and upload rejection, plus the batch download, through Flask's test client |
| Hosting (`tests/test_hosting.py`) | The password, rate limit, open health check, honest hosted footer, and that `wsgi.py` refuses to start unprotected |
| Parity (`tests/parity.mjs`) | Parsing, fuzzy-match scores, beverage classification, tolerances, and type-size tiers agree between Python and JavaScript |
| Browser (`tests/browser.mjs`) | In Chromium: a compliant label passes, an undersized or missing warning is caught, and a front/back pair is combined correctly |

</details>

---

## Project layout

<details>
<summary><b>Show the file tree</b></summary>

```
app.py                     Flask routes, and the local server entry point
wsgi.py                    Production entry point for a hosted deployment
run.sh                     Dependency check, then start
Dockerfile                 Image that includes the Tesseract engine
render.yaml                Deployment blueprint for Render
deploy/huggingface/        Free Docker hosting: Space card and publish script
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
  hosting.py               Password, rate limit, proxy support (hosted only)
  findings.py              One finding: check, verdict, plain-English text
templates/  static/        Large-type, high-contrast interface
samples/make_samples.py    Generates the test artwork
web/                       The static, browser-only build
  index.html bulk.html help.html
  js/                      The compliance logic, ported to JavaScript
  vendor/                  Tesseract WebAssembly, vendored (see its README)
tests/                     Unit and integration tests
  browser.mjs              Drives the static build in Chromium
  parity.mjs               Python and JavaScript must agree
```

</details>

---

## Limitations

- **Up to two pictures per product.** Mandatory information on a third panel, such as a neck or side label, isn't covered. Check that panel by eye or supply a composite image.
- **Bold detection is a hint,** not a determination.
- **Some rules need a person's judgment,** such as whether the warning is "separate and apart" (27 CFR 16.21) and on a contrasting background.
- **Not every rule is covered.** Age statements for young whisky, commodity statements, appellations, varietal rules, allergen and aspartame declarations, and state-level requirements are out of scope.
- **OCR is imperfect** on curved bottles, foil, and low-contrast artwork. The results page shows exactly what was read, so you can see when this happens.

> [!IMPORTANT]
> This tool is a checking aid. It isn't an official determination and doesn't replace review by a qualified person.
