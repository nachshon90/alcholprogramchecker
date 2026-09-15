"""Alcohol Label Compliance Checker - local web application.

Runs entirely on this computer. There is no cloud service, no database and
no account. Label images and company details are held in memory only for the
few seconds a check takes, and are then discarded.

Start it with:   python3 app.py
Then open:       http://127.0.0.1:5000
"""
import base64
import io
import os
import secrets
import time
from typing import Dict, Optional, Tuple

from flask import Flask, Response, abort, render_template, request, send_file

from labelcheck import bulk, config, security
from labelcheck.application import (
    ApplicationData, ApplicationDataError, from_mapping, template_csv,
)
from labelcheck.checker import check_label
from labelcheck.findings import FAIL, PASS, UNKNOWN, WARN
from labelcheck.ocr import OcrUnavailable, ensure_available, load_image
from labelcheck.rules import class_choices

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_BYTES
# No sessions and no cookies are used anywhere, so there is no session
# secret to leak and no login state to steal.
app.config["JSON_SORT_KEYS"] = False

THUMBNAIL_MAX = 480


# --- Short-lived results store --------------------------------------------
# Batch results are held in memory only, so that the "download results"
# button does not have to re-run the whole batch. Entries expire quickly and
# are removed as soon as they are downloaded. Nothing touches the disk, and
# label images are never kept here - only the results table.
_RESULTS: Dict[str, Tuple[float, str]] = {}
_RESULTS_TTL_SECONDS = 600
_RESULTS_MAX = 20


def _store_results(csv_text: str) -> str:
    _expire_results()
    if len(_RESULTS) >= _RESULTS_MAX:
        oldest = min(_RESULTS, key=lambda key: _RESULTS[key][0])
        _RESULTS.pop(oldest, None)
    token = secrets.token_urlsafe(24)
    _RESULTS[token] = (time.time(), csv_text)
    return token


def _expire_results() -> None:
    cutoff = time.time() - _RESULTS_TTL_SECONDS
    for token in [k for k, (stamp, _) in _RESULTS.items() if stamp < cutoff]:
        _RESULTS.pop(token, None)


@app.after_request
def apply_security_headers(response: Response) -> Response:
    for header, value in security.SECURITY_HEADERS.items():
        response.headers[header] = value
    return response


@app.context_processor
def inject_globals():
    return {
        "beverage_choices": class_choices(),
        "PASS": PASS, "FAIL": FAIL, "WARN": WARN, "UNKNOWN": UNKNOWN,
        "time_budget": config.TIME_BUDGET_SECONDS,
    }


def _thumbnail(image_bytes: bytes) -> Optional[str]:
    """A small copy of the label to show beside the results, as a data URI.

    This is the operator's own image handed straight back to their own
    browser. It is never written to disk or kept after the response.
    """
    try:
        image = load_image(image_bytes)
        image.thumbnail((THUMBNAIL_MAX, THUMBNAIL_MAX))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=72)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return None


def _application_from_form(form) -> ApplicationData:
    mapping = {
        "brand_name": form.get("brand_name", ""),
        "class_type": form.get("class_type", ""),
        "alcohol_content": form.get("alcohol_content", ""),
        "net_contents": form.get("net_contents", ""),
        "bottler_name": form.get("bottler_name", ""),
        "bottler_address": form.get("bottler_address", ""),
        "country_of_origin": form.get("country_of_origin", ""),
        "beverage_class": form.get("beverage_class", ""),
        "reference": form.get("reference", ""),
        "is_import": "yes" if form.get("is_import") else "no",
        "label_width_mm": form.get("label_width_mm", ""),
    }
    sulfites = form.get("contains_sulfites", "")
    if sulfites in ("yes", "no"):
        mapping["contains_sulfites"] = sulfites
    return from_mapping(mapping)


@app.route("/", methods=["GET"])
def index():
    engine_error = None
    try:
        ensure_available()
    except OcrUnavailable as exc:
        engine_error = str(exc)
    return render_template("index.html", form={}, engine_error=engine_error)


