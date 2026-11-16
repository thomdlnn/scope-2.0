"""Point d'entrée : python -m scope_gen [--local DOSSIER] [--projects DIR] [--out DIR]."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path

from .backends import Backend, GitHubBackend, LocalBackend
from .config import ConfigError, load_projects
from .models import Project
from .render import ProjectData, write_site
from .sources import SOURCES

log = logging.getLogger("scope")


def secret(name: str) -> str | None:
    """Valeur d'un token : variable d'environnement, ou secret GitHub transmis
    en bloc par l'Action (SCOPE_SECRETS = toJSON(secrets))."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        return json.loads(os.environ.get("SCOPE_SECRETS") or "{}").get(name) or None
    except ValueError:
        return None


def github_backend_factory() -> Callable[[Project], Backend]:
    """Un backend GitHub par token : le token dédié du projet s'il en a un,
    sinon le token global (SCOPE_GH_TOKEN, à défaut GITHUB_TOKEN)."""
    global_token = secret("SCOPE_GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    cache: dict[str | None, Backend] = {}

    def for_project(project: Project) -> Backend:
        token = global_token
        if project.token:
            token = secret(project.token)
            if not token:
                log.warning("%s : secret %s introuvable, token global utilisé", project.name, project.token)
                token = global_token
        if token not in cache:
            cache[token] = GitHubBackend(token)
        return cache[token]

    if not global_token:
        log.warning("aucun token global (SCOPE_GH_TOKEN) : seuls les dépôts publics et ceux des tokens dédiés seront lisibles")
    return for_project


def build(
    projects_dir: Path,
    out: Path,
    backend: Backend | Callable[[Project], Backend],
    sources=SOURCES,
) -> list[ProjectData]:
    projects = load_projects(projects_dir)
    backend_for = backend if callable(backend) and not isinstance(backend, Backend) else (lambda _p: backend)
    data = []
    for project in projects:
        pd = ProjectData(project)
        b = backend_for(project)
        for source in sources:
            log.info("%s : collecte %s", project.name, source.name)
            pd.sources[source.name] = source.collect(project, b)
        data.append(pd)
    write_site(out, data, sources)
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scope_gen", description="Génère le site statique SCOPE.")
    ap.add_argument("--projects", type=Path, default=Path("projects"), help="dossier des projets *.yml")
    ap.add_argument("--out", type=Path, default=Path("site"), help="dossier de sortie (écrasé)")
    ap.add_argument(
        "--local",
        type=Path,
        metavar="DOSSIER",
        help="lit des clones locaux (DOSSIER/<repo>) au lieu de l'API GitHub",
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    backend = LocalBackend(args.local) if args.local else github_backend_factory()
    try:
        data = build(args.projects, args.out, backend)
    except ConfigError as exc:
        print(f"erreur de configuration : {exc}", file=sys.stderr)
        return 2
    total = sum(len(pd.rapports.reports) for pd in data)
    errors = sum(len(pd.rapports.errors) for pd in data)
    print(f"site généré dans {args.out}/ : {len(data)} projet(s), {total} rapport(s), {errors} dépôt(s) en erreur")
    return 0
