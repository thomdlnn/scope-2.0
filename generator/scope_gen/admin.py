"""`./scope.sh init <projet> <dossier-du-clone>... [--lang en|fr]`

Installe SCOPE dans des clones locaux, sans token, sans `gh`, sans commit :
  1. bloc de consigne (entre <!-- scope:start --> et <!-- scope:end -->) dans
     CLAUDE.md et AGENTS.md, ajouté ou mis à jour ;
  2. `.scope/` et `.claude/settings.local.json` ajoutés à .git/info/exclude :
     les rapports ne sont jamais commités ;
  3. `.scope/projet` : nom du projet, pour regrouper le dépôt même sans rapport ;
  4. hook Claude Code (.scope/hooks/scope_hook.py) déclaré dans
     .claude/settings.local.json : rappel si un tour modifie le dépôt sans
     mettre à jour de rapport.
Tout est idempotent : relancer la commande met à jour sans dupliquer.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
START, END = "<!-- scope:start -->", "<!-- scope:end -->"
BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
INSTRUCTION_FILES = ("CLAUDE.md", "AGENTS.md")
EXCLUDES = (".scope/", ".claude/settings.local.json")
HOOK_REL = ".scope/hooks/scope_hook.py"
LANGS = ("en", "fr")


class AdminError(RuntimeError):
    pass


def say(msg: str = "") -> None:
    print(msg, flush=True)


# --- Consigne -----------------------------------------------------------------------
def consigne(projet: str, lang: str = "en", root: Path = ROOT) -> str:
    return (root / "templates" / f"instructions-ia.{lang}.md").read_text(encoding="utf-8").replace("{{PROJET}}", projet)


def upsert_block(target: Path, block: str) -> str:
    """Insère ou remplace le bloc SCOPE (entre les marqueurs). Idempotent.
    Renvoie « créé », « ajouté », « remplacé » ou « inchangé »."""
    block = block.strip()
    if START not in block or END not in block:
        raise AdminError(f"le bloc doit être entouré de {START} et {END}")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(block + "\n", encoding="utf-8")
        return "créé"
    text = target.read_text(encoding="utf-8")
    if BLOCK_RE.search(text):
        new = BLOCK_RE.sub(lambda _: block, text, count=1)
        if new == text:
            return "inchangé"
        target.write_text(new, encoding="utf-8")
        return "remplacé"
    if not text or text.endswith("\n\n"):
        sep = ""
    elif text.endswith("\n"):
        sep = "\n"
    else:
        sep = "\n\n"
    target.write_text(text + sep + block + "\n", encoding="utf-8")
    return "ajouté"


# --- Git --------------------------------------------------------------------------------
def git_path(clone: Path, path: str) -> Path:
    """Chemin d'un fichier du dossier git (gère les worktrees)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "--git-path", path],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError) as exc:
        raise AdminError(f"{clone} : pas un dépôt git ({exc})") from None
    p = Path(out)
    return p if p.is_absolute() else clone / p


def exclure(clone: Path, motifs=EXCLUDES) -> list[str]:
    """Ajoute les motifs absents à .git/info/exclude. Renvoie ceux ajoutés."""
    f = git_path(clone, "info/exclude")
    text = f.read_text(encoding="utf-8") if f.exists() else ""
    lignes = {line.strip() for line in text.splitlines()}
    ajout = [m for m in motifs if m not in lignes]
    if ajout:
        f.parent.mkdir(parents=True, exist_ok=True)
        sep = "" if not text or text.endswith("\n") else "\n"
        f.write_text(text + sep + "# SCOPE : rapports locaux, jamais commités\n" + "\n".join(ajout) + "\n", encoding="utf-8")
    return ajout