@app.route("/check", methods=["POST"])
def check():
    try:
        ensure_available()
    except OcrUnavailable as exc:
        return render_template("index.html", form=request.form,
                               engine_error=str(exc)), 503

    upload = request.files.get("label_image")
    if upload is None or not upload.filename:
        return render_template(
            "index.html", form=request.form,
            error="Please choose a picture of the label to check."), 400

    if not security.has_allowed_suffix(upload.filename):
        return render_template(
            "index.html", form=request.form,
            error="That file type is not accepted. Please use a PNG, JPEG, "
                  "TIFF, BMP, WEBP or GIF picture."), 400

    try:
        image_bytes = security.read_limited(upload.stream)
    except ValueError as exc:
        return render_template("index.html", form=request.form,
                               error=str(exc)), 413

    if not image_bytes:
        return render_template("index.html", form=request.form,
                               error="That file appears to be empty."), 400

    app_data = _application_from_form(request.form)
    display_name = security.safe_display_name(upload.filename)
    report = check_label(image_bytes, app_data, image_name=display_name)

    return render_template(
        "result.html", report=report, app_data=app_data,
        thumbnail=_thumbnail(image_bytes),
    )


@app.route("/bulk", methods=["GET"])
def bulk_form():
    engine_error = None
    try:
        ensure_available()
    except OcrUnavailable as exc:
        engine_error = str(exc)
    return render_template("bulk.html", engine_error=engine_error)


@app.route("/bulk", methods=["POST"])
def bulk_run():
    try:
        ensure_available()
    except OcrUnavailable as exc:
        return render_template("bulk.html", engine_error=str(exc)), 503

    csv_upload = request.files.get("csv_file")
    if csv_upload is None or not csv_upload.filename:
        return render_template(
            "bulk.html", error="Please choose the CSV file listing your labels."), 400

    try:
        csv_bytes = security.read_limited(csv_upload.stream)
    except ValueError as exc:
        return render_template("bulk.html", error=str(exc)), 413

    try:
        csv_text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        csv_text = csv_bytes.decode("latin-1", errors="replace")

    zip_bytes = None
    zip_upload = request.files.get("zip_file")
    if zip_upload is not None and zip_upload.filename:
        try:
            zip_bytes = security.read_limited(zip_upload.stream)
        except ValueError as exc:
            return render_template("bulk.html", error=str(exc)), 413

    folder = (request.form.get("folder") or "").strip()

    try:
        summary = bulk.run_uploaded_batch(csv_text, zip_bytes=zip_bytes,
                                          folder=folder or None)
    except (bulk.BulkError, ApplicationDataError) as exc:
        return render_template("bulk.html", error=str(exc)), 400

    token = _store_results(bulk.results_csv(summary))
    return render_template("bulk_result.html", summary=summary, token=token)


@app.route("/results/<token>.csv")
def download_results(token: str):
    _expire_results()
    entry = _RESULTS.pop(token, None)
    if entry is None:
        abort(404, "Those results have expired. Please run the batch again.")
    _, csv_text = entry
    return send_file(
        io.BytesIO(csv_text.encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="label-check-results.csv",
    )


@app.route("/template.csv")
def download_template():
    return send_file(
        io.BytesIO(template_csv().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="label-check-template.csv",
    )


@app.route("/help")
def help_page():
    return render_template("help.html")


@app.errorhandler(413)
def too_large(_error):
    limit = config.MAX_UPLOAD_BYTES // (1024 * 1024)
    return render_template(
        "index.html", form={},
        error=f"That file is too big. The limit is {limit} MB."), 413


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", message=getattr(
        error, "description", "That page was not found.")), 404


@app.errorhandler(500)
def server_error(_error):
    return render_template("error.html", message=(
        "Something went wrong while checking. Please try again.")), 500


if __name__ == "__main__":
    host = os.environ.get("LABELCHECK_HOST", "127.0.0.1")
    port = int(os.environ.get("LABELCHECK_PORT", "5000"))
    print("=" * 68)
    print("  Alcohol Label Compliance Checker")
    print(f"  Open this address in your web browser:  http://{host}:{port}")
    print("  Everything runs on this computer. Nothing is sent to the internet.")
    print("  Press Ctrl+C to stop.")
    print("=" * 68)
    # debug=False deliberately: the debugger would expose an interactive
    # console on this machine.
    app.run(host=host, port=port, debug=False, threaded=True)
