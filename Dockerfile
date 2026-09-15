# Container image for hosting the checker.
#
# The Tesseract OCR engine is a system package, not a Python one, which is
# the usual reason a naive deployment of this app fails: a plain Python
# buildpack installs the pytesseract wrapper and nothing to wrap. This image
# installs the engine itself, so the deployment works.
FROM python:3.12-slim

# tesseract-ocr is the engine; tesseract-ocr-eng is the English language
# data it needs to read anything.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so edits to the source do not invalidate this layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as an unprivileged user. Nothing here needs root, and the app never
# writes to disk outside the system temporary directory.
# UID 1000 explicitly: Hugging Face Spaces runs containers as that user, and
# pinning it is harmless on every other host.
# Fall back to an automatic UID if 1000 is ever already taken, so the build
# cannot fail on a base-image change.
RUN (useradd --create-home --uid 1000 --shell /usr/sbin/nologin checker \
     || useradd --create-home --shell /usr/sbin/nologin checker) \
    && chown -R checker:checker /app
USER checker
ENV HOME=/home/checker

ENV PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LABELCHECK_BEHIND_PROXY=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,os,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/healthz', timeout=4).status==200 else 1)"

# wsgi.py refuses to start unless LABELCHECK_PASSWORD is set.
CMD ["python", "wsgi.py"]
