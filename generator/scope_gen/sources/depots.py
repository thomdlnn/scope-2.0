"""Source « depots » : état de chaque dépôt du projet.

Pour chaque dépôt : branche par défaut, nombre de PR ouvertes, dernier commit
et, si le projet le déclare (`deploiements` dans projects/<projet>.yml), la
version déployée lue dans le dépôt GitOps suivi par ArgoCD, avec le nombre de
commits pas encore déployés.
"""

from __future__ import annotations

import logging
from typing import Any

import yaml

from ..backends import Backend, BackendError
from ..models import DeployInfo, DeployTarget, Project, RepoStatus
from .base import Source

log = logging.getLogger(__name__)


def lookup(data: Any, dotted: str) -> Any:
    """Valeur d'un chemin pointé (`image.tag`) dans un document YAML."""
    for part in dotted.split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


class DepotsSource(Source):
    name = "depots"

    def collect(self, project: Project, backend: Backend) -> list[RepoStatus]:
        return [self.status(repo, project.deploiements.get(repo), backend) for repo in project.repos]

    @staticmethod
    def status(repo: str, target: DeployTarget | None, backend: Backend) -> RepoStatus:
        st = RepoStatus(repo=repo, url=backend.github_repo_url(repo))
        try:
            st.default_branch = backend.default_branch(repo)
            prs = backend.open_pulls_count(repo)
            if prs is not None:
                st.open_prs, st.open_prs_capped = prs
            if st.default_branch:
                st.last_commit = backend.head_commit(repo, st.default_branch)
        except BackendError as exc:
            log.warning("%s : %s", repo, exc)
            st.error = str(exc)
            return st
        if target:
            st.deploy = DepotsSource.deployed(st, target, backend)
        return st

    @staticmethod
    def deployed(st: RepoStatus, target: DeployTarget, backend: Backend) -> DeployInfo:
        info = DeployInfo(environnement=target.environnement, version=None, source_url=None)
        try:
            ref = target.ref or backend.default_branch(target.depot) or "HEAD"
            info.source_url = backend.github_file_url(target.depot, target.fichier, ref)
            text = backend.read_file(target.depot, target.fichier, ref)
            if text is None:
                info.error = f"{target.fichier} introuvable dans {target.depot}"
                return info
            value = lookup(yaml.safe_load(text), target.cle)
            if value in (None, ""):
                info.error = f"clé {target.cle} absente de {target.fichier}"
                return info
            info.version = str(value)
            if st.default_branch:
                info.en_attente = backend.commits_between(st.repo, info.version, st.default_branch)
        except (BackendError, yaml.YAMLError) as exc:
            log.warning("%s : version déployée illisible : %s", st.repo, exc)
            info.error = str(exc)
        return info

    def to_json(self, result: list[RepoStatus]):
        return [r.to_dict() for r in result]
