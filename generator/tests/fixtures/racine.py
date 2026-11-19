"""Fausse racine SCOPE_ROOT : dépôts, rapports (FR, EN, ancien format, cassés).

Les dates sont relatives à `maintenant`, pour tester « 7 derniers jours » et
« sans nouvelles ».

    python tests/fixtures/racine.py DOSSIER   # crée la racine dans DOSSIER
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def nom(dt: datetime, slug: str) -> str:
    return dt.strftime("%Y-%m-%d-%H%M%S-") + slug + ".md"


def depot(racine: Path, rel: str, branche: str = "main", projet: str | None = None, origin: str | None = None) -> Path:
    d = racine / rel
    (d / ".git").mkdir(parents=True, exist_ok=True)
    (d / ".git" / "HEAD").write_text(f"ref: refs/heads/{branche}\n")
    if origin:
        (d / ".git" / "config").write_text(
            '[core]\n\tbare = false\n[remote "upstream"]\n\turl = git@github.com:autre/fork.git\n'
            f'[remote "origin"]\n\turl = {origin}\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n'
        )
    (d / ".scope" / "rapports").mkdir(parents=True, exist_ok=True)
    if projet:
        (d / ".scope" / "projet").write_text(projet + "\n")
    return d


def rapport(d: Path, debut: datetime, slug: str, texte: str) -> Path:
    f = d / ".scope" / "rapports" / nom(debut, slug)
    f.write_text(texte, encoding="utf-8")
    return f


def construire(racine: Path, maintenant: datetime | None = None) -> Path:
    t = maintenant or datetime.now(timezone.utc).replace(microsecond=0)
    front = depot(racine, "demo/demo-front", "feat/login-google", projet="demo", origin="git@github.com:acme/demo-front.git")
    # Identifiants dans l'URL : jamais affichés.
    api = depot(racine, "demo/demo-api", "main", projet="demo", origin="https://x-access-token:SECRET@github.com/acme/demo-api")
    depot(racine, "perso/notes")  # dépôt sans SCOPE : n'apparaît pas
    depot(racine, "demo/node_modules/paquet")  # ignoré
    depot(racine, "a/b/c/d/trop-profond")  # au-delà de la profondeur

    # Nouveau format, français, en attente (question + remarque).
    d = t - timedelta(minutes=12)
    rapport(front, d, "login-google", f"""---
projet: demo
repo: demo-front
agent: claude-code
branche: feat/login-google
demande: "Page de login avec authentification Google"
statut: attente
actions: [code, commit]
debut: {iso(d)}
maj: {iso(t - timedelta(minutes=2))}
---

## Résumé
Page de login codée, il manque l'identifiant client Google.

## Pour vous
- Question : quel Client ID Google dois-je utiliser ?
- Remarque : déclarez `http://localhost:3000/auth/callback` dans la console Google.

## Détail
- `src/pages/Login.tsx` créé
- Test : `npm test` vert. <script>alert(1)</script>
""")

    # Nouveau format, anglais, en cours.
    d = t - timedelta(minutes=5)
    rapport(api, d, "rate-limit", f"""---
project: demo
repo: demo-api
agent: codex
branch: feat/rate-limit
request: "Add rate limiting to the public API"
status: in-progress
actions: [code]
started: {iso(d)}
updated: {iso(t - timedelta(minutes=1))}
---

## Summary
Middleware written, tests running.

## For you
- Note: the limit is 100 requests per minute per IP.

## Details
Added `middleware/ratelimit.py`.
""")

    # En cours mais silencieuse depuis 3 h.
    d = t - timedelta(hours=3)
    rapport(api, d, "migration", f"""---
projet: demo
agent: cursor
demande: "Migration de la base"
statut: en-cours
actions: [code]
debut: {iso(d)}
maj: {iso(d)}
---

## Résumé
Migration commencée.
""")

    # Terminée hier, avec PR et déploiement.
    d = t - timedelta(days=1)
    rapport(front, d, "header", f"""---
projet: demo
agent: claude-code
demande: "Ajoute un en-tête"
statut: termine
actions: [code, commit, push, pr, deploy]
debut: {iso(d)}
maj: {iso(d + timedelta(minutes=20))}
pr: 42
---

## Résumé
En-tête ajouté et déployé.
""")

    # Échec il y a 2 jours.
    d = t - timedelta(days=2)
    rapport(api, d, "build", f"""---
projet: demo
agent: copilot
demande: "Corrige le build"
statut: echec
debut: {iso(d)}
---

## Résumé
Le build échoue toujours : dépendance introuvable.
""")

    # Terminée il y a 10 jours : hors des 7 derniers jours.
    d = t - timedelta(days=10)
    rapport(front, d, "init", f"""---
projet: demo
statut: termine
debut: {iso(d)}
---

## Résumé
Initialisation du front.
""")

    # Ancien format : un `bloque` levé par un rapport plus récent, et un `bloque` actuel.
    d = t - timedelta(days=3)
    rapport(api, d, "ancien-bloque", f"""---
date: {iso(d)}
projet: demo
repo: demo-api
agent: claude-code
branche: main
statut: bloque
---

## Résumé court
Il faut un token.

## Prochaine étape
Ajoutez le token dans .env.
""")
    d = t - timedelta(days=2, hours=1)
    rapport(api, d, "ancien-pr", f"""---
date: {iso(d)}
projet: demo
repo: demo-api
agent: claude-code
branche: main
statut: pr-ouverte
pr_numero: 7
---

## Résumé court
PR ouverte pour le token.
""")
    autre = depot(racine, "outils/scope-cli", "develop")
    d = t - timedelta(hours=6)
    rapport(autre, d, "question-ancienne", f"""---
date: {iso(d)}
projet: outils
repo: scope-cli
agent: claude-code
statut: bloque
---

## Résumé court
Quel nom pour la commande ?

## Prochaine étape
Choisissez entre `scope` et `sc`.
""")

    # Rapports illisibles.
    rapport(front, t - timedelta(hours=1), "yaml-casse", "---\nstatut: [termine\n---\n\n## Résumé\nx\n")
    rapport(front, t - timedelta(hours=2), "sans-resume", "---\nstatut: termine\n---\n\nPas de section.\n")
    return racine


if __name__ == "__main__":
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else "racine")
    construire(dest)
    print(dest)
