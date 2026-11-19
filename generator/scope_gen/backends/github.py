"""Backend API GitHub (dépôts privés compris, via un token)."""

from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import quote

import requests

from ..models import CommitInfo, PullRequestInfo, commit_title
from .base import Backend, BackendError

log = logging.getLogger(__name__)
API = "https://api.github.com"
REPO_DENIED = (
    "dépôt introuvable avec ce token (HTTP 404) : ajoutez ce dépôt au token "
    "(Repository access), ou vérifiez l'URL du remote origin du clone"
)
PULLS_DENIED = "PR non lues : ajoutez la permission « Pull requests : Read-only » au token"
TOKEN_REFUSED = "token refusé (HTTP 401) : SCOPE_GH_TOKEN est invalide ou expiré"


class GitHubBackend(Backend):
    def __init__(self, token: str | None, api: str = API, session: requests.Session | None = None):
        self.api = api.rstrip("/")
        self.s = session or requests.Session()
        self.s.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "scope-generator",
            }
        )
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"
        self._cache: dict[str, object] = {}
        self.warnings: dict[str, str] = {}  # dépôt → permission manquante (non bloquante)

    # --- HTTP -------------------------------------------------------------
    def _get(self, path: str, params: dict | None = None, raw: bool = False, allow_404: bool = False):
        url = path if path.startswith("http") else f"{self.api}{path}"
        headers = {"Accept": "application/vnd.github.raw"} if raw else None
        try:
            r = self.s.get(url, params=params, headers=headers, timeout=30)
        except requests.RequestException as exc:
            raise BackendError(f"GET {url} : {exc}") from None
        if r.status_code == 404 and allow_404:
            return None
        if r.status_code == 401:
            raise BackendError(TOKEN_REFUSED)
        if r.status_code >= 400:
            msg = r.text[:200].replace("\n", " ")
            raise BackendError(f"GET {url} → HTTP {r.status_code} : {msg}")
        return r

    def _json(self, path: str, params: dict | None = None, allow_404: bool = False):
        key = f"{path}?{sorted((params or {}).items())}"
        if key not in self._cache:
            r = self._get(path, params, allow_404=allow_404)
            self._cache[key] = None if r is None else r.json()
        return self._cache[key]

    # --- Backend ------------------------------------------------------------
    def _open_pulls(self, repo: str) -> list[dict] | None:
        """PR ouvertes ; None si le token n'a pas la permission « Pull requests »
        (le reste de l'état du dépôt reste lu)."""
        try:
            return self._json(f"/repos/{repo}/pulls", {"state": "open", "per_page": 100}) or []
        except BackendError as exc:
            if "HTTP 403" not in str(exc):
                raise
            if repo not in self.warnings:
                log.info("%s : PR illisibles : %s", repo, exc)
                self.warnings[repo] = PULLS_DENIED
            return None

    def default_branch(self, repo: str) -> str | None:
        data = self._json(f"/repos/{repo}", allow_404=True)
        if data is None:
            raise BackendError(REPO_DENIED)
        return data["default_branch"]

    def open_pulls(self, repo: str) -> tuple[list[PullRequestInfo], bool] | None:
        pulls = self._open_pulls(repo)
        if pulls is None:
            return None
        out = []
        for p in pulls:
            maj = p.get("updated_at")
            out.append(
                PullRequestInfo(
                    number=p.get("number"),
                    title=p.get("title"),
                    url=p.get("html_url"),
                    auteur=(p.get("user") or {}).get("login"),
                    brouillon=bool(p.get("draft")),
                    maj=datetime.fromisoformat(maj.replace("Z", "+00:00")) if maj else None,
                )
            )
        return out, len(pulls) >= 100

    def warning(self, repo: str) -> str | None:
        return self.warnings.get(repo)

    def head_commit(self, repo: str, ref: str) -> CommitInfo | None:
        c = self._json(f"/repos/{repo}/commits/{quote(ref, safe='')}", allow_404=True)
        if not c:
            return None
        commit = c.get("commit") or {}
        raw_date = (commit.get("committer") or {}).get("date")
        return CommitInfo(
            sha=c["sha"],
            message=commit_title(commit.get("message")),
            url=c.get("html_url"),
            date=datetime.fromisoformat(raw_date.replace("Z", "+00:00")) if raw_date else None,
        )

    def read_file(self, repo: str, path: str, ref: str | None = None) -> str | None:
        r = self._get(f"/repos/{repo}/contents/{quote(path)}", {"ref": ref} if ref else None, raw=True, allow_404=True)
        return None if r is None else r.text

    def commits_between(self, repo: str, base: str, head: str) -> int | None:
        c = self._json(f"/repos/{repo}/compare/{quote(base, safe='')}...{quote(head, safe='')}", allow_404=True)
        return None if not c else c.get("ahead_by")
