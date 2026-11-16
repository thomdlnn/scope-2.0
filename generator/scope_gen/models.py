"""Structures de données manipulées par le générateur."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

STATUTS = ("termine", "pr-ouverte", "bloque", "echec")

_MERGE_PR = re.compile(r"^Merge pull request #(\d+) from \S+")


def commit_title(message: str | None) -> str | None:
    """Première ligne utile d'un message de commit. Pour un merge de PR GitHub
    (« Merge pull request #14 from … »), renvoie le titre de la PR suivi de (#14)."""
    if not message:
        return None
    lines = [line.strip() for line in message.strip().splitlines()]
    m = _MERGE_PR.match(lines[0])
    if m:
        body = next((line for line in lines[1:] if line), None)
        if body:
            return f"{body} (#{m.group(1)})"
    return lines[0] or None
STATUT_ILLISIBLE = "illisible"


@dataclass
class DeployTarget:
    """Où lire la version déployée d'un dépôt (dépôt GitOps suivi par ArgoCD)."""

    depot: str  # "owner/repo" du dépôt de déploiement
    fichier: str  # chemin du fichier de valeurs, ex. environments/local/app.yaml
    cle: str = "image.tag"  # chemin pointé dans le YAML
    environnement: str = "local"
    ref: str | None = None  # branche lue (défaut : branche par défaut)


@dataclass
class Project:
    name: str
    title: str
    repos: list[str]  # "owner/repo"
    deploiements: dict[str, DeployTarget] = field(default_factory=dict)
    token: str | None = None  # nom du secret/variable du token dédié (sinon token global)
    sante: str | None = None  # URL de santé appelée par le navigateur (CORS requis)


@dataclass
class RawReport:
    """Un fichier de rapport tel que lu par un backend, avant parsing."""

    repo: str  # "owner/repo"
    path: str  # chemin dans le dépôt, ex. ".scope/rapports/2026-...md"
    ref: str  # branche (ou ref) où le fichier a été lu
    content: str

    @property
    def filename(self) -> str:
        return self.path.rsplit("/", 1)[-1]


@dataclass
class CommitInfo:
    sha: str
    message: str | None = None
    url: str | None = None
    date: datetime | None = None

    @property
    def short(self) -> str:
        return self.sha[:7]


@dataclass
class PullRequestInfo:
    number: int | None
    title: str | None
    state: str | None = None  # open | merged | closed | None (inconnu)
    url: str | None = None


@dataclass
class Report:
    repo: str
    path: str
    ref: str
    valid: bool
    error: str | None = None
    date: datetime | None = None
    projet: str | None = None
    agent: str | None = None
    branche: str | None = None
    statut: str = STATUT_ILLISIBLE
    commit_message: str | None = None
    pr_titre: str | None = None
    pr_numero: int | None = None
    resume: str | None = None
    detail_md: str | None = None
    prochaine_etape_md: str | None = None
    commit: CommitInfo | None = None
    pr: PullRequestInfo | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def filename(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def repo_name(self) -> str:
        return self.repo.rsplit("/", 1)[-1]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["date"] = self.date.isoformat() if self.date else None
        d["filename"] = self.filename
        if self.commit:
            d["commit"]["short"] = self.commit.short
        return d


@dataclass
class DeployInfo:
    environnement: str
    version: str | None  # valeur lue (SHA de l'image en général)
    source_url: str | None  # lien vers le fichier GitOps
    en_attente: int | None = None  # commits de la branche par défaut non déployés
    error: str | None = None

    @property
    def short(self) -> str | None:
        return self.version[:7] if self.version else None


@dataclass
class RepoStatus:
    repo: str  # "owner/repo"
    url: str
    default_branch: str | None = None
    open_prs: int | None = None
    open_prs_capped: bool = False  # True si la liste a été tronquée (>= 100)
    last_commit: CommitInfo | None = None
    deploy: DeployInfo | None = None
    error: str | None = None

    @property
    def name(self) -> str:
        return self.repo.rsplit("/", 1)[-1]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["name"] = self.name
        if self.last_commit:
            d["last_commit"]["short"] = self.last_commit.short
            d["last_commit"]["date"] = self.last_commit.date.isoformat() if self.last_commit.date else None
        return d
