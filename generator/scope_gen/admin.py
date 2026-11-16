"""Administration de SCOPE : `./scope.sh init | consigne | refresh`.

init <projet>
    1. Demande un token GitHub en lecture (masqué, ou variable SCOPE_TOKEN).
    2. Liste les dépôts que ce token peut lire ; vous choisissez ceux du projet
       (ou --repos o/a,o/b).
    3. Écrit projects/<projet>.yml (les réglages existants, comme
       `deploiements`, sont conservés).
    4. Enregistre le token en secret du dépôt SCOPE : token global
       SCOPE_GH_TOKEN, ou token dédié SCOPE_TOKEN_<PROJET>.
    5. Dépose la consigne SCOPE dans CLAUDE.md et AGENTS.md de chaque dépôt,
       avec VOS droits (gh) : une PR par dépôt, ou directement dans vos
       clones locaux (--clones DIR).
    6. Propose projects/<projet>.yml au dépôt SCOPE (PR).
    Avec --env (Docker Compose) : le token va dans .env et le fichier projet
    reste local, lu directement par le générateur.
consigne <projet>
    Redépose (ou met à jour) la consigne dans les dépôts d'un projet existant.
refresh
    Lance une régénération immédiate de la page (Action build-site).

--dry-run : rien n'est envoyé (ni secret, ni push, ni PR) ; les fichiers
locaux sont écrits et les changements prévus sont affichés.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
import yaml

from .config import NAME_RE, REPO_RE

ROOT = Path(__file__).resolve().parents[2]
START, END = "<!-- scope:start -->", "<!-- scope:end -->"
BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
GLOBAL_SECRET = "SCOPE_GH_TOKEN"
INSTRUCTION_FILES = ("CLAUDE.md", "AGENTS.md")
#: Fichiers posés par d'anciennes versions de SCOPE, retirés à la mise à jour.
OBSOLETE_FILES = (".github/workflows/notify-scope.yml",)


class AdminError(RuntimeError):
    pass


def say(msg: str = "") -> None:
    print(msg, flush=True)


# --- Consigne IA ---------------------------------------------------------------
def consigne(projet: str, root: Path = ROOT) -> str:
    return (root / "templates" / "instructions-ia.md").read_text(encoding="utf-8").replace("{{PROJET}}", projet)


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


def apply_consigne(repo_dir: Path, block: str) -> dict[str, str]:
    """Pose la consigne et le dossier des rapports dans un dépôt sur disque."""
    gitkeep = repo_dir / ".scope" / "rapports" / ".gitkeep"
    gitkeep.parent.mkdir(parents=True, exist_ok=True)
    gitkeep.touch()
    changes = {f: upsert_block(repo_dir / f, block) for f in INSTRUCTION_FILES}
    for f in OBSOLETE_FILES:
        if (repo_dir / f).exists():
            (repo_dir / f).unlink()
            changes[f] = "supprimé (obsolète)"
    return changes


# --- Projet ----------------------------------------------------------------------
def secret_name(projet: str) -> str:
    return "SCOPE_TOKEN_" + re.sub(r"[^A-Z0-9]", "_", projet.upper())


def write_project(path: Path, name: str, title: str, repos: list[str], token: str | None) -> None:
    """Écrit projects/<projet>.yml en conservant les réglages déjà présents
    (deploiements…), sauf ceux des dépôts retirés."""
    data = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data["name"] = name
    data["title"] = title
    data["repos"] = repos
    if token:
        data["token"] = token
    else:
        data.pop("token", None)
    if isinstance(data.get("deploiements"), dict):
        data["deploiements"] = {k: v for k, v in data["deploiements"].items() if k in repos}
        if not data["deploiements"]:
            data.pop("deploiements")
    order = ["name", "title", "token", "repos", "deploiements"]
    ordered = {k: data[k] for k in order if k in data} | {k: v for k, v in data.items() if k not in order}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False), encoding="utf-8")


def parse_selection(answer: str, n: int) -> list[int]:
    """« » ou « tous » → tout ; « 1,3-5 » → [0, 2, 3, 4]."""
    answer = answer.strip().lower()
    if answer in ("", "tous", "*", "all"):
        return list(range(n))
    out: list[int] = []
    for part in answer.replace(" ", "").split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a) - 1, int(b)))
        elif part:
            out.append(int(part) - 1)
    if not out or any(i < 0 or i >= n for i in out):
        raise AdminError(f"sélection invalide : {answer!r} (numéros de 1 à {n})")
    return sorted(set(out))


# --- GitHub : lecture avec le token de l'utilisateur ------------------------------
class TokenReader:
    """Ce que le token fourni permet de lire (API REST, lecture seule)."""

    def __init__(self, token: str, api: str = "https://api.github.com"):
        self.api = api
        self.s = requests.Session()
        self.s.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "scope-admin",
            }
        )

    def readable_repos(self) -> list[str]:
        repos, url = [], f"{self.api}/user/repos"
        params = {"per_page": 100, "sort": "full_name"}
        while url:
            r = self.s.get(url, params=params, timeout=30)
            if r.status_code == 401:
                raise AdminError("token refusé par GitHub (401) : vérifiez-le ou sa date d'expiration")
            r.raise_for_status()
            repos += [x["full_name"] for x in r.json()]
            url, params = r.links.get("next", {}).get("url"), None
        return repos

    def can_read(self, repo: str) -> bool:
        return self.s.get(f"{self.api}/repos/{repo}", timeout=30).status_code == 200


# --- gh / git : actions avec les droits de l'utilisateur ---------------------------
def run(*cmd: str, cwd: Path | None = None, input: str | None = None, check: bool = True) -> str:
    res = subprocess.run(cmd, cwd=cwd, input=input, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise AdminError(f"{' '.join(cmd[:3])}… : {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout.strip()


def scope_repo(root: Path = ROOT) -> str:
    if os.environ.get("SCOPE_REPO"):
        return os.environ["SCOPE_REPO"]
    url = run("git", "-C", str(root), "remote", "get-url", "origin", check=False)
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    if not m:
        raise AdminError("dépôt SCOPE introuvable : définissez SCOPE_REPO=owner/scope")
    return m.group(1)


def existing_secrets(repo: str) -> set[str]:
    out = run("gh", "secret", "list", "-R", repo, "--json", "name", "-q", ".[].name", check=False)
    return set(out.split())


def set_secret(repo: str, name: str, value: str) -> None:
    run("gh", "secret", "set", name, "-R", repo, input=value)


def read_env(path: Path) -> dict[str, str]:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def write_env(path: Path, name: str, value: str) -> None:
    """Ajoute ou remplace NAME=valeur dans un fichier .env (droits 600)."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == name and not line.lstrip().startswith("#"):
            lines[i] = f"{name}={value}"
            break
    else:
        lines.append(f"{name}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def git_identity(root: Path) -> list[str]:
    name = run("git", "-C", str(root), "config", "user.name", check=False) or "scope"
    email = run("git", "-C", str(root), "config", "user.email", check=False) or "scope@localhost"
    return ["-c", f"user.name={name}", "-c", f"user.email={email}"]


def push_branch_and_pr(d: Path, repo: str, branch: str, base: str, title: str, body: str, ident: list[str]) -> str:
    run("git", *ident, "commit", "-q", "-m", title, cwd=d)
    # Si la branche existe déjà (PR ouverte à mettre à jour, ou ancienne PR mergée),
    # on la remplace en vérifiant qu'elle n'a pas bougé depuis sa lecture.
    remote = run("git", "ls-remote", "origin", f"refs/heads/{branch}", cwd=d, check=False).split()
    lease = f"--force-with-lease=refs/heads/{branch}:{remote[0]}" if remote else "--force-with-lease"
    run("git", "push", "-q", lease, "origin", f"HEAD:refs/heads/{branch}", cwd=d)
    existing = run("gh", "pr", "view", branch, "-R", repo, "--json", "url,state", "-q", 'select(.state=="OPEN") | .url', check=False)
    if existing:
        return f"PR mise à jour : {existing}"
    url = run("gh", "pr", "create", "-R", repo, "--base", base, "--head", branch, "--title", title, "--body", body)
    return f"PR ouverte : {url}"


def consigne_by_pr(repo: str, projet: str, block: str, dry_run: bool, ident: list[str]) -> str:
    branch = f"scope/init-{projet}"
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "repo"
        run("gh", "repo", "clone", repo, str(d), "--", "-q", "--depth", "1")
        base = run("git", "rev-parse", "--abbrev-ref", "HEAD", cwd=d)
        run("git", "checkout", "-q", "-b", branch, cwd=d)
        changes = apply_consigne(d, block)
        run("git", "add", "-A", cwd=d)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=d).returncode == 0:
            return "déjà à jour"
        summary = ", ".join(f"{f} {c}" for f, c in changes.items())
        if dry_run:
            return f"(dry-run) {summary}"
        body = (
            "Ajoute la consigne SCOPE à ce dépôt :\n\n"
            "- `.scope/rapports/` : dossier des rapports déposés par l'IA après chaque prompt ;\n"
            "- consigne SCOPE dans `CLAUDE.md` et `AGENTS.md`, entre `<!-- scope:start -->` et `<!-- scope:end -->` "
            "(relancer `./scope.sh consigne` la met à jour sans la dupliquer) ;\n"
            "- suppression des fichiers posés par d'anciennes versions de SCOPE (`notify-scope.yml`), s'il y en a.\n\n"
            "Pour Cursor ou Copilot, copiez le même bloc dans `.cursor/rules/scope.mdc` ou `.github/copilot-instructions.md`."
        )
        return f"{summary} — " + push_branch_and_pr(
            d, repo, branch, base, f"chore(scope): consigne SCOPE (projet {projet})", body, ident
        )


