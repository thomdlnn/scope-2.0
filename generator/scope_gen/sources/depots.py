"""État des dépôts GitHub d'un projet (seulement avec un token, optionnel).

Pour chaque dépôt (déduit du remote origin des clones) : branche par défaut,
toutes les PR ouvertes, dernier commit de la branche par défaut et, si le
projet le déclare (`deploiements` dans projects/<projet>.yml), la version
déployée lue dans le dépôt GitOps, avec le nombre de commits pas encore
déployés.

L'API GitHub est lue en tâche de fond toutes les SCOPE_GH_INTERVAL secondes :
la lecture locale des rapports (toutes les 3 s) n'attend jamais le réseau.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import yaml

from ..backends import Backend, BackendError
from ..models import DeployInfo, DeployTarget, RepoStatus

log = logging.getLogger(__name__)

Demande = tuple[str, DeployTarget | None]  # (owner/repo, cible de déploiement)


def lookup(data: Any, dotted: str) -> Any:
    """Valeur d'un chemin pointé (`image.tag`) dans un document YAML."""
    for part in dotted.split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def status(repo: str, target: DeployTarget | None, backend: Backend) -> RepoStatus:
    """État d'un dépôt. Ne lève pas : une erreur est consignée dans le résultat."""
    st = RepoStatus(repo=repo, url=backend.github_repo_url(repo))
    try:
        st.default_branch = backend.default_branch(repo)
        prs = backend.open_pulls(repo)
        if prs is not None:
            st.prs, st.prs_capped = prs
        if st.default_branch:
            st.last_commit = backend.head_commit(repo, st.default_branch)
    except BackendError as exc:
        log.warning("%s : %s", repo, exc)
        st.error = str(exc)
        return st
    st.warning = backend.warning(repo)
    if target:
        st.deploy = deployed(st, target, backend)
    return st


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


def collect(demandes: list[Demande], backend: Backend) -> dict[Demande, RepoStatus]:
    return {d: status(d[0], d[1], backend) for d in dict.fromkeys(demandes)}


class EtatGitHub:
    """Cache de l'état des dépôts, rafraîchi en tâche de fond.

    `voir(demandes)` déclare les dépôts affichés et renvoie le dernier état
    connu de chacun (None tant qu'il n'a jamais été lu). Un nouveau dépôt
    déclenche une lecture sans attendre la fin de l'intervalle."""

    def __init__(self, backend_factory: Callable[[], Backend], intervalle: float = 60):
        self.factory = backend_factory
        self.intervalle = intervalle
        self.etats: dict[Demande, RepoStatus] = {}
        self.voulues: list[Demande] = []
        self._lock = threading.Lock()
        self._reveil = threading.Event()
        self._thread: threading.Thread | None = None

    def rafraichir(self) -> None:
        with self._lock:
            demandes = list(self.voulues)
        if not demandes:
            return
        etats = collect(demandes, self.factory())  # backend neuf : pas de cache HTTP périmé
        with self._lock:
            self.etats = etats

    def _boucle(self) -> None:
        while True:
            try:
                self.rafraichir()
            except Exception:  # la tâche de fond ne meurt jamais
                log.exception("lecture GitHub en échec")
            self._reveil.wait(self.intervalle)
            self._reveil.clear()

    def voir(self, demandes: list[Demande], synchrone: bool = False) -> dict[Demande, RepoStatus | None]:
        demandes = list(dict.fromkeys(demandes))
        with self._lock:
            nouvelles = any(d not in self.etats for d in demandes) and demandes != self.voulues
            self.voulues = demandes
        if synchrone:
            self.rafraichir()
        else:
            if self._thread is None:
                self._thread = threading.Thread(target=self._boucle, daemon=True, name="scope-github")
                self._thread.start()
            elif nouvelles:
                self._reveil.set()
        with self._lock:
            return {d: self.etats.get(d) for d in demandes}

