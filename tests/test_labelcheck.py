"""Unit and integration tests.

Run with:  python3 -m unittest discover -s tests -v

The unit tests are pure and fast. The integration tests at the bottom drive
the real OCR engine over the generated sample labels, and are skipped
automatically when Tesseract is not installed.
"""
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from labelcheck import config, healthwarning, rules, security  # noqa: E402
from labelcheck.application import (  # noqa: E402
    ApplicationDataError, from_mapping, rows_from_csv, template_csv,
)
from labelcheck.compare import (  # noqa: E402
    check_alcohol_content, check_country_of_origin, check_net_contents,
    check_sulfites,
)
from labelcheck.findings import FAIL, PASS, UNKNOWN, WARN, worst  # noqa: E402
from labelcheck.ocr import OcrResult, Word, merge_results  # noqa: E402
from labelcheck.textnorm import (  # noqa: E402
    field_match_score, parse_alcohol, parse_net_contents, token_coverage,
)


def fake_ocr(text: str) -> OcrResult:
    """An OcrResult carrying just text, for comparison-logic tests."""
    words = []
    for line_number, line in enumerate(text.splitlines()):
        for position, token in enumerate(line.split()):
            words.append(Word(text=token, conf=90.0, left=position * 50,
                              top=line_number * 40, width=45, height=30,
                              line_key=(0, 0, line_number)))
    return OcrResult(text=text, words=words, image_width=1000,
                     image_height=1000)


class TestAlcoholParsing(unittest.TestCase):
    def test_common_abv_formats(self):
        for text, expected in [
            ("ALC. 13.5% BY VOL", 13.5),
            ("40% ALC/VOL", 40.0),
            ("5.2% ABV", 5.2),
            ("ALCOHOL 12% BY VOLUME", 12.0),
            ("ALC 5,2% VOL", 5.2),          # European decimal comma
        ]:
            with self.subTest(text=text):
                values = [e["abv"] for e in parse_alcohol(text)]
                self.assertIn(expected, values)

    def test_proof_converts_to_abv(self):
        entries = parse_alcohol("90 PROOF")
        self.assertEqual(entries[0]["kind"], "proof")
        self.assertAlmostEqual(entries[0]["abv"], 45.0)

    def test_impossible_values_rejected(self):
        # 150% ABV is not a reading, it is OCR noise.
        self.assertEqual([e for e in parse_alcohol("150% ALC/VOL")], [])

    def test_no_alcohol_statement(self):
        self.assertEqual(parse_alcohol("BOTTLED IN KENTUCKY"), [])


class TestNetContentsParsing(unittest.TestCase):
    def test_metric_and_customary(self):
        for text, expected_ml in [
            ("750 mL", 750.0), ("1.75 L", 1750.0), ("50 cl", 500.0),
        ]:
            with self.subTest(text=text):
                self.assertAlmostEqual(parse_net_contents(text)[0]["ml"],
                                       expected_ml, places=1)

    def test_fluid_ounces(self):
        self.assertAlmostEqual(parse_net_contents("12 FL OZ")[0]["ml"],
                               354.88, places=1)

    def test_compound_imperial_statement(self):
        # "1 PT 9 FL OZ" is a single quantity, not two.
        parsed = parse_net_contents("1 PT 9 FL OZ")
        self.assertEqual(len(parsed), 1)
        self.assertAlmostEqual(parsed[0]["ml"], 739.3, places=0)


class TestFuzzyMatching(unittest.TestCase):
    def test_matches_through_ocr_noise(self):
        score = field_match_score("Old Bridge Distillery",
                                  "SINCE 1897 0LD BRIDGE DISTILLERY KENTUCKY")
        self.assertGreater(score, config.MATCH_THRESHOLD)

    def test_matches_letterspaced_display_type(self):
        self.assertGreater(field_match_score("BROOKLYN", "B R O O K L Y N BREWING"),
                           config.MATCH_THRESHOLD)

    def test_rejects_a_different_brand(self):
        score = field_match_score("Old Bridge Distillery", "MOUNTAIN CREEK VINEYARDS")
        self.assertLess(score, config.PRESENCE_THRESHOLD)

    def test_token_coverage_ignores_company_boilerplate(self):
        self.assertEqual(token_coverage("Harbor Light Brewing Co.",
                                        "HARBOR LIGHT BREWING"), 1.0)