def propose_project_file(root: Path, repo: str, projet: str, dry_run: bool, ident: list[str]) -> str:
    """PR sur le dépôt SCOPE avec projects/<projet>.yml, via un worktree temporaire
    (votre copie de travail n'est pas touchée)."""
    rel = f"projects/{projet}.yml"
    if dry_run:
        return f"(dry-run) {rel} serait proposé au dépôt {repo}"
    base = run("gh", "repo", "view", repo, "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name")
    branch = f"scope/projet-{projet}"
    run("git", "-C", str(root), "fetch", "-q", "origin", base)
    with tempfile.TemporaryDirectory() as tmp:
        wt = Path(tmp) / "wt"
        run("git", "-C", str(root), "worktree", "add", "-q", "--detach", str(wt), f"origin/{base}")
        try:
            (wt / "projects").mkdir(exist_ok=True)
            shutil.copy(root / rel, wt / rel)
            run("git", "add", "--force", rel, cwd=wt)  # projects/*.yml est ignoré par défaut
            if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=wt).returncode == 0:
                return f"{rel} déjà à jour sur {base}"
            body = f"Ajoute ou met à jour le projet SCOPE `{projet}` (`{rel}`).\n\nGénéré par `./scope.sh init {projet}`."
            return push_branch_and_pr(wt, repo, branch, base, f"feat(projects): projet {projet}", body, ident)
        finally:
            run("git", "-C", str(root), "worktree", "remove", "--force", str(wt), check=False)