def rapports_suivis(clone: Path) -> int:
    """Nombre de rapports encore suivis par git (ancien fonctionnement)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(clone), "ls-files", ".scope"], capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, OSError):
        return 0
    return sum(1 for line in out.splitlines() if line.endswith(".md"))


# --- Hook Claude Code --------------------------------------------------------------------
def hook_commands(lang: str) -> dict[str, str]:
    base = f'python3 "$CLAUDE_PROJECT_DIR/{HOOK_REL}"'
    return {"UserPromptSubmit": f"{base} debut --lang {lang}", "Stop": f"{base} fin --lang {lang}"}


def installer_hook(clone: Path, lang: str, root: Path = ROOT) -> str:
    """Copie le script et déclare les deux hooks dans .claude/settings.local.json,
    en conservant les réglages existants. Renvoie « ajouté », « mis à jour » ou « inchangé »."""
    dest = clone / HOOK_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = (root / "templates" / "hooks" / "scope_hook.py").read_bytes()
    script_change = not dest.exists() or dest.read_bytes() != src
    if script_change:
        dest.write_bytes(src)
        dest.chmod(0o755)

    f = clone / ".claude" / "settings.local.json"
    try:
        settings = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except ValueError as exc:
        raise AdminError(f"{f} : JSON invalide ({exc}), corrigez-le puis relancez") from None
    if not isinstance(settings, dict):
        raise AdminError(f"{f} : un objet JSON est attendu")
    avant = json.dumps(settings, sort_keys=True)
    hooks = settings.setdefault("hooks", {})
    for event, command in hook_commands(lang).items():
        groupes = [
            g for g in hooks.get(event, [])
            if not any(HOOK_REL in str(h.get("command", "")) for h in g.get("hooks", []) if isinstance(h, dict))
        ]
        groupes.append({"hooks": [{"type": "command", "command": command, "timeout": 30}]})
        hooks[event] = groupes
    if json.dumps(settings, sort_keys=True) == avant:
        return "mis à jour" if script_change else "inchangé"
    f.parent.mkdir(parents=True, exist_ok=True)
    existait = f.exists()
    f.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return "mis à jour" if existait else "ajouté"


# --- init -------------------------------------------------------------------------------
def init_clone(clone: Path, projet: str, lang: str, root: Path = ROOT) -> dict[str, str]:
    clone = clone.expanduser().resolve()
    if not clone.is_dir():
        raise AdminError(f"{clone} : dossier introuvable")
    git_path(clone, "info/exclude")  # vérifie que c'est un dépôt git
    block = consigne(projet, lang, root)
    changes = {f: upsert_block(clone / f, block) for f in INSTRUCTION_FILES}
    ajout = exclure(clone)
    changes[".git/info/exclude"] = ("ajouté : " + ", ".join(ajout)) if ajout else "inchangé"
    pf = clone / ".scope" / "projet"
    pf.parent.mkdir(parents=True, exist_ok=True)
    (clone / ".scope" / "rapports").mkdir(exist_ok=True)
    ancien = pf.read_text(encoding="utf-8").strip() if pf.exists() else None
    if ancien != projet:
        pf.write_text(projet + "\n", encoding="utf-8")
    changes[".scope/projet"] = "inchangé" if ancien == projet else ("créé" if ancien is None else "remplacé")
    changes["hook Claude Code"] = installer_hook(clone, lang, root)
    return changes


def cmd_init(args) -> int:
    projet = args.projet.strip()
    if not NAME_RE.match(projet):
        raise AdminError(f"nom de projet invalide : {projet!r} (lettres, chiffres, espaces, . _ -)")
    erreurs = 0
    for clone in args.clones:
        say(f"\n{clone}")
        try:
            for f, what in init_clone(Path(clone), projet, args.lang).items():
                say(f"  {f} : {what}")
        except AdminError as exc:
            say(f"  ERREUR : {exc}")
            erreurs += 1
            continue
        n = rapports_suivis(Path(clone).expanduser())
        if n:
            say(f"  note : {n} ancien(s) rapport(s) encore suivi(s) par git. Pour les retirer de l'index sans les effacer :")
            say(f"         git -C {clone} rm -r --cached .scope && git -C {clone} commit -m 'chore(scope): rapports hors de git'")
    say("\nRien n'a été commité : relisez CLAUDE.md et AGENTS.md, puis commitez-les si vous le souhaitez.")
    return 1 if erreurs else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scope.sh init", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projet", help="nom du projet, ex. boutique")
    ap.add_argument("clones", nargs="+", help="dossiers des clones locaux")
    ap.add_argument("--lang", choices=LANGS, default="en", help="langue de la consigne (défaut : en)")
    args = ap.parse_args(argv)
    try:
        return cmd_init(args)
    except AdminError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
