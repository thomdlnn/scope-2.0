"""Construit de vrais dépôts git à partir de tests/fixtures/repos/.

repos/<repo>/<branche>/*.md  →  <dest>/<repo>/.scope/rapports/*.md, un commit
par rapport, sur la branche <branche> ("__" devient "/"). La branche `main`
est créée d'abord ; les autres partent de `main`.

repos/<repo>/files/**  →  fichiers copiés tels quels sur `main` (dépôt GitOps de
démonstration), après les autres dépôts : `{{SHA:<repo>:<rev>}}` y est remplacé
par le SHA de <rev> dans <repo>.

Usage : python tests/fixtures/make_repos.py <dest>
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPOS = HERE / "repos"
ENV = {
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
}


def git(d: Path, *args: str, date: str | None = None) -> None:
    env = dict(ENV)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True, env=env)


def commit_message(text: str, name: str) -> str:
    m = re.search(r'^commit_message:\s*"([^"\n]*)"\s*$', text, re.M)
    return m.group(1) if m else f"docs: rapport {name}"


SHA_RE = re.compile(r"\{\{SHA:([^:}]+):([^}]+)\}\}")


def rev_parse(d: Path, rev: str) -> str:
    env = dict(ENV)
    return subprocess.run(
        ["git", "-C", str(d), "rev-parse", rev], check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


def build_files_repo(dest: Path, repo_src: Path) -> None:
    d = dest / repo_src.name
    d.mkdir()
    git(d, "init", "-q", "-b", "main")
    for f in sorted(p for p in (repo_src / "files").rglob("*") if p.is_file()):
        target = d / f.relative_to(repo_src / "files")
        target.parent.mkdir(parents=True, exist_ok=True)
        text = SHA_RE.sub(lambda m: rev_parse(dest / m.group(1), m.group(2)), f.read_text(encoding="utf-8"))
        target.write_text(text, encoding="utf-8")
    git(d, "add", ".")
    git(d, "commit", "-q", "-m", "chore(gitops): versions déployées", date="2026-11-16T12:00:00Z")


def build(dest: Path) -> Path:
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    all_repos = sorted(p for p in REPOS.iterdir() if p.is_dir())
    for repo_src in all_repos:
        if (repo_src / "files").is_dir():
            continue  # dépôts GitOps : construits après les autres
        d = dest / repo_src.name
        d.mkdir()
        git(d, "init", "-q", "-b", "main")
        branches = sorted((p for p in repo_src.iterdir() if p.is_dir()), key=lambda p: p.name != "main")
        for br in branches:
            branch = br.name.replace("__", "/")
            if branch != "main":
                git(d, "checkout", "-q", "-b", branch, "main")
            reports = d / ".scope" / "rapports"
            reports.mkdir(parents=True, exist_ok=True)
            for f in sorted(br.glob("*.md")):
                target = reports / f.name
                if target.exists():
                    continue  # déjà présent (hérité de main)
                text = f.read_text(encoding="utf-8")
                target.write_text(text, encoding="utf-8")
                ts = f.name[:17]  # AAAA-MM-JJ-HHMMSS
                date = f"{ts[:10]}T{ts[11:13]}:{ts[13:15]}:{ts[15:17]}Z"
                git(d, "add", ".")
                git(d, "commit", "-q", "-m", commit_message(text, f.name), date=date)
        git(d, "checkout", "-q", "main")
    for repo_src in all_repos:
        if (repo_src / "files").is_dir():
            build_files_repo(dest, repo_src)
    return dest


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(build(Path(sys.argv[1])))
