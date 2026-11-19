"""Réglages optionnels des projets : projects/<projet>.yml.

Les dépôts d'un projet sont déduits des clones trouvés sur le disque ; le
fichier ne sert qu'à ce qui ne peut pas l'être :

    deploiements:                      # version déployée (dépôt GitOps suivi par ArgoCD)
      owner/app:
        depot: owner/app-deploy
        fichier: environments/local/app.yaml
        cle: image.tag                 # optionnel (défaut image.tag)
        environnement: local           # optionnel (défaut local)
        ref: develop                   # optionnel (défaut : branche par défaut)
    sante: http://app.local/health     # état de l'application, appelé par le navigateur

Le nom du fichier (ou `name:`) est le nom du projet, comparé sans casse ni accents.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .models import DeployTarget, Project

REPO_RE = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")


class ConfigError(ValueError):
    pass


def load_project(path: Path) -> Project:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: YAML invalide : {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: un dictionnaire YAML est attendu")
    sante = data.get("sante")
    if isinstance(sante, dict):
        sante = sante.get("url")
    if sante is not None and not re.match(r"^https?://[^\s\"'<>]+$", str(sante)):
        raise ConfigError(f"{path}: sante doit être une URL http(s), ex. http://app.local/health")
    return Project(
        name=str(data.get("name") or path.stem),
        deploiements=_load_deploiements(path, data.get("deploiements") or {}),
        sante=str(sante) if sante else None,
    )


def _load_deploiements(path: Path, raw) -> dict[str, DeployTarget]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: 'deploiements' doit être un dictionnaire owner/repo → cible")
    out = {}
    for repo, cfg in raw.items():
        if not REPO_RE.match(str(repo)):
            raise ConfigError(f"{path}: deploiements.{repo} : dépôt invalide (format owner/repo)")
        if not isinstance(cfg, dict) or not cfg.get("depot") or not cfg.get("fichier"):
            raise ConfigError(f"{path}: deploiements.{repo} : 'depot' et 'fichier' sont obligatoires")
        if not REPO_RE.match(str(cfg["depot"])):
            raise ConfigError(f"{path}: deploiements.{repo}.depot invalide (format owner/repo)")
        out[str(repo)] = DeployTarget(
            depot=str(cfg["depot"]),
            fichier=str(cfg["fichier"]),
            cle=str(cfg.get("cle") or "image.tag"),
            environnement=str(cfg.get("environnement") or "local"),
            ref=str(cfg["ref"]) if cfg.get("ref") else None,
        )
    return out


def load_projects(directory: Path | None) -> tuple[dict[str, Project], list[str]]:
    """Réglages par nom de projet (slug), et erreurs. Un fichier invalide est
    signalé sans empêcher la génération."""
    from .locale import slug

    out: dict[str, Project] = {}
    erreurs: list[str] = []
    if not directory or not directory.is_dir():
        return out, erreurs
    for p in sorted(directory.glob("*.yml")):
        try:
            proj = load_project(p)
        except (ConfigError, OSError) as exc:
            erreurs.append(str(exc))
            continue
        out[slug(proj.name)] = proj
    return out, erreurs
