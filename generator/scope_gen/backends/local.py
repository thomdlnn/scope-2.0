"""Backend local : lit des clones git sur disque, sans token ni réseau.

`<dossier>/<nom-du-repo>` est le clone de `owner/<nom-du-repo>`.
- Clone git : la branche courante joue le rôle de branche par défaut, les
  autres branches locales celui des branches de PR ouvertes.
- Dossier sans .git : on lit simplement `.scope/rapports/` sur disque.
Les PR ne sont pas connues en local : l'affichage se rabat sur pr_numero /
pr_titre du rapport.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from ..models import CommitInfo, PullRequestInfo, RawReport, commit_title
from .base import REPORTS_DIR, Backend, BackendError


class LocalBackend(Backend):
    def __init__(self, root: Path):
        self.root = Path(root)

    def _dir(self, repo: str) -> Path:
        d = self.root / repo.rsplit("/", 1)[-1]
        if not d.is_dir():
            raise BackendError(f"clone local introuvable : {d}")
        return d

    def _git(self, d: Path, *args: str) -> str:
        try:
            res = subprocess.run(
                ["git", "-C", str(d), *args], capture_output=True, text=True, check=True
            )
        except subprocess.CalledProcessError as exc:
            raise BackendError(f"git {' '.join(args)} : {exc.stderr.strip()}") from None
        return res.stdout

    def _is_git(self, d: Path) -> bool:
        return (d / ".git").exists()

    def _branches(self, d: Path) -> list[str]:
        current = self._git(d, "rev-parse", "--abbrev-ref", "HEAD").strip()
        others = [
            b
            for b in self._git(d, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()
            if b != current
        ]
        return [current, *sorted(others)]

    def list_reports(self, repo: str) -> list[RawReport]:
        d = self._dir(repo)
        if not self._is_git(d):
            folder = d / REPORTS_DIR
            return [
                RawReport(repo, f"{REPORTS_DIR}/{p.name}", "local", p.read_text(encoding="utf-8"))
                for p in sorted(folder.glob("*.md"))
            ]
        out = []
        for ref in self._branches(d):
            names = self._git(d, "ls-tree", "--name-only", f"{ref}:{REPORTS_DIR}") if self._has_dir(d, ref) else ""
            for name in sorted(names.split()):
                if name.endswith(".md"):
                    path = f"{REPORTS_DIR}/{name}"
                    out.append(RawReport(repo, path, ref, self._git(d, "show", f"{ref}:{path}")))
        return out

    def _has_dir(self, d: Path, ref: str) -> bool:
        try:
            self._git(d, "cat-file", "-e", f"{ref}:{REPORTS_DIR}")
            return True
        except BackendError:
            return False

    def commit_adding(self, repo: str, path: str, ref: str) -> CommitInfo | None:
        d = self._dir(repo)
        if not self._is_git(d):
            return None
        out = self._git(d, "log", ref, "--diff-filter=A", "--format=%H%x00%s", "--", path).strip()
        if not out:
            return None
        sha, _, subject = out.splitlines()[-1].partition("\x00")
        return CommitInfo(sha=sha, message=subject or None, url=self.github_commit_url(repo, sha))

    def pulls_for_commit(self, repo: str, sha: str) -> list[PullRequestInfo]:
        return []

    # --- État des dépôts ----------------------------------------------------
    def default_branch(self, repo: str) -> str | None:
        d = self._dir(repo)
        return self._branches(d)[0] if self._is_git(d) else None

    def head_commit(self, repo: str, ref: str) -> CommitInfo | None:
        d = self._dir(repo)
        if not self._is_git(d):
            return None
        sha, date, message = self._git(d, "log", "-1", "--format=%H%x00%cI%x00%B", ref).strip().split("\x00", 2)
        return CommitInfo(sha, commit_title(message), self.github_commit_url(repo, sha), datetime.fromisoformat(date))

    def read_file(self, repo: str, path: str, ref: str | None = None) -> str | None:
        d = self._dir(repo)
        if not self._is_git(d):
            f = d / path
            return f.read_text(encoding="utf-8") if f.is_file() else None
        try:
            return self._git(d, "show", f"{ref or 'HEAD'}:{path}")
        except BackendError:
            return None

    def commits_between(self, repo: str, base: str, head: str) -> int | None:
        d = self._dir(repo)
        if not self._is_git(d):
            return None
        try:
            return int(self._git(d, "rev-list", "--count", f"{base}..{head}").strip())
        except BackendError:
            return None
