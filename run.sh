#!/usr/bin/env bash
# Start the Alcohol Label Compliance Checker.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v tesseract >/dev/null 2>&1; then
  echo "ERROR: The Tesseract OCR engine is not installed." >&2
  echo "  Ubuntu/Debian:  sudo apt-get install tesseract-ocr" >&2
  echo "  macOS:          brew install tesseract" >&2
  echo "  Windows:        https://github.com/UB-Mannheim/tesseract/wiki" >&2
  exit 1
fi

python3 -c "import flask, PIL, pytesseract" 2>/dev/null || {
  echo "Installing Python packages..." >&2
  python3 -m pip install -r requirements.txt
}

exec python3 app.py
