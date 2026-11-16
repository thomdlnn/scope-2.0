#!/bin/sh
# Génère le site dans /site/build-<horodatage>, puis bascule /site/current dessus
# de façon atomique : nginx ne sert jamais une page à moitié écrite.
#   loop  (défaut) : génère maintenant, puis toutes les $SCOPE_INTERVAL secondes
#   once           : génère une seule fois
set -eu

SITE=/site
PROJECTS="${SCOPE_PROJECTS_DIR:-/projects}"

generate() {
  build="build-$(date -u +%Y%m%d%H%M%S)"
  set -- --projects "$PROJECTS" --out "$SITE/$build"
  if [ -n "${SCOPE_LOCAL_DIR:-}" ]; then set -- "$@" --local "$SCOPE_LOCAL_DIR"; fi
  if python -m scope_gen "$@"; then
    ln -sfn "$build" "$SITE/.current.tmp"
    mv -T "$SITE/.current.tmp" "$SITE/current"
    find "$SITE" -mindepth 1 -maxdepth 1 -type d -name 'build-*' ! -name "$build" -exec rm -rf {} +
  else
    echo "génération en échec : la version précédente reste en ligne" >&2
    rm -rf "${SITE:?}/$build"
  fi
}

case "${1:-loop}" in
  once) generate ;;
  loop)
    trap 'exit 0' TERM INT
    while :; do
      generate
      sleep "$SCOPE_INTERVAL" &
      wait $!
    done
    ;;
  *) exec "$@" ;;
esac
