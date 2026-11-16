"""Backend API GitHub (dépôts privés compris, via un token)."""

from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import quote

import requests

from ..models import CommitInfo, PullRequestInfo, RawReport, commit_title
from .base import REPORTS_DIR, Backend, BackendError

log = logging.getLogger(__name__)
API = "https://api.github.com"


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
    def _open_pulls(self, repo: str) -> list[dict]:
        return self._json(f"/repos/{repo}/pulls", {"state": "open", "per_page": 100}) or []

    def default_branch(self, repo: str) -> str | None:
        return self._json(f"/repos/{repo}")["default_branch"]

    def open_pulls_count(self, repo: str) -> tuple[int, bool]:
        pulls = self._open_pulls(repo)
        return len(pulls), len(pulls) >= 100

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

    def _refs_to_scan(self, repo: str) -> list[tuple[str, str]]:
        """[(repo_qui_porte_le_fichier, ref)], branche par défaut d'abord."""
        refs = [(repo, self.default_branch(repo))]
        pulls = self._open_pulls(repo)
        for pr in pulls:
            head = pr.get("head") or {}
            head_repo = (head.get("repo") or {}).get("full_name")
            if head_repo and head.get("ref"):
                refs.append((head_repo, head["ref"]))
        return refs

    def list_reports(self, repo: str) -> list[RawReport]:
        out: list[RawReport] = []
        seen: set[str] = set()
        for src_repo, ref in self._refs_to_scan(repo):
            listing = self._json(
                f"/repos/{src_repo}/contents/{REPORTS_DIR}", {"ref": ref}, allow_404=True
            )
            if not isinstance(listing, list):
                continue
            for item in listing:
                name = item.get("name", "")
                if item.get("type") != "file" or not name.endswith(".md") or name in seen:
                    continue
                seen.add(name)  # dédoublonnage dès la lecture : évite des appels inutiles
                r = self._get(
                    f"/repos/{src_repo}/contents/{quote(item['path'])}", {"ref": ref}, raw=True
                )
                out.append(RawReport(repo=repo, path=item["path"], ref=ref, content=r.text))
        return out

    def commit_adding(self, repo: str, path: str, ref: str) -> CommitInfo | None:
        params = {"path": path, "sha": ref, "per_page": 100}
        r = self._get(f"/repos/{repo}/commits", params, allow_404=True)
        if r is None:
            return None
        commits = r.json()
        # Le commit d'ajout est le plus ancien : dernière page, dernier élément.
        last = r.links.get("last", {}).get("url")
        if last:
            commits = self._get(last).json()
        if not commits:
            return None
        c = commits[-1]
        message = commit_title((c.get("commit") or {}).get("message"))
        return CommitInfo(sha=c["sha"], message=message, url=c.get("html_url"))

    def pulls_for_commit(self, repo: str, sha: str) -> list[PullRequestInfo]:
        pulls = self._json(f"/repos/{repo}/commits/{sha}/pulls", allow_404=True) or []
        out = []
        for p in pulls:
            state = "merged" if p.get("merged_at") else p.get("state")
            out.append(
                PullRequestInfo(
                    number=p.get("number"), title=p.get("title"), state=state, url=p.get("html_url")
                )
            )
        return out

    def pull(self, repo: str, number: int) -> PullRequestInfo | None:
        p = self._json(f"/repos/{repo}/pulls/{number}", allow_404=True)
        if not p:
            return None
        state = "merged" if p.get("merged_at") else p.get("state")
        return PullRequestInfo(number=p["number"], title=p.get("title"), state=state, url=p.get("html_url"))