class TestBeverageClassification(unittest.TestCase):
    def test_infers_class_from_designation(self):
        for text, expected in [
            ("Kentucky Straight Bourbon Whisky", "distilled_spirits"),
            ("India Pale Ale", "malt_beverage"),
            ("Cabernet Sauvignon", "wine"),
            ("Junmai Ginjo", "sake"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(rules.resolve_class(None, text), expected)

    def test_operator_choice_wins(self):
        self.assertEqual(rules.resolve_class("beer", "Cabernet Sauvignon"),
                         "malt_beverage")

    def test_low_alcohol_cider_leaves_the_faa_act(self):
        # Under 7% ABV cider is labelled under FDA rules, not Part 4.
        self.assertEqual(rules.resolve_class(None, "Hard Cider", 5.0),
                         "fda_regulated")
        self.assertEqual(rules.resolve_class(None, "Hard Cider", 8.0), "cider")
        self.assertFalse(rules.get_rules("fda_regulated").faa_act_covered)

    def test_wine_tolerance_depends_on_strength(self):
        wine = rules.get_rules("wine")
        self.assertEqual(wine.abv_tolerance_for(13.0), 1.5)
        self.assertEqual(wine.abv_tolerance_for(15.0), 1.0)


class TestAlcoholComparison(unittest.TestCase):
    def _check(self, beverage, declared, on_label):
        app = from_mapping({"alcohol_content": declared,
                            "beverage_class": beverage})
        return check_alcohol_content(app, fake_ocr(on_label),
                                     rules.get_rules(beverage))[0]

    def test_spirits_tolerance_is_tight(self):
        self.assertEqual(self._check("distilled_spirits", "40% ABV",
                                     "40.1% ALC/VOL").status, PASS)
        self.assertEqual(self._check("distilled_spirits", "40% ABV",
                                     "40.5% ALC/VOL").status, FAIL)

    def test_malt_beverage_tolerance(self):
        self.assertEqual(self._check("malt_beverage", "5.0% ABV",
                                     "5.2% ALC/VOL").status, PASS)
        self.assertEqual(self._check("malt_beverage", "5.0% ABV",
                                     "5.6% ALC/VOL").status, FAIL)

    def test_proof_on_label_matches_abv_declaration(self):
        finding = self._check("distilled_spirits", "45% ABV", "90 PROOF")
        self.assertEqual(finding.status, PASS)

    def test_tolerance_may_not_cross_the_wine_tax_class_line(self):
        # 13.9 vs 14.4 is inside the 1.5 point tolerance, but crosses 14%.
        finding = self._check("wine", "13.9% ABV", "ALC 14.4% BY VOL")
        self.assertEqual(finding.status, FAIL)
        self.assertIn("14%", finding.title)

    def test_missing_from_label_is_reported(self):
        finding = self._check("distilled_spirits", "40% ABV", "OLD BRIDGE")
        self.assertEqual(finding.status, FAIL)
        self.assertIn("missing", finding.title.lower())


class TestNetContentsComparison(unittest.TestCase):
    def test_metric_and_customary_agree(self):
        app = from_mapping({"net_contents": "750 mL",
                            "beverage_class": "distilled_spirits"})
        findings = check_net_contents(app, fake_ocr("25.4 FL OZ"),
                                      rules.get_rules("distilled_spirits"))
        self.assertEqual(findings[0].status, PASS)

    def test_wrong_size_is_a_failure(self):
        app = from_mapping({"net_contents": "750 mL",
                            "beverage_class": "distilled_spirits"})
        findings = check_net_contents(app, fake_ocr("1.75 L"),
                                      rules.get_rules("distilled_spirits"))
        self.assertEqual(findings[0].status, FAIL)

    def test_non_standard_fill_is_advisory_only(self):
        app = from_mapping({"net_contents": "690 mL",
                            "beverage_class": "distilled_spirits"})
        findings = check_net_contents(app, fake_ocr("690 mL"),
                                      rules.get_rules("distilled_spirits"))
        advisory = [f for f in findings if f.advisory]
        self.assertTrue(advisory)
        self.assertTrue(all(f.advisory for f in findings if f.status == WARN))


class TestCountryOfOrigin(unittest.TestCase):
    def test_absent_statement_reads_as_missing_not_mismatched(self):
        app = from_mapping({"country_of_origin": "Scotland", "is_import": "yes"})
        finding = check_country_of_origin(
            app, fake_ocr("THISTLE ROW DISTILLERS EDINBURGH"),
            rules.get_rules("distilled_spirits"))[0]
        self.assertEqual(finding.status, FAIL)
        self.assertIn("missing", finding.title.lower())

    def test_present_statement_matches(self):
        app = from_mapping({"country_of_origin": "Scotland", "is_import": "yes"})
        finding = check_country_of_origin(
            app, fake_ocr("PRODUCT OF SCOTLAND"),
            rules.get_rules("distilled_spirits"))[0]
        self.assertEqual(finding.status, PASS)

    def test_not_required_for_domestic_products(self):
        app = from_mapping({})
        finding = check_country_of_origin(app, fake_ocr("ANYTHING"),
                                          rules.get_rules("malt_beverage"))[0]
        self.assertEqual(finding.status, PASS)


class TestSulfites(unittest.TestCase):
    def test_wine_without_declaration_is_flagged(self):
        app = from_mapping({"beverage_class": "wine", "contains_sulfites": "yes"})
        finding = check_sulfites(app, fake_ocr("CHARDONNAY 750 ML"),
                                 rules.get_rules("wine"))[0]
        self.assertEqual(finding.status, FAIL)

    def test_declaration_present(self):
        app = from_mapping({"beverage_class": "wine", "contains_sulfites": "yes"})
        finding = check_sulfites(app, fake_ocr("CONTAINS SULFITES"),
                                 rules.get_rules("wine"))[0]
        self.assertEqual(finding.status, PASS)

    def test_not_required_below_threshold(self):
        app = from_mapping({"beverage_class": "wine", "contains_sulfites": "no"})
        finding = check_sulfites(app, fake_ocr("CHARDONNAY"),
                                 rules.get_rules("wine"))[0]
        self.assertEqual(finding.status, PASS)


class TestHealthWarning(unittest.TestCase):
    def test_type_size_tiers(self):
        self.assertEqual(healthwarning.required_mm(200.0)[0], 1.0)
        self.assertEqual(healthwarning.required_mm(750.0)[0], 2.0)
        self.assertEqual(healthwarning.required_mm(5000.0)[0], 3.0)

    def test_unknown_volume_is_flagged_as_assumed(self):
        minimum, _, assumed = healthwarning.required_mm(None)
        self.assertEqual(minimum, 2.0)
        self.assertTrue(assumed)

    def test_missing_warning_fails(self):
        findings = healthwarning.check(fake_ocr("OLD BRIDGE BOURBON 750 ML"),
                                       volume_ml=750)
        self.assertEqual(findings[0].status, FAIL)
        self.assertIn("missing", findings[0].title.lower())

    def test_correct_wording_passes(self):
        result = fake_ocr(healthwarning.FULL_STATEMENT.upper())
        findings = healthwarning.check(result, volume_ml=750)
        wording = [f for f in findings if "wording" in f.title.lower()]
        self.assertEqual(wording[0].status, PASS)

    def test_incomplete_wording_fails(self):
        # Part (2) omitted entirely.
        partial = f"{healthwarning.PREFIX} {healthwarning.PART_ONE}".upper()
        findings = healthwarning.check(fake_ocr(partial), volume_ml=750)
        wording = [f for f in findings if "wording" in f.title.lower()]
        self.assertEqual(wording[0].status, FAIL)

    def test_lowercase_prefix_fails(self):
        text = healthwarning.FULL_STATEMENT.replace(
            "GOVERNMENT WARNING:", "Government Warning:")
        findings = healthwarning.check(fake_ocr(text), volume_ml=750)
        caps = [f for f in findings if "capital letters" in f.title
                and not f.advisory]
        self.assertEqual(caps[0].status, FAIL)

    def test_type_size_unverifiable_without_scale(self):
        # No mm_per_px means we must say so, never quietly pass.
        result = fake_ocr(healthwarning.FULL_STATEMENT.upper())
        findings = healthwarning.check(result, volume_ml=750)
        size = [f for f in findings if "big" in f.title.lower()
                or "how big" in f.title.lower()]
        self.assertTrue(size)
        self.assertEqual(size[0].status, UNKNOWN)

    def test_full_caps_finding_is_advisory_only(self):
        text = (healthwarning.PREFIX + " " + healthwarning.PART_ONE + " "
                + healthwarning.PART_TWO)
        findings = healthwarning.check(fake_ocr(text), volume_ml=750)
        house = [f for f in findings if "house style" in f.title.lower()]
        self.assertTrue(house)
        self.assertTrue(all(f.advisory for f in house))


class TestMultiplePanels(unittest.TestCase):
    """Up to two pictures per scan: a front label and an optional back."""

    def test_merge_pools_text_from_every_panel(self):
        merged = merge_results([fake_ocr("BRAND NAME"), fake_ocr("750 ML")])
        self.assertIn("BRAND NAME", merged.text)
        self.assertIn("750 ML", merged.text)

    def test_merge_clears_physical_scale(self):
        # Two pictures can be taken at different scales, so one conversion
        # factor would be wrong for at least one of them.
        first = fake_ocr("A")
        first.mm_per_px = 0.1
        second = fake_ocr("B")
        second.mm_per_px = 0.4
        self.assertIsNone(merge_results([first, second]).mm_per_px)

    def test_merge_keeps_panel_lines_apart(self):
        merged = merge_results([fake_ocr("ONE"), fake_ocr("TWO")])
        keys = {w.line_key for w in merged.words}
        self.assertEqual(len(keys), 2)

    def test_single_result_passes_through_untouched(self):
        only = fake_ocr("ONLY ONE")
        self.assertIs(merge_results([only]), only)

    def test_warning_located_on_the_back_panel(self):
        front = fake_ocr("IRONWOOD BEND TENNESSEE WHISKEY")
        back = fake_ocr(healthwarning.FULL_STATEMENT.upper())
        findings, panel = healthwarning.check_panels(
            [(front, None), (back, None)], volume_ml=750)
        self.assertEqual(panel, 1)
        self.assertFalse(any("missing" in f.title.lower() for f in findings))

    def test_warning_absent_from_both_panels_is_reported_missing(self):
        findings, panel = healthwarning.check_panels(
            [(fake_ocr("BRAND"), None), (fake_ocr("750 ML"), None)],
            volume_ml=750)
        self.assertIsNone(panel)
        self.assertEqual(findings[0].status, FAIL)
        self.assertIn("missing", findings[0].title.lower())

    def test_application_reports_one_or_two_panels(self):
        one = from_mapping({"image_path": "front.png", "label_width_mm": "95"})
        self.assertEqual(one.panels(), [("front.png", 95.0)])
        two = from_mapping({"image_path": "front.png", "image_path_2": "back.png",
                            "label_width_mm": "95", "label_width_mm_2": "80"})
        self.assertEqual(two.panels(), [("front.png", 95.0), ("back.png", 80.0)])

    def test_blank_second_image_is_simply_omitted(self):
        record = from_mapping({"image_path": "front.png", "image_path_2": "   "})
        self.assertEqual(len(record.panels()), 1)

    def test_csv_accepts_back_image_column_aliases(self):
        rows, _ = rows_from_csv(
            "image,back_image,brand\nf.png,b.png,Acme\n")
        self.assertEqual(rows[0].image_path, "f.png")
        self.assertEqual(rows[0].image_path_2, "b.png")


class TestApplicationData(unittest.TestCase):
    def test_template_round_trips(self):
        rows, warnings = rows_from_csv(template_csv())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].declared_abv(), 45.0)
        self.assertEqual(rows[0].declared_ml(), 750.0)
        self.assertEqual(warnings, [])

    def test_column_aliases_are_accepted(self):
        rows, _ = rows_from_csv(
            "file,brand,type,abv,volume,producer,address\n"
            "a.png,Acme,Vodka,40% ABV,750 mL,Acme Co,\"Reno, Nevada\"\n")
        self.assertEqual(rows[0].brand_name, "Acme")
        self.assertEqual(rows[0].image_path, "a.png")

    def test_unknown_columns_warn_but_do_not_fail(self):
        _, warnings = rows_from_csv(
            "image,brand,bookkeeping_code\nx.png,Acme,ZZ9\n")
        self.assertTrue(any("bookkeeping_code" in w for w in warnings))

    def test_missing_image_column_is_rejected(self):
        with self.assertRaises(ApplicationDataError):
            rows_from_csv("brand,abv\nAcme,40%\n")

    def test_header_only_is_rejected(self):
        with self.assertRaises(ApplicationDataError):
            rows_from_csv("image,brand\n")

    def test_foreign_origin_implies_import(self):
        record = from_mapping({"country_of_origin": "France"})
        self.assertTrue(record.is_import)

    def test_usa_origin_does_not_imply_import(self):
        self.assertFalse(from_mapping({"country_of_origin": "USA"}).is_import)


