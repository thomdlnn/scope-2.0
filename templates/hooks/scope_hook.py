#!/usr/bin/env python3
"""Hook Claude Code de SCOPE (installé par `./scope.sh init` dans .scope/hooks/).

  scope_hook.py debut [--lang en|fr]   UserPromptSubmit : note l'état du dépôt
  scope_hook.py fin   [--lang en|fr]   Stop : si des fichiers du dépôt ont changé
                                       pendant le tour et qu'aucun rapport n'a été
                                       créé ou mis à jour, bloque une fois avec
                                       un rappel.

Ne bloque jamais deux fois de suite (`stop_hook_active`), ne lève jamais
d'erreur : en cas de doute, il laisse passer.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RAPPEL = {
    "fr": (
        "SCOPE : des fichiers du dépôt ont changé pendant ce tour, mais aucun rapport n'a été "
        "créé ni mis à jour dans .scope/rapports/. Crée ou mets à jour le rapport de cette demande "
        "(statut, actions, maj, « Pour vous » si tu attends quelque chose), sans le commiter, puis rends la main."
    ),
    "en": (
        "SCOPE: repository files changed during this turn, but no report was created or updated "
        "in .scope/rapports/. Create or update the report for this request (status, actions, "
        "updated, 'For you' if you are waiting for something), do not commit it, then hand over."
    ),
}
GARDE = 2 * 24 * 3600  # les fichiers d'état plus vieux sont supprimés


def git(depot: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(depot), *args], capture_output=True, text=True, check=True, timeout=20
    ).stdout


def etat_depot(depot: Path) -> str:
    """Empreinte de l'arbre de travail : HEAD, fichiers modifiés ou nouveaux,
    avec leur taille et leur date (.scope/ est exclu de git, donc ignoré)."""
    h = hashlib.sha256()
    try:
        h.update(git(depot, "rev-parse", "HEAD").encode())
    except (subprocess.SubprocessError, OSError):
        h.update(b"-")
    sortie = git(depot, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    for entree in sorted(filter(None, sortie.split("\0"))):
        h.update(entree.encode())
        chemin = depot / entree[3:]
        try:
            st = chemin.stat()
            h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
        except OSError:
            h.update(b"absent")
    return h.hexdigest()


def rapport_touche(depot: Path, depuis: float) -> bool:
    dossier = depot / ".scope" / "rapports"
    try:
        return any(p.stat().st_mtime >= depuis for p in dossier.glob("*.md"))
    except OSError:
        return False


def main(argv: list[str]) -> int:
    phase = argv[1] if len(argv) > 1 else ""
    lang = argv[argv.index("--lang") + 1] if "--lang" in argv[:-1] else "en"
    try:
        entree = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        entree = {}
    base = Path(os.environ.get("CLAUDE_PROJECT_DIR") or entree.get("cwd") or ".")
    try:
        depot = Path(git(base, "rev-parse", "--show-toplevel").strip())
    except (subprocess.SubprocessError, OSError):
        return 0
    session = "".join(c for c in str(entree.get("session_id") or "session") if c.isalnum() or c in "-_")[:64]
    dossier = depot / ".scope" / "hooks"
    fichier = dossier / f".tour-{session}.json"

    if phase == "debut":
        dossier.mkdir(parents=True, exist_ok=True)
        maintenant = time.time()
        for vieux in dossier.glob(".tour-*.json"):
            try:
                if maintenant - vieux.stat().st_mtime > GARDE:
                    vieux.unlink()
            except OSError:
                pass
        fichier.write_text(json.dumps({"debut": maintenant, "etat": etat_depot(depot)}), encoding="utf-8")
        return 0

    if phase == "fin":
        if entree.get("stop_hook_active"):
            return 0
        try:
            tour = json.loads(fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0  # début du tour inconnu : on ne juge pas
        if etat_depot(depot) == tour.get("etat"):
            return 0
        if rapport_touche(depot, float(tour.get("debut") or 0) - 1):
            return 0
        print(json.dumps({"decision": "block", "reason": RAPPEL.get(lang, RAPPEL["en"])}, ensure_ascii=False))
        return 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception:  # un hook ne doit jamais gêner l'agent
        sys.exit(0)