# --- Commandes ----------------------------------------------------------------------
def ask(prompt: str, default: str = "") -> str:
    try:
        return input(prompt).strip() or default
    except EOFError:
        return default


def cmd_init(args, reader_factory=TokenReader) -> int:
    projet = args.projet
    if not NAME_RE.match(projet):
        raise AdminError(f"nom de projet invalide : {projet!r} (minuscules, chiffres, tirets)")
    root = Path(args.root)
    token = os.environ.get("SCOPE_TOKEN") or getpass.getpass(
        "Token GitHub en lecture sur les dépôts du projet (non affiché) : "
    )
    if not token.strip():
        raise AdminError("token vide")
    reader = reader_factory(token.strip())

    # 1. Dépôts du projet
    if args.repos:
        repos = [r.strip() for r in args.repos.split(",") if r.strip()]
    else:
        found = reader.readable_repos()
        if not found:
            raise AdminError("ce token ne donne accès à aucun dépôt")
        say(f"\nDépôts lisibles avec ce token ({len(found)}) :")
        for i, r in enumerate(found, 1):
            say(f"  {i:>2}. {r}")
        choice = "" if args.yes else ask("Dépôts du projet (Entrée = tous, ou numéros : 1,3-5) : ")
        repos = [found[i] for i in parse_selection(choice, len(found))]
    bad = [r for r in repos if not REPO_RE.match(r)]
    if bad:
        raise AdminError(f"dépôt(s) invalide(s) : {', '.join(bad)} (format owner/repo)")
    unreadable = [r for r in repos if not reader.can_read(r)]
    if unreadable:
        raise AdminError(f"le token ne lit pas : {', '.join(unreadable)}")
    say(f"✔ {len(repos)} dépôt(s) lisible(s) : {', '.join(repos)}")

    # 2. Token : global ou dédié au projet, en secret GitHub (Actions) ou dans
    #    un fichier .env (Docker Compose, --env).
    env_file = Path(args.env) if args.env else None
    if env_file:
        where, existing = str(env_file), set(read_env(env_file))
    else:
        scope = scope_repo(root)
        where, existing = scope, existing_secrets(scope) if not args.offline else set()
    if args.token_dedie:
        dedicated = True
    elif args.token_global or GLOBAL_SECRET not in existing:
        dedicated = False
    elif args.yes:
        dedicated = True
    else:
        say(f"\nUn token global ({GLOBAL_SECRET}) existe déjà dans {where}.")
        dedicated = ask("  [d] token dédié à ce projet (recommandé) / [r] remplacer le token global : ", "d").lower() != "r"
    secret = secret_name(projet) if dedicated else GLOBAL_SECRET

    # 3. projects/<projet>.yml
    path = root / "projects" / f"{projet}.yml"
    write_project(path, projet, args.titre or projet.capitalize(), repos, secret if dedicated else None)
    say(f"✔ {path.relative_to(root)}")

    # 4. Token
    if env_file:
        write_env(env_file, secret, token.strip())
        say(f"✔ {secret} enregistré dans {env_file} (fichier local, jamais commité)")
    elif args.dry_run:
        say(f"(dry-run) secret {secret} non enregistré dans {where}")
    else:
        set_secret(where, secret, token.strip())
        say(f"✔ secret {secret} enregistré dans {where}")

    # 5. Consigne dans les dépôts + 6. fichier projet
    ident = git_identity(root)
    deposit(projet, repos, args, ident)
    if env_file:
        say("\nÉtapes suivantes : merger les PR ci-dessus, puis « ./scope.sh up » (ou « ./scope.sh refresh » s'il tourne déjà).")
        return 0
    say("\n── " + where)
    say("  " + propose_project_file(root, where, projet, args.dry_run or args.offline, ident))
    say(
        "\nÉtapes suivantes : merger les PR ci-dessus, puis « ./scope.sh refresh » "
        "(sinon la page se met à jour d'elle-même toutes les 15 min)."
    )
    return 0