class TestSecurity(unittest.TestCase):
    def test_path_traversal_is_refused(self):
        with self.assertRaises(ValueError):
            security.resolve_within(Path("/tmp/base"), "../../etc/passwd")

    def test_absolute_paths_are_confined(self):
        resolved = security.resolve_within(Path("/tmp/base"), "/etc/passwd")
        self.assertTrue(str(resolved).startswith("/tmp/base"))

    def test_csv_formula_injection_is_neutralised(self):
        for payload in ["=cmd|'/c calc'!A1", "+1+1", "-2+3", "@SUM(A1)"]:
            with self.subTest(payload=payload):
                self.assertTrue(security.csv_safe(payload).startswith("'"))

    def test_csv_safe_strips_newlines(self):
        self.assertNotIn("\n", security.csv_safe("a\nb"))

    def test_filenames_are_sanitised_for_display(self):
        self.assertEqual(security.safe_display_name("../../evil name.png"),
                         "evil_name.png")

    def test_suffix_allowlist(self):
        self.assertTrue(security.has_allowed_suffix("label.PNG"))
        self.assertFalse(security.has_allowed_suffix("label.svg"))
        self.assertFalse(security.has_allowed_suffix("label.exe"))


class TestFindings(unittest.TestCase):
    def test_worst_status_wins(self):
        from labelcheck.findings import Finding
        group = [Finding("f", "a", PASS, ""), Finding("f", "b", FAIL, "")]
        self.assertEqual(worst(group), FAIL)


