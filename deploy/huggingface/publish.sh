#!/usr/bin/env bash
#
# Publish this application to a Hugging Face Space (free Docker hosting).
#
#   ./deploy/huggingface/publish.sh <hf-username> [space-name]
#
# Before the first run:
#   1. Create the Space at https://huggingface.co/new-space
#        SDK: Docker        Template: Blank
#   2. In the Space's Settings, add a secret:
#        LABELCHECK_PASSWORD = <a long random password>
#      The app refuses to start without it, so this is not optional.
#   3. Authenticate git for huggingface.co, either with
#        pip install huggingface_hub && huggingface-cli login
#      or by pasting an access token when git asks for a password.
#
# The script never stores or echoes your password or token.
set -euo pipefail

USERNAME="${1:-}"
SPACE="${2:-alcohol-label-checker}"

if [ -z "$USERNAME" ]; then
  echo "usage: $0 <hf-username> [space-name]" >&2
  exit 1
fi

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
REMOTE="https://huggingface.co/spaces/${USERNAME}/${SPACE}"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

echo "Staging the application..."
# Export the committed tree, so nothing untracked or ignored is published.
git -C "$REPO_ROOT" archive HEAD | tar -x -C "$STAGING"

# A Space is configured by the YAML header of its own README, which replaces
# the project README in the published copy.
mv "$STAGING/deploy/huggingface/SPACE_README.md" "$STAGING/README.md"
rm -rf "$STAGING/deploy" "$STAGING/.github" "$STAGING/render.yaml"

cd "$STAGING"
git init -q
git checkout -q -b main
git add -A
git -c user.name="deploy" -c user.email="deploy@example.com" \
    commit -q -m "Deploy alcohol label compliance checker"

echo "Pushing to ${REMOTE}"
echo "(git will ask for your Hugging Face username and an access token)"
git remote add space "$REMOTE"
git push -f space main

cat <<EOF

Done. The Space is building. It will be available at:

    https://${USERNAME}-${SPACE}.hf.space

The first build takes a few minutes while Tesseract is installed.

If the Space shows an error, check its Logs tab. The most common cause is a
missing LABELCHECK_PASSWORD secret - the app deliberately refuses to start
without one rather than exposing an open OCR service.
EOF
