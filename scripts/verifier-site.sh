#!/usr/bin/env bash
# Génère le site depuis les fixtures et le vérifie dans Chromium headless
# (image Docker Playwright : rien à installer en local à part Docker).
# Usage : scripts/verifier-site.sh [dossier_captures]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/out"; WORK="$(mktemp -d "$ROOT/out/verif.XXXXXX")"
SHOTS="${1:-$ROOT/out/captures}"
PY="${PYTHON:-$ROOT/generator/.venv/bin/python}"
[ -x "$PY" ] || PY=python3
IMAGE="mcr.microsoft.com/playwright/python:v1.55.0-noble"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$SHOTS"
"$PY" "$ROOT/generator/tests/fixtures/make_repos.py" "$WORK/repos" >/dev/null
PYTHONPATH="$ROOT/generator" "$PY" -m scope_gen \
  --local "$WORK/repos" --projects "$ROOT/generator/tests/fixtures/projects" --out "$WORK/site" 2>/dev/null

# Faux endpoint de santé (servi par le même serveur) : un service KO, et des
# versions « en production » pour tester l'affichage dans le panneau.
API_SHA="$(git -C "$WORK/repos/demo-api" rev-parse main)"
cat > "$WORK/site/sante-demo.json" <<JSON
{"status": "degraded",
 "services": {"demo-front": "ok", "demo-api": "unavailable"},
 "versions": {"demo-api": "$API_SHA", "demo-front": "0000000000000000000000000000000000000000"}}
JSON

docker run --rm \
  -v "$WORK/site:/site:ro" -v "$ROOT/generator/e2e:/e2e:ro" -v "$SHOTS:/shots" \
  "$IMAGE" bash -c '
    pip install -q --break-system-packages playwright==1.55.0 2>/dev/null || pip install -q playwright==1.55.0
    cd /site && python3 -m http.server 8080 >/dev/null 2>&1 &
    sleep 1
    python3 /e2e/check_site.py http://localhost:8080 /shots'
echo "Captures : $SHOTS"