# --- Integration: real OCR over the generated sample labels ----------------
SAMPLES = ROOT / "samples"
LABELS = SAMPLES / "labels"


def tesseract_available() -> bool:
    try:
        from labelcheck.ocr import ensure_available
        ensure_available()
        return True
    except Exception:
        return False


@unittest.skipUnless(tesseract_available(), "Tesseract OCR is not installed")
@unittest.skipUnless(LABELS.is_dir(), "Run samples/make_samples.py first")
class TestEndToEnd(unittest.TestCase):
    """Drives the real engine over labels with known, deliberate defects."""

    @classmethod
    def setUpClass(cls):
        from labelcheck.application import rows_from_csv as parse
        cls.rows = {
            Path(row.image_path).name: row
            for row in parse((SAMPLES / "sample_batch.csv").read_text())[0]
        }

    def _report(self, filename):
        """Check using only the row's first picture."""
        from labelcheck.checker import check_label
        app = self.rows[filename]
        data = (SAMPLES / app.image_path).read_bytes()
        return check_label(data, app, image_name=filename)

    def _titles(self, report):
        return " | ".join(f.title.lower() for f in report.all_findings()
                          if f.status in (FAIL, WARN))

    def test_compliant_label_passes(self):
        report = self._report("01_bourbon_compliant.png")
        self.assertEqual(report.overall, PASS,
                         f"unexpected problems: {self._titles(report)}")

    def test_abv_mismatch_is_caught(self):
        report = self._report("02_wine_abv_mismatch.png")
        self.assertEqual(report.overall, FAIL)
        self.assertIn("alcohol content", self._titles(report))

    def test_undersized_warning_is_caught(self):
        report = self._report("03_beer_tiny_warning.png")
        self.assertEqual(report.overall, FAIL)
        self.assertIn("too small", self._titles(report))

    def test_absent_warning_is_caught(self):
        report = self._report("04_wine_no_warning.png")
        self.assertEqual(report.overall, FAIL)
        self.assertIn("government health warning is missing", self._titles(report))

    def test_missing_country_of_origin_is_caught(self):
        report = self._report("05_imported_gin_no_origin.png")
        self.assertEqual(report.overall, FAIL)
        self.assertIn("country of origin", self._titles(report))

    def test_lowercase_warning_is_advisory_not_failure(self):
        report = self._report("06_cider_lowercase_warning.png")
        house = [f for f in report.all_findings()
                 if "capital letters" in f.title and f.advisory]
        self.assertTrue(house)
        self.assertEqual(house[0].status, WARN)

    def test_low_alcohol_cider_uses_fda_rules(self):
        # 6.9% ABV cider sits outside the FAA Act.
        report = self._report("06_cider_lowercase_warning.png")
        self.assertEqual(report.beverage_class, "fda_regulated")

    def test_single_picture_is_still_checked_on_its_own(self):
        # Supplying one picture must work exactly as before.
        report = self._report("01_bourbon_compliant.png")
        self.assertEqual(report.panel_count, 1)
        self.assertEqual(report.overall, PASS)
        self.assertIsNone(report.warning_panel_label)

    def test_front_panel_alone_is_incomplete(self):
        from labelcheck.checker import Panel, check_label
        app = self.rows["07_whiskey_front.png"]
        front = Panel((SAMPLES / app.image_path).read_bytes(), "front.png",
                      app.label_width_mm)
        report = check_label([front], app)
        titles = " | ".join(f.title.lower() for f in report.all_findings())
        self.assertEqual(report.overall, FAIL)
        self.assertIn("government health warning is missing", titles)

    def test_front_and_back_together_are_compliant(self):
        from labelcheck.checker import Panel, check_label
        app = self.rows["07_whiskey_front.png"]
        panels = [
            Panel((SAMPLES / path).read_bytes(), Path(path).name, width)
            for path, width in app.panels()
        ]
        report = check_label(panels, app)
        self.assertEqual(report.panel_count, 2)
        self.assertEqual(report.overall, PASS,
                         f"unexpected: {self._titles(report)}")
        # The warning lives on the back label, and must be measured there.
        self.assertEqual(report.warning_panel, 1)

    def test_a_broken_second_picture_does_not_lose_the_first(self):
        from labelcheck.checker import Panel, check_label
        app = self.rows["01_bourbon_compliant.png"]
        good = Panel((SAMPLES / app.image_path).read_bytes(), "good.png",
                     app.label_width_mm)
        broken = Panel(b"this is not an image", "broken.png", 95.0)
        report = check_label([good, broken], app)
        self.assertIsNone(report.error)
        self.assertEqual(report.overall, PASS)
        self.assertTrue(any("skipped" in n.lower() for n in report.notes))

    def test_small_print_is_recovered_from_a_dominant_brand(self):
        # A very large brand name makes Tesseract discard much smaller text
        # as noise. The banded pass exists to recover it.
        from labelcheck.ocr import read_label
        result = read_label(
            (SAMPLES / "labels" / "07_whiskey_front.png").read_bytes(),
            label_width_mm=95)
        self.assertIn("43%", result.text)
        self.assertIn("750", result.text)

    def test_read_text_has_no_repeated_lines(self):
        from labelcheck.ocr import read_label
        result = read_label(
            (SAMPLES / "labels" / "01_bourbon_compliant.png").read_bytes(),
            label_width_mm=95)
        lines = [" ".join(l.split()).lower()
                 for l in result.text.splitlines() if l.strip()]
        self.assertEqual(len(lines), len(set(lines)))

    def test_every_label_is_checked_within_the_time_budget(self):
        for filename in self.rows:
            with self.subTest(label=filename):
                started = time.monotonic()
                report = self._report(filename)
                elapsed = time.monotonic() - started
                self.assertLessEqual(
                    elapsed, config.TIME_BUDGET_SECONDS,
                    f"{filename} took {elapsed:.2f}s, over the "
                    f"{config.TIME_BUDGET_SECONDS}s budget")
                self.assertTrue(report.within_budget)


