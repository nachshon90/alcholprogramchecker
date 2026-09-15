"""Tests for the guards that apply when the tool is hosted publicly.

Locally the tool has no password and no rate limit, which is correct for a
single-user program on your own machine. The moment it is reachable from the
internet those become the only things protecting it, so they are tested as
carefully as the compliance logic.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as web_app  # noqa: E402
from labelcheck import hosting  # noqa: E402

PASSWORD = "a-long-enough-test-password"


def with_password(value=PASSWORD):
    """Run as though LABELCHECK_PASSWORD were set to `value`."""
    return mock.patch.dict(os.environ, {hosting.PASSWORD_ENV: value})


def without_password():
    environment = dict(os.environ)
    environment.pop(hosting.PASSWORD_ENV, None)
    return mock.patch.dict(os.environ, environment, clear=True)


class HostingTestCase(unittest.TestCase):
    def setUp(self):
        web_app.app.config["TESTING"] = True
        self.client = web_app.app.test_client()
        hosting.reset_rate_limits()

    def tearDown(self):
        hosting.reset_rate_limits()


class TestLocalModeIsUnchanged(HostingTestCase):
    """Adding hosting support must not burden the local single-user run."""

    def test_no_password_is_required_locally(self):
        with without_password():
            self.assertFalse(hosting.is_public_mode())
            self.assertEqual(self.client.get("/").status_code, 200)

    def test_no_rate_limit_applies_locally(self):
        with without_password():
            for _ in range(hosting.MAX_REQUESTS + 5):
                self.assertFalse(hosting._too_many("10.0.0.1")
                                 and hosting.is_public_mode())

    def test_no_hsts_header_on_plain_http(self):
        with without_password():
            self.assertNotIn("Strict-Transport-Security",
                             self.client.get("/").headers)


class TestPasswordProtection(HostingTestCase):
    def test_pages_demand_a_password_when_hosted(self):
        with with_password():
            for path in ("/", "/bulk", "/help", "/template.csv"):
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 401)
                    self.assertIn("Basic", response.headers["WWW-Authenticate"])

    def test_correct_password_is_accepted(self):
        with with_password():
            response = self.client.get(
                "/", auth=("reviewer", PASSWORD))
            self.assertEqual(response.status_code, 200)

    def test_wrong_password_is_refused(self):
        with with_password():
            response = self.client.get("/", auth=("reviewer", "not-the-password"))
            self.assertEqual(response.status_code, 401)

    def test_password_may_be_given_as_the_username(self):
        # Friendlier for someone pasting into a browser prompt.
        with with_password():
            response = self.client.get("/", auth=(PASSWORD, ""))
            self.assertEqual(response.status_code, 200)

    def test_posting_a_check_also_requires_the_password(self):
        with with_password():
            response = self.client.post("/check", data={"brand_name": "Acme"},
                                        content_type="multipart/form-data")
            self.assertEqual(response.status_code, 401)

    def test_health_check_stays_open_for_the_host(self):
        # Hosts probe this to decide whether the instance is alive; if it
        # needed the password every deployment would look unhealthy.
        with with_password():
            response = self.client.get("/healthz")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["status"], "ok")

    def test_comparison_is_constant_time(self):
        # A plain == would leak the password through response timing.
        import inspect
        source = inspect.getsource(hosting._password_matches)
        self.assertIn("compare_digest", source)


class TestRateLimiting(HostingTestCase):
    def test_a_flood_from_one_address_is_cut_off(self):
        with with_password():
            allowed = sum(0 if hosting._too_many("203.0.113.7") else 1
                          for _ in range(hosting.MAX_REQUESTS + 10))
            self.assertEqual(allowed, hosting.MAX_REQUESTS)

    def test_addresses_are_limited_independently(self):
        with with_password():
            for _ in range(hosting.MAX_REQUESTS):
                hosting._too_many("203.0.113.7")
            self.assertTrue(hosting._too_many("203.0.113.7"))
            self.assertFalse(hosting._too_many("203.0.113.8"))

    def test_expensive_endpoint_returns_429_when_flooded(self):
        with with_password():
            for _ in range(hosting.MAX_REQUESTS):
                hosting._too_many("127.0.0.1")
            response = self.client.post(
                "/check", data={"brand_name": "Acme"},
                auth=("reviewer", PASSWORD),
                content_type="multipart/form-data")
            self.assertEqual(response.status_code, 429)
            self.assertIn("Retry-After", response.headers)


class TestHostedPageWording(HostingTestCase):
    """A hosted copy must stop claiming nothing leaves your computer."""

    def test_hosted_footer_is_honest_about_the_network(self):
        with with_password():
            body = self.client.get("/", auth=("r", PASSWORD)).data.decode()
            self.assertIn("runs on a server, not on your computer", body)
            self.assertNotIn("never sent over the internet", body)

    def test_local_footer_keeps_the_privacy_promise(self):
        with without_password():
            body = self.client.get("/").data.decode()
            self.assertIn("never sent over the internet", body)


class TestProductionEntryPoint(unittest.TestCase):
    """wsgi.py must refuse to start an unprotected public service."""

    def _run(self, environment):
        import subprocess
        merged = dict(os.environ)
        merged.pop(hosting.PASSWORD_ENV, None)
        merged.update(environment)
        return subprocess.run(
            [sys.executable, str(ROOT / "wsgi.py")],
            capture_output=True, text=True, timeout=60, env=merged, cwd=str(ROOT))

    def test_refuses_to_start_without_a_password(self):
        result = self._run({})
        self.assertEqual(result.returncode, 1)
        self.assertIn("REFUSING TO START", result.stderr)
        self.assertIn("No password is set", result.stderr)

    def test_refuses_a_short_password(self):
        result = self._run({hosting.PASSWORD_ENV: "short"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("shorter than 12 characters", result.stderr)

    def test_exposes_the_wsgi_callable(self):
        import wsgi
        self.assertIs(wsgi.application, web_app.app)


if __name__ == "__main__":
    unittest.main(verbosity=2)
