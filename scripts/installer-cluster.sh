#!/usr/bin/env bash
# Installe SCOPE sur le cluster Kubernetes courant (kubectl) via ArgoCD.
#
# Usage : scripts/installer-cluster.sh
#
# Le token GitHub (fine-grained, Contents: read sur le dépôt SCOPE) est
# demandé de façon masquée, ou lu dans la variable SCOPE_READ_TOKEN. Il sert à
# git-sync (Secret scope/scope-git-credentials) et à ArgoCD (Secret
# argocd/repo-scope). Le script est idempotent : relancez-le pour changer de
# token.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/deploy/argocd/application.yaml"

REPO_URL="$(sed -nE 's/^[[:space:]]*repoURL:[[:space:]]*([^[:space:]#]+).*$/\1/p' "$APP" | head -1)"
if printf '%s' "$REPO_URL" | grep -q 'OWNER/REPO' || kubectl kustomize "$ROOT/deploy/k8s" | grep -q 'OWNER/REPO'; then
  echo "Adaptez d'abord l'URL de votre dépôt (OWNER/REPO) dans deploy/argocd/application.yaml" >&2
  echo "et dans le bloc patches de deploy/k8s/kustomization.yaml." >&2
  exit 1
fi
OWNER="$(printf '%s' "$REPO_URL" | sed -E 's#https://github.com/([^/]+)/.*#\1#')"
REPO="$(printf '%s' "$REPO_URL" | sed -E 's#https://github.com/([^/]+/[^/.]+)(\.git)?$#\1#')"
HOST="$(kubectl kustomize "$ROOT/deploy/k8s" | sed -nE 's/^[[:space:]]*- host:[[:space:]]*(.+)$/\1/p' | head -1)"

echo "Contexte kubectl : $(kubectl config current-context)"
echo "Dépôt            : $REPO_URL"
echo "Hôte             : $HOST"
kubectl get namespace argocd >/dev/null || { echo "ArgoCD introuvable (namespace argocd)" >&2; exit 1; }

TOKEN="${SCOPE_READ_TOKEN:-}"
if [ -z "$TOKEN" ]; then
  read -rsp "Token GitHub en lecture sur $REPO (non affiché) : " TOKEN
  echo
fi
[ -n "$TOKEN" ] || { echo "token vide" >&2; exit 1; }

# Vérifie que le token lit bien la branche publiée.
code="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" \
  "https://api.github.com/repos/$REPO/branches/scope-site")"
case "$code" in
  200) echo "✔ token valide, branche scope-site présente" ;;
  404) echo "⚠ branche scope-site absente (ou token sans accès) : lancez « gh workflow run build-site -R $REPO »" ;;
  *)   echo "✘ le token ne permet pas de lire $REPO (HTTP $code)" >&2; exit 1 ;;
esac

apply_secret() { kubectl create secret generic "$@" --dry-run=client -o yaml | kubectl apply -f - >/dev/null; }

kubectl create namespace scope --dry-run=client -o yaml | kubectl apply -f - >/dev/null
apply_secret scope-git-credentials -n scope \
  --from-literal=username="$OWNER" --from-literal=password="$TOKEN"
echo "✔ Secret scope/scope-git-credentials"

apply_secret repo-scope -n argocd \
  --from-literal=type=git --from-literal=url="$REPO_URL" \
  --from-literal=username="$OWNER" --from-literal=password="$TOKEN"
kubectl label secret repo-scope -n argocd argocd.argoproj.io/secret-type=repository --overwrite >/dev/null
echo "✔ Secret argocd/repo-scope (accès ArgoCD au dépôt)"

kubectl apply -f "$APP" >/dev/null
echo "✔ Application ArgoCD « scope » appliquée"

# Un changement de token doit être relu par git-sync.
if kubectl -n scope get deploy scope >/dev/null 2>&1; then
  kubectl -n scope rollout restart deploy/scope >/dev/null
fi

echo "… attente du déploiement (ArgoCD puis git-sync), 3 min max"
for _ in $(seq 1 36); do
  if kubectl -n scope rollout status deploy/scope --timeout=5s >/dev/null 2>&1; then
    echo "✔ SCOPE est prêt"
    break
  fi
  sleep 5
done
kubectl -n scope get pods

if ! grep -qE "[[:space:]]$HOST([[:space:]]|$)" /etc/hosts; then
  echo
  echo "Ajoutez le nom d'hôte : echo \"127.0.0.1 $HOST\" | sudo tee -a /etc/hosts"
fi
echo "Page : http://$HOST/"
