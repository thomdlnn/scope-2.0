#!/usr/bin/env bash
# SCOPE — point d'entrée unique.
#
#   ./scope.sh init <projet>      ajoute un projet : 1 token en lecture, choix des dépôts,
#                                 consigne IA déposée dans chaque dépôt (PR)
#                                 (--env : mode Docker Compose, token dans .env)
#   ./scope.sh consigne <projet>  redépose / met à jour la consigne IA d'un projet
#   ./scope.sh up | down | logs   démarre / arrête SCOPE en local (Docker Compose)
#   ./scope.sh refresh            régénère la page maintenant (sinon : toutes les 15 min)
#   ./scope.sh apercu             génère la page une fois et la sert sur http://localhost:8000
#   ./scope.sh cluster            installe SCOPE sur le cluster Kubernetes courant (ArgoCD)
#
# Options : ./scope.sh <commande> --help
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/generator/.venv"
cd "$ROOT"

usage() { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; }

python_env() {
  if [ ! -x "$VENV/bin/python" ]; then
    command -v python3 >/dev/null || { echo "python3 (≥ 3.12) est requis" >&2; exit 1; }
    echo "Installation de l'environnement Python (une seule fois)…" >&2
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q -r "$ROOT/generator/requirements.txt"
  fi
}

need_gh() {
  command -v gh >/dev/null || { echo "gh (GitHub CLI) est requis : https://cli.github.com" >&2; exit 1; }
  gh auth status >/dev/null 2>&1 || { echo "connectez gh d'abord : gh auth login" >&2; exit 1; }
}

compose() {
  if docker compose version >/dev/null 2>&1; then docker compose "$@"
  elif command -v docker-compose >/dev/null; then docker-compose "$@"
  else echo "Docker Compose est requis : https://docs.docker.com/compose/install/" >&2; exit 1
  fi
}

compose_running() {
  command -v docker >/dev/null || return 1
  [ -n "$(compose ps -q --status running generator 2>/dev/null)" ]
}

cmd="${1:-help}"
[ $# -gt 0 ] && shift
case "$cmd" in
  init|consigne)
    python_env
    need_gh
    PYTHONPATH="$ROOT/generator" exec "$VENV/bin/python" -m scope_gen.admin "$cmd" "$@"
    ;;
  up)
    [ -f .env ] || { cp .env.example .env; chmod 600 .env; echo "→ .env créé depuis .env.example : renseignez SCOPE_GH_TOKEN (ou lancez ./scope.sh init <projet> --env)"; }
    compose up -d --build "$@"
    echo "SCOPE : http://localhost:$(sed -n 's/^SCOPE_PORT=//p' .env | tail -1 | grep . || echo 8080)"
    ;;
  down) compose down "$@" ;;
  logs) compose logs -f generator "$@" ;;
  refresh)
    if compose_running; then
      compose restart generator >/dev/null
      echo "✔ régénération lancée (conteneur generator) : rechargez la page dans quelques secondes"
    else
      python_env
      need_gh
      PYTHONPATH="$ROOT/generator" exec "$VENV/bin/python" -m scope_gen.admin refresh "$@"
    fi
    ;;
  apercu)
    python_env
    if [ -z "${SCOPE_GH_TOKEN:-}" ]; then
      read -rsp "Token GitHub en lecture (non affiché) : " SCOPE_GH_TOKEN; echo
      export SCOPE_GH_TOKEN
    fi
    PYTHONPATH="$ROOT/generator" "$VENV/bin/python" -m scope_gen --projects "$ROOT/projects" --out "$ROOT/out/apercu" "$@"
    echo "Aperçu : http://localhost:8000  (Ctrl+C pour arrêter)"
    exec "$VENV/bin/python" -m http.server -d "$ROOT/out/apercu" 8000
    ;;
  cluster) exec "$ROOT/scripts/installer-cluster.sh" "$@" ;;
  help|-h|--help) usage ;;
  *) echo "commande inconnue : $cmd" >&2; usage >&2; exit 2 ;;
esac
