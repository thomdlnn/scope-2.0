"""Interface d'accès à l'état des dépôts (implémentation : API GitHub)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import CommitInfo, PullRequestInfo


class BackendError(RuntimeError):
    pass


class Backend(ABC):
    @abstractmethod
    def default_branch(self, repo: str) -> str | None:
        """Branche par défaut ; BackendError si le dépôt est illisible."""

    @abstractmethod
    def open_pulls(self, repo: str) -> tuple[list[PullRequestInfo], bool] | None:
        """(PR ouvertes, liste tronquée ?) ; None si les PR sont illisibles."""

    def warning(self, repo: str) -> str | None:
        """Permission manquante qui n'empêche pas la lecture (ex. PR illisibles)."""
        return None

    @abstractmethod
    def head_commit(self, repo: str, ref: str) -> CommitInfo | None:
        """Dernier commit de `ref` (avec sa date)."""

    @abstractmethod
    def read_file(self, repo: str, path: str, ref: str | None = None) -> str | None:
        """Contenu d'un fichier, None s'il n'existe pas."""

    @abstractmethod
    def commits_between(self, repo: str, base: str, head: str) -> int | None:
        """Nombre de commits présents dans `head` et absents de `base`."""

    @staticmethod
    def github_repo_url(repo: str) -> str:
        return f"https://github.com/{repo}"

    @staticmethod
    def github_file_url(repo: str, path: str, ref: str) -> str:
        return f"https://github.com/{repo}/blob/{ref}/{path}"