@unittest.skipUnless(tesseract_available(), "Tesseract OCR is not installed")
@unittest.skipUnless(LABELS.is_dir(), "Run samples/make_samples.py first")
class TestBulk(unittest.TestCase):
    def test_batch_runs_every_row(self):
        from labelcheck.bulk import results_csv, run_batch
        summary = run_batch((SAMPLES / "sample_batch.csv").read_text(), SAMPLES)
        self.assertEqual(summary.total, 7)
        self.assertEqual(summary.passed + summary.failed
                         + summary.needs_attention, 7)
        self.assertIn("reference,image", results_csv(summary))

    def test_batch_handles_a_two_picture_row(self):
        from labelcheck.bulk import results_csv, run_batch
        summary = run_batch((SAMPLES / "sample_batch.csv").read_text(), SAMPLES)
        pair = [r for r in summary.reports if r.reference == "SKU-1007"][0]
        self.assertEqual(pair.panel_count, 2)
        self.assertEqual(pair.overall, PASS)
        # Both file names are recorded in the exported results.
        self.assertIn("07_whiskey_back.png", results_csv(summary))

    def test_missing_image_is_reported_not_fatal(self):
        from labelcheck.bulk import run_batch
        summary = run_batch(
            "image,brand_name\nnot_here.png,Acme\n", SAMPLES)
        self.assertEqual(summary.total, 1)
        self.assertIsNotNone(summary.reports[0].error)

    def test_zip_slip_entry_is_skipped(self):
        import io
        import shutil
        import tempfile
        import zipfile
        from labelcheck.bulk import extract_zip
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../escaped.png", b"x")
            archive.writestr("safe.png", b"x")
        destination = Path(tempfile.mkdtemp(prefix="labelcheck-test-"))
        try:
            warnings = extract_zip(buffer.getvalue(), destination)
            self.assertTrue(any("unsafe" in w for w in warnings))
            self.assertTrue((destination / "safe.png").exists())
            self.assertFalse((destination.parent / "escaped.png").exists())
        finally:
            shutil.rmtree(destination, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
