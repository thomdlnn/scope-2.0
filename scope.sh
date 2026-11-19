#!/usr/bin/env bash
# SCOPE — point d'entrée unique.
#
#   ./scope.sh init <projet> <clone>... [--lang en|fr]
#                        installe la consigne et le hook dans vos clones (sans commit)
#   ./scope.sh up        lance SCOPE (Docker Compose) sur http://localhost:8080
#   ./scope.sh down      arrête SCOPE
#   ./scope.sh logs      suit les journaux du générateur
#   ./scope.sh apercu    même page sans Docker (Python seul) sur http://localhost:8000
#
# Réglages (variables d'environnement ou fichier .env) : SCOPE_ROOT (défaut ~/Git),
# SCOPE_DEPTH (4), SCOPE_INTERVAL (3 s), SCOPE_PORT (8080) ; optionnel :
# SCOPE_GH_TOKEN (lecture seule) pour l'état des dépôts GitHub.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/generator/.venv"

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; }

python_env() {
  if [ ! -x "$VENV/bin/python" ]; then
    command -v python3 >/dev/null || { echo "python3 (≥ 3.12) est requis" >&2; exit 1; }
    echo "Installation de l'environnement Python (une seule fois)…" >&2
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q -r "$ROOT/generator/requirements.txt"
  fi
}

compose() {
  local dc
  if docker compose version >/dev/null 2>&1; then dc=(docker compose)
  elif command -v docker-compose >/dev/null; then dc=(docker-compose)
  else
    echo "Docker Compose est requis (plugin « docker compose » ou docker-compose)," >&2
    echo "ou lancez SCOPE sans Docker : ./scope.sh apercu" >&2
    exit 1
  fi
  SCOPE_UID="$(id -u)" SCOPE_GID="$(id -g)" "${dc[@]}" --project-directory "$ROOT" -f "$ROOT/docker-compose.yml" "$@"
}

# Lit une variable de .env si elle n'est pas déjà définie.
from_env_file() {
  local name="$1" line
  [ -n "${!name:-}" ] && return 0
  [ -f "$ROOT/.env" ] || return 0
  line="$(grep -E "^${name}=" "$ROOT/.env" | tail -n 1 || true)"
  [ -n "$line" ] && export "$name=${line#*=}"
  return 0
}

cmd="${1:-help}"
[ $# -gt 0 ] && shift
case "$cmd" in
  init)
    python_env
    PYTHONPATH="$ROOT/generator" exec "$VENV/bin/python" -m scope_gen.admin "$@"
    ;;
  up)
    compose up -d --build "$@"
    from_env_file SCOPE_PORT
    from_env_file SCOPE_ROOT
    echo "SCOPE lit ${SCOPE_ROOT:-$HOME/Git} : http://localhost:${SCOPE_PORT:-8080}"
    ;;
  down)
    compose down "$@"
    ;;
  logs)
    compose logs -f generator "$@"
    ;;
  apercu)
    python_env
    for v in SCOPE_ROOT SCOPE_DEPTH SCOPE_INTERVAL SCOPE_GH_TOKEN SCOPE_GH_INTERVAL; do from_env_file "$v"; done
    export SCOPE_ROOT="${SCOPE_ROOT:-$HOME/Git}"
    PYTHONPATH="$ROOT/generator" exec "$VENV/bin/python" -m scope_gen \
      --site "$ROOT/out/apercu" --boucle --servir "${SCOPE_APERCU_PORT:-8000}" "$@"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "commande inconnue : $cmd" >&2
    usage >&2
    exit 2
    ;;
esac
