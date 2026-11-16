"""Interface d'accès aux dépôts.

Un backend sait lire des fichiers et résoudre des commits/PR. Deux
implémentations : GitHub (API REST) et local (clones git sur disque).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import CommitInfo, PullRequestInfo, RawReport

REPORTS_DIR = ".scope/rapports"


class BackendError(RuntimeError):
    pass


class Backend(ABC):
    @abstractmethod
    def list_reports(self, repo: str) -> list[RawReport]:
        """Rapports de la branche par défaut puis des branches des PR ouvertes
        (branche par défaut en premier : utile au dédoublonnage)."""

    @abstractmethod
    def commit_adding(self, repo: str, path: str, ref: str) -> CommitInfo | None:
        """Le commit qui a ajouté `path` (le plus ancien qui le touche)."""

    @abstractmethod
    def pulls_for_commit(self, repo: str, sha: str) -> list[PullRequestInfo]:
        """Les PR qui contiennent ce commit."""

    def pull(self, repo: str, number: int) -> PullRequestInfo | None:
        """Une PR par son numéro (None si le backend ne sait pas)."""
        return None

    # --- État des dépôts (source « depots ») ---------------------------------
    # Implémentations par défaut : « inconnu ». Un backend surcharge ce qu'il sait faire.
    def default_branch(self, repo: str) -> str | None:
        return None

    def open_pulls_count(self, repo: str) -> tuple[int, bool] | None:
        """(nombre de PR ouvertes, liste tronquée ?)"""
        return None

    def head_commit(self, repo: str, ref: str) -> CommitInfo | None:
        """Dernier commit de `ref` (avec sa date)."""
        return None

    def read_file(self, repo: str, path: str, ref: str | None = None) -> str | None:
        """Contenu d'un fichier, None s'il n'existe pas."""
        return None

    def commits_between(self, repo: str, base: str, head: str) -> int | None:
        """Nombre de commits présents dans `head` et absents de `base`."""
        return None

    @staticmethod
    def github_commit_url(repo: str, sha: str) -> str:
        return f"https://github.com/{repo}/commit/{sha}"

    @staticmethod
    def github_pr_url(repo: str, number: int) -> str:
        return f"https://github.com/{repo}/pull/{number}"

    @staticmethod
    def github_repo_url(repo: str) -> str:
        return f"https://github.com/{repo}"

    @staticmethod
    def github_file_url(repo: str, path: str, ref: str) -> str:
        return f"https://github.com/{repo}/blob/{ref}/{path}"
