"""Interface d'une source de données.

Une source collecte une famille de données pour un projet (les rapports
aujourd'hui ; demain les PR ouvertes, les déploiements, la santé…). Pour en
ajouter une : créer une classe `Source`, l'ajouter à `SOURCES` dans
`sources/__init__.py`, puis afficher son résultat dans `render.py`.
Le résultat est aussi exporté tel quel dans data.json (clé = `name`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..backends import Backend
from ..models import Project


class Source(ABC):
    #: clé du résultat dans ProjectData.sources et dans data.json
    name: str

    @abstractmethod
    def collect(self, project: Project, backend: Backend) -> Any:
        """Collecte les données du projet. Ne doit pas lever pour une erreur
        propre à un dépôt : la consigner dans le résultat."""

    def to_json(self, result: Any) -> Any:
        return result
