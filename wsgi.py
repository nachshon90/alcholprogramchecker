"""Production entry point for a hosted deployment.

Use this instead of `python3 app.py` when the tool is reachable from the
internet. It differs from the local entry point in three ways that matter:

  1. It refuses to start without a password. An open, unauthenticated OCR
     endpoint on the public internet is not something to leave running by
     accident, so this fails loudly rather than starting insecurely.
  2. It serves through Waitress, a production WSGI server, instead of the
     Flask development server.
  3. It binds to every interface on the port the host assigns.

IMPORTANT - run ONE process. Batch results are held in this process's memory
for ten minutes so the download button does not have to re-run the whole
batch. With several worker processes a download would often land on a worker
that has never seen those results and would 404. Waitress serves concurrent
requests with threads inside a single process, which is exactly what this
design needs. Do not put it behind a multi-worker gunicorn.
"""
import os
import sys
from typing import NoReturn

from app import app
from labelcheck import hosting
from labelcheck.ocr import OcrUnavailable, ensure_available

# Expose the WSGI callable under the conventional name, so a host that wants
# to import `wsgi:application` itself can do so.
application = app


def _fail(message: str) -> NoReturn:
    print(f"\nREFUSING TO START: {message}\n", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if not hosting.is_public_mode():
        _fail(
            "No password is set, so this would be an open OCR service on the\n"
            "public internet. Set one before starting:\n\n"
            "    export LABELCHECK_PASSWORD='choose-a-long-random-password'\n\n"
            "To run privately on your own machine instead, use:\n\n"
            "    python3 app.py\n"
        )

    if len(hosting.configured_password()) < 12:
        _fail(
            f"The password in {hosting.PASSWORD_ENV} is shorter than 12 "
            "characters.\nThis is the only thing standing between the public "
            "internet and\nthis service. Please choose a longer one."
        )

    try:
        version = ensure_available()
    except OcrUnavailable as exc:
        _fail(
            "The Tesseract OCR engine is not installed in this environment, "
            "so\nevery check would fail. Use the supplied Dockerfile, which "
            "installs it.\n\n"
            f"{exc}"
        )

    try:
        from waitress import serve
    except ImportError:
        _fail(
            "The 'waitress' package is not installed. Run:\n\n"
            "    pip install -r requirements.txt\n"
        )

    port = int(os.environ.get("PORT", "8080"))
    threads = int(os.environ.get("LABELCHECK_THREADS", "4"))

    print("=" * 70)
    print("  Alcohol Label Compliance Checker - hosted mode")
    print(f"  Tesseract {version}")
    print(f"  Listening on 0.0.0.0:{port} with {threads} threads")
    print("  Password protection is ON.")
    print("  Label pictures are processed in memory and never written to disk.")
    print("=" * 70)

    serve(app, host="0.0.0.0", port=port, threads=threads,
          # Refuse oversized bodies at the server, before Flask sees them.
          max_request_body_size=config_max_body(),
          ident="label-checker")


def config_max_body() -> int:
    from labelcheck import config
    # A batch ZIP is the largest thing anyone legitimately sends.
    return max(config.MAX_UPLOAD_BYTES, 64 * 1024 * 1024)


if __name__ == "__main__":
    main()
