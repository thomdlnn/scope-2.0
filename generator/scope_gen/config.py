"""Lecture des projets (projects/*.yml)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .models import DeployTarget, Project

REPO_RE = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class ConfigError(ValueError):
    pass


def load_project(path: Path) -> Project:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: YAML invalide : {exc}") from None
    name = str(data.get("name") or path.stem)
    if not NAME_RE.match(name):
        raise ConfigError(f"{path}: name invalide {name!r} (minuscules, chiffres, tirets)")
    repos = data.get("repos") or []
    if not isinstance(repos, list) or not repos:
        raise ConfigError(f"{path}: 'repos' doit être une liste non vide de owner/repo")
    for r in repos:
        if not isinstance(r, str) or not REPO_RE.match(r):
            raise ConfigError(f"{path}: repo invalide {r!r} (format owner/repo)")
    token = data.get("token")
    if token is not None and not TOKEN_RE.match(str(token)):
        raise ConfigError(f"{path}: token invalide {token!r} (nom de secret, ex. SCOPE_TOKEN_{name.upper().replace('-', '_')})")
    sante = data.get("sante")
    if isinstance(sante, dict):
        sante = sante.get("url")
    if sante is not None and not re.match(r"^https?://[^\s\"'<>]+$", str(sante)):
        raise ConfigError(f"{path}: sante doit être une URL http(s), ex. http://app.local/health")
    return Project(
        sante=str(sante) if sante else None,
        token=str(token) if token else None,
        name=name,
        title=str(data.get("title") or name),
        repos=list(repos),
        deploiements=_load_deploiements(path, data.get("deploiements") or {}, repos),
    )


def _load_deploiements(path: Path, raw, repos: list[str]) -> dict[str, DeployTarget]:
    """deploiements:
      owner/app:                       # un dépôt du projet
        depot: owner/app-deploy        # dépôt GitOps suivi par ArgoCD
        fichier: environments/local/app.yaml
        cle: image.tag                 # optionnel (défaut image.tag)
        environnement: local           # optionnel (défaut local)
        ref: develop                   # optionnel (défaut : branche par défaut)
    """
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: 'deploiements' doit être un dictionnaire owner/repo → cible")
    out = {}
    for repo, cfg in raw.items():
        if repo not in repos:
            raise ConfigError(f"{path}: deploiements.{repo} : dépôt absent de 'repos'")
        if not isinstance(cfg, dict) or not cfg.get("depot") or not cfg.get("fichier"):
            raise ConfigError(f"{path}: deploiements.{repo} : 'depot' et 'fichier' sont obligatoires")
        if not REPO_RE.match(str(cfg["depot"])):
            raise ConfigError(f"{path}: deploiements.{repo}.depot invalide (format owner/repo)")
        out[repo] = DeployTarget(
            depot=str(cfg["depot"]),
            fichier=str(cfg["fichier"]),
            cle=str(cfg.get("cle") or "image.tag"),
            environnement=str(cfg.get("environnement") or "local"),
            ref=str(cfg["ref"]) if cfg.get("ref") else None,
        )
    return out


def load_projects(directory: Path) -> list[Project]:
    projects = [load_project(p) for p in sorted(directory.glob("*.yml"))]
    names = [p.name for p in projects]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        raise ConfigError(f"noms de projets en double : {', '.join(sorted(dup))}")
    return projects
