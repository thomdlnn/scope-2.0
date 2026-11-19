#!/usr/bin/env bash
# Vérifie SCOPE dans Chromium headless (image Docker Playwright : rien à
# installer en local à part Docker). Le générateur tourne en boucle sur une
# fausse racine (tests/fixtures/racine.py), avec un faux token et une API
# GitHub simulée (tests/fixtures/github.py) ; le test modifie un rapport et
# vérifie que la page se met à jour seule.
# Usage : scripts/verifier-site.sh [dossier_captures]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SHOTS="${1:-$ROOT/out/captures}"
IMAGE="mcr.microsoft.com/playwright/python:v1.55.0-noble"
mkdir -p "$SHOTS"

docker run --rm \
  -v "$ROOT/generator:/generator:ro" -v "$SHOTS:/shots" \
  "$IMAGE" bash -euc '
    pip install -q --break-system-packages playwright==1.55.0 -r /generator/requirements.txt 2>/dev/null \
      || pip install -q playwright==1.55.0 -r /generator/requirements.txt
    cd /generator
    python3 tests/fixtures/racine.py /tmp/racine >/dev/null
    python3 tests/fixtures/github.py 9999 &
    SCOPE_GH_TOKEN=faux SCOPE_GH_API=http://127.0.0.1:9999 SCOPE_GH_INTERVAL=2 \
      python3 -m scope_gen --racine /tmp/racine --projets tests/fixtures/projects \
        --site /tmp/site --boucle 1 --servir 8080 &
    python3 -c "import time, urllib.request as u
for _ in range(50):
    try: u.urlopen(\"http://127.0.0.1:8080/etat.json\"); break
    except Exception: time.sleep(0.2)"
    python3 e2e/check_site.py http://127.0.0.1:8080 /tmp/racine /shots'
echo "Captures : $SHOTS"
