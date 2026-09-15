"""End-to-end tests for the web interface.

These drive the real Flask application through its test client, which
exercises the routes, the upload handling and every template. Unit tests
cannot catch a broken template or a bad url_for; these do.

Run with:  python3 -m unittest discover -s tests -v
"""
import io
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as web_app  # noqa: E402
from labelcheck import security  # noqa: E402

SAMPLES = ROOT / "samples"
LABELS = SAMPLES / "labels"


def tesseract_available() -> bool:
    try:
        from labelcheck.ocr import ensure_available
        ensure_available()
        return True
    except Exception:
        return False


def image_bytes(name: str) -> bytes:
    return (LABELS / name).read_bytes()


class WebTestCase(unittest.TestCase):
    def setUp(self):
        web_app.app.config["TESTING"] = True
        self.client = web_app.app.test_client()


class TestPagesLoad(WebTestCase):
    """Every page renders. This catches template and routing mistakes."""

    def test_home_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Check one label", response.data)

    def test_bulk_page(self):
        response = self.client.get("/bulk")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Check many labels", response.data)

    def test_help_page(self):
        response = self.client.get("/help")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"GOVERNMENT WARNING", response.data)

    def test_blank_csv_template_downloads(self):
        response = self.client.get("/template.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["Content-Type"])
        self.assertIn(b"image_2", response.data)

    def test_unknown_page_shows_a_friendly_error(self):
        response = self.client.get("/no-such-page")
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Something went wrong", response.data)


class TestSecurityHeaders(WebTestCase):
    def test_every_response_is_locked_down(self):
        headers = self.client.get("/").headers
        for name, expected in security.SECURITY_HEADERS.items():
            with self.subTest(header=name):
                self.assertEqual(headers.get(name), expected)

    def test_results_are_not_cached(self):
        self.assertIn("no-store", self.client.get("/").headers["Cache-Control"])

    def test_no_cookies_are_ever_set(self):
        # There is no session, so there is no session state to steal.
        self.assertNotIn("Set-Cookie", self.client.get("/").headers)


class TestUploadValidation(WebTestCase):
    """Bad input is refused with a plain explanation, not a stack trace."""

    def test_missing_image_is_refused(self):
        response = self.client.post("/check", data={"brand_name": "Acme"},
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"choose a picture", response.data)

    def test_wrong_file_type_is_refused(self):
        response = self.client.post("/check", data={
            "brand_name": "Acme",
            "label_image": (io.BytesIO(b"#!/bin/sh\necho hi"), "script.sh"),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"not a file type the tool accepts", response.data)

    def test_empty_file_is_refused(self):
        response = self.client.post("/check", data={
            "brand_name": "Acme",
            "label_image": (io.BytesIO(b""), "empty.png"),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)

    def test_a_file_that_is_not_really_an_image_is_handled(self):
        # Correct extension, junk content: must report, not crash.
        response = self.client.post("/check", data={
            "brand_name": "Acme",
            "label_image": (io.BytesIO(b"not an image at all"), "fake.png"),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"could not be read as an image", response.data)

    def test_bulk_requires_a_csv(self):
        response = self.client.post("/bulk", data={},
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"choose the CSV file", response.data)

    def test_bulk_rejects_a_csv_with_no_image_column(self):
        response = self.client.post("/bulk", data={
            "csv_file": (io.BytesIO(b"brand,abv\nAcme,40%\n"), "rows.csv"),
            "folder": str(SAMPLES),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"column naming each label image", response.data)


@unittest.skipUnless(tesseract_available(), "Tesseract OCR is not installed")
@unittest.skipUnless(LABELS.is_dir(), "Run samples/make_samples.py first")
class TestCheckingThroughTheWeb(WebTestCase):
    """The real workflow: company details plus artwork, in and out."""

    BOURBON = {
        "brand_name": "Old Bridge",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "alcohol_content": "45% ABV",
        "net_contents": "750 mL",
        "bottler_name": "Old Bridge Distillery",
        "bottler_address": "Frankfort, Kentucky",
        "beverage_class": "distilled_spirits",
        "label_width_mm": "95",
        "reference": "SKU-1001",
    }

    def test_compliant_label_passes(self):
        data = dict(self.BOURBON)
        data["label_image"] = (io.BytesIO(image_bytes("01_bourbon_compliant.png")),
                               "01_bourbon_compliant.png")
        response = self.client.post("/check", data=data,
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PASS - everything matches", response.data)
        self.assertIn(b"SKU-1001", response.data)

    def test_problem_label_is_reported_in_plain_english(self):
        data = {
            "brand_name": "Harbor Light", "class_type": "India Pale Ale",
            "alcohol_content": "6.2% ABV", "net_contents": "12 fl oz",
            "bottler_name": "Harbor Light Brewing Co.",
            "bottler_address": "Portland, Maine",
            "beverage_class": "malt_beverage", "label_width_mm": "90",
            "label_image": (io.BytesIO(image_bytes("03_beer_tiny_warning.png")),
                            "03_beer_tiny_warning.png"),
        }
        response = self.client.post("/check", data=data,
                                    content_type="multipart/form-data")
        self.assertIn(b"PROBLEMS FOUND", response.data)
        self.assertIn(b"letters are too small", response.data)
        self.assertIn(b"27 CFR 16.22", response.data)

    def test_one_picture_is_checked_on_its_own(self):
        data = dict(self.BOURBON)
        data["label_image"] = (io.BytesIO(image_bytes("01_bourbon_compliant.png")),
                               "front.png")
        response = self.client.post("/check", data=data,
                                    content_type="multipart/form-data")
        body = response.data.decode()
        # One picture, so no "which panel" note and a single preview.
        self.assertEqual(body.count("data:image/jpeg;base64"), 1)
        self.assertNotIn("Checked 2 pictures", body)

    def test_two_pictures_are_checked_as_one_container(self):
        data = {
            "brand_name": "Ironwood Bend", "class_type": "Tennessee Whiskey",
            "alcohol_content": "43% ABV", "net_contents": "750 mL",
            "bottler_name": "Ironwood Bend Distilling Co.",
            "bottler_address": "Nashville, Tennessee",
            "beverage_class": "distilled_spirits",
            "label_width_mm": "95", "label_width_mm_2": "95",
            "label_image": (io.BytesIO(image_bytes("07_whiskey_front.png")),
                            "07_whiskey_front.png"),
            "label_image_2": (io.BytesIO(image_bytes("07_whiskey_back.png")),
                              "07_whiskey_back.png"),
        }
        response = self.client.post("/check", data=data,
                                    content_type="multipart/form-data")
        body = response.data.decode()
        self.assertIn("PASS - everything matches", body)
        self.assertIn("Checked 2 pictures together as one container", body)
        # The warning is on the back label, and the page must say so.
        self.assertIn("picture 2 (back)", body)
        self.assertEqual(body.count("data:image/jpeg;base64"), 2)

    def test_the_words_read_from_the_label_are_shown(self):
        data = dict(self.BOURBON)
        data["label_image"] = (io.BytesIO(image_bytes("01_bourbon_compliant.png")),
                               "front.png")
        response = self.client.post("/check", data=data,
                                    content_type="multipart/form-data")
        self.assertIn(b"Show the words the computer read", response.data)


@unittest.skipUnless(tesseract_available(), "Tesseract OCR is not installed")
@unittest.skipUnless(LABELS.is_dir(), "Run samples/make_samples.py first")
class TestBulkThroughTheWeb(WebTestCase):
    @staticmethod
    def zipped_labels() -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for path in sorted(LABELS.glob("*.png")):
                archive.write(path, f"labels/{path.name}")
        return buffer.getvalue()

    def test_batch_from_csv_and_zip(self):
        response = self.client.post("/bulk", data={
            "csv_file": (io.BytesIO((SAMPLES / "sample_batch.csv").read_bytes()),
                         "sample_batch.csv"),
            "zip_file": (io.BytesIO(self.zipped_labels()), "labels.zip"),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn("Results for 7 labels", body)
        self.assertIn("/results/", body)

    def test_results_download_works_once_then_expires(self):
        response = self.client.post("/bulk", data={
            "csv_file": (io.BytesIO((SAMPLES / "sample_batch.csv").read_bytes()),
                         "sample_batch.csv"),
            "folder": str(SAMPLES),
        }, content_type="multipart/form-data")
        body = response.data.decode()
        start = body.index("/results/")
        link = body[start:body.index('"', start)]

        first = self.client.get(link)
        self.assertEqual(first.status_code, 200)
        self.assertIn("text/csv", first.headers["Content-Type"])
        self.assertIn(b"SKU-1001", first.data)

        # Results are deleted on download, so the link cannot be reused.
        self.assertEqual(self.client.get(link).status_code, 404)

    def test_batch_from_a_folder_on_this_computer(self):
        response = self.client.post("/bulk", data={
            "csv_file": (io.BytesIO((SAMPLES / "sample_batch.csv").read_bytes()),
                         "batch.csv"),
            "folder": str(SAMPLES),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"passed", response.data)

    def test_a_missing_folder_is_reported_clearly(self):
        response = self.client.post("/bulk", data={
            "csv_file": (io.BytesIO(b"image,brand\na.png,Acme\n"), "b.csv"),
            "folder": "/no/such/folder/anywhere",
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"could not be found", response.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
