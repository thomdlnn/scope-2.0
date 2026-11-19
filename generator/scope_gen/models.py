"""Structures de données de l'état des dépôts GitHub (token optionnel)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

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


def _iso(d: datetime | None) -> str | None:
    return d.isoformat().replace("+00:00", "Z") if d else None


@dataclass(frozen=True)
class DeployTarget:
    """Où lire la version déployée d'un dépôt (dépôt GitOps suivi par ArgoCD)."""

    depot: str  # "owner/repo" du dépôt de déploiement
    fichier: str  # chemin du fichier de valeurs, ex. environments/local/app.yaml
    cle: str = "image.tag"  # chemin pointé dans le YAML
    environnement: str = "local"
    ref: str | None = None  # branche lue (défaut : branche par défaut)


@dataclass
class Project:
    """Réglages optionnels d'un projet (projects/<projet>.yml)."""

    name: str
    deploiements: dict[str, DeployTarget] = field(default_factory=dict)
    sante: str | None = None  # URL de santé appelée par le navigateur (CORS requis)


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
    number: int
    title: str | None
    url: str | None = None
    auteur: str | None = None
    brouillon: bool = False
    maj: datetime | None = None


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
    prs: list[PullRequestInfo] | None = None  # None : PR illisibles avec ce token
    prs_capped: bool = False  # True si la liste a été tronquée (>= 100)
    last_commit: CommitInfo | None = None
    deploy: DeployInfo | None = None
    error: str | None = None
    warning: str | None = None  # permission manquante non bloquante

    @property
    def name(self) -> str:
        return self.repo.rsplit("/", 1)[-1]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["name"] = self.name
        if self.last_commit:
            d["last_commit"]["short"] = self.last_commit.short
            d["last_commit"]["date"] = _iso(self.last_commit.date)
        for p, src in zip(d["prs"] or [], self.prs or []):
            p["maj"] = _iso(src.maj)
        return d