def deposit(projet: str, repos: list[str], args, ident: list[str]) -> None:
    block = consigne(projet, Path(args.root))
    for repo in repos:
        say(f"\n── {repo}")
        if args.clones:
            d = Path(args.clones) / repo.rsplit("/", 1)[-1]
            if not d.is_dir():
                say(f"  ⚠ clone introuvable : {d}")
                continue
            changes = apply_consigne(d, block)
            say("  " + ", ".join(f"{f} {c}" for f, c in changes.items()) + f" (dans {d}, à commiter)")
        else:
            say("  " + consigne_by_pr(repo, projet, block, args.dry_run, ident))


def cmd_consigne(args) -> int:
    from .config import load_project

    project = load_project(Path(args.root) / "projects" / f"{args.projet}.yml")
    deposit(project.name, project.repos, args, git_identity(Path(args.root)))
    return 0


def cmd_refresh(args) -> int:
    repo = scope_repo(Path(args.root))
    run("gh", "workflow", "run", "build-site.yml", "-R", repo)
    say(f"✔ régénération lancée sur {repo} (environ 1 min, puis 60 s pour la synchronisation) :")
    say(f"  https://github.com/{repo}/actions/workflows/build-site.yml")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scope.sh", description="Administration de SCOPE.")
    ap.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="ajoute (ou met à jour) un projet")
    p.add_argument("projet")
    p.add_argument("--titre", help="titre affiché (défaut : nom du projet)")
    p.add_argument("--repos", help="dépôts owner/repo séparés par des virgules (sinon : choix parmi ceux du token)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--token-dedie", action="store_true", help="enregistre le token pour ce projet seulement")
    g.add_argument("--token-global", action="store_true", help=f"remplace le token global {GLOBAL_SECRET}")
    p.add_argument("--clones", metavar="DIR", help="dépose la consigne dans vos clones locaux DIR/<repo> au lieu d'ouvrir des PR")
    p.add_argument(
        "--env", metavar="FICHIER", nargs="?", const=".env",
        help="mode Docker Compose : token écrit dans FICHIER (défaut .env) au lieu d'un secret GitHub",
    )
    p.add_argument("--dry-run", action="store_true", help="n'envoie rien (ni secret, ni push, ni PR)")
    p.add_argument("--offline", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("-y", "--yes", action="store_true", help="aucune question (tous les dépôts, token dédié si un global existe)")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("consigne", help="redépose la consigne IA dans les dépôts d'un projet")
    p.add_argument("projet")
    p.add_argument("--clones", metavar="DIR")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_consigne)

    p = sub.add_parser("refresh", help="régénère la page maintenant")
    p.set_defaults(func=cmd_refresh)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except AdminError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrompu", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
