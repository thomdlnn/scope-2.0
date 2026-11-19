"""Point d'entrée : python -m scope_gen.

Une fois :   python -m scope_gen --racine ~/Git --out site
En boucle :  python -m scope_gen --racine ~/Git --site /site --boucle 3 [--servir 8000]

En boucle, chaque cycle relit les rapports. Si l'affichage a changé, le site est
écrit dans <site>/build-<horodatage>, puis <site>/current est basculé d'un coup
(lien symbolique remplacé par rename) : le serveur ne sert jamais une page à
moitié écrite. Sinon, seul <site>/current/etat.json est rafraîchi (date de la
dernière vérification, lue par la page).
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import logging
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .backends import GitHubBackend
from .backends.github import API
from .config import load_projects
from .locale import PROFONDEUR, Projet, collecter
from .render import calculer_empreinte, ecrire_etat, write_site
from .sources import EtatGitHub

log = logging.getLogger("scope")
REPO_SCOPE = Path(__file__).resolve().parents[2]


@dataclass
class Config:
    racine: Path
    profondeur: int = PROFONDEUR
    projets: Path | None = None  # dossier des réglages optionnels projects/*.yml
    github: EtatGitHub | None = None  # None : pas de token, pas d'appel réseau


def github_depuis_env() -> EtatGitHub | None:
    """Un seul token, optionnel : SCOPE_GH_TOKEN (lecture seule)."""
    token = os.environ.get("SCOPE_GH_TOKEN", "").strip()
    if not token:
        return None
    api = os.environ.get("SCOPE_GH_API") or API
    intervalle = float(os.environ.get("SCOPE_GH_INTERVAL") or 60)
    return EtatGitHub(lambda: GitHubBackend(token, api=api), intervalle)


def preparer(cfg: Config, synchrone: bool = False) -> tuple[list[Projet], list[str]]:
    """Projets lus sur le disque, complétés des réglages et de l'état GitHub."""
    projets = collecter(cfg.racine, cfg.profondeur)
    reglages, erreurs = load_projects(cfg.projets)
    for p in projets:
        p.reglages = reglages.get(p.slug)
    if cfg.github is not None:
        par_projet = {}
        for p in projets:
            cibles = p.reglages.deploiements if p.reglages else {}
            par_projet[p.slug] = [(r, cibles.get(r)) for r in p.repos_github]
        etats = cfg.github.voir([d for ds in par_projet.values() for d in ds], synchrone)
        for p in projets:
            p.etats = [(d[0], etats.get(d)) for d in par_projet[p.slug]]
    return projets, erreurs


def generer(cfg: Config, out: Path) -> str:
    """Génère le site une fois dans `out` (écrasé)."""
    projets, erreurs = preparer(cfg, synchrone=True)
    if out.exists():
        shutil.rmtree(out)
    emp = write_site(out, projets, alertes=erreurs)
    n = sum(len(p.demandes) for p in projets)
    print(f"site généré dans {out}/ : {len(projets)} projet(s), {n} demande(s)")
    return emp


def empreinte_courante(site: Path) -> str | None:
    try:
        return json.loads((site / "current" / "etat.json").read_text(encoding="utf-8")).get("empreinte")
    except (OSError, ValueError):
        return None


def cycle(site: Path, cfg: Config, intervalle: float) -> bool:
    """Un cycle de la boucle. Renvoie True si le site a été rebasculé."""
    maintenant = datetime.now(timezone.utc)
    projets, erreurs = preparer(cfg)
    emp = calculer_empreinte(projets, maintenant, erreurs)
    current = site / "current"
    if emp == empreinte_courante(site):
        ecrire_etat(current, emp, maintenant, intervalle)
        return False
    build = site / f"build-{maintenant.strftime('%Y%m%d%H%M%S%f')}"
    write_site(build, projets, maintenant, emp, intervalle, erreurs)
    tmp = site / ".current.tmp"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    precedent = os.readlink(current) if current.is_symlink() else None
    os.symlink(build.name, tmp)
    os.replace(tmp, current)
    # Le build précédent est gardé jusqu'à la bascule suivante : une requête
    # en cours de lecture n'y trouve jamais un fichier supprimé.
    for old in site.glob("build-*"):
        if old.name not in (build.name, precedent) and old.is_dir():
            shutil.rmtree(old, ignore_errors=True)
    log.info("site mis à jour (%s)", emp)
    return True


def boucle(site: Path, cfg: Config, intervalle: float, tours: int | None = None) -> None:
    site.mkdir(parents=True, exist_ok=True)
    n = 0
    while tours is None or n < tours:
        try:
            cycle(site, cfg, intervalle)
        except Exception:  # la boucle ne s'arrête jamais : la version précédente reste en ligne
            log.exception("génération en échec : la version précédente reste en ligne")
        n += 1
        if tours is None or n < tours:
            time.sleep(intervalle)


class _Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args):  # silencieux
        pass


def servir(site: Path, port: int) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(_Handler, directory=str(site / "current"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scope_gen", description="Génère le site statique SCOPE.")
    ap.add_argument("--racine", type=Path, default=Path(os.environ.get("SCOPE_ROOT") or "~/Git"),
                    help="dossier parcouru à la recherche des dépôts (SCOPE_ROOT, défaut ~/Git)")
    ap.add_argument("--profondeur", type=int, default=int(os.environ.get("SCOPE_DEPTH") or PROFONDEUR),
                    help=f"niveaux de dossiers parcourus (SCOPE_DEPTH, défaut {PROFONDEUR})")
    ap.add_argument("--projets", type=Path,
                    default=Path(os.environ.get("SCOPE_PROJECTS") or REPO_SCOPE / "projects"),
                    help="réglages optionnels projects/*.yml (SCOPE_PROJECTS)")
    ap.add_argument("--out", type=Path, help="génère une fois dans ce dossier (écrasé)")
    ap.add_argument("--site", type=Path, help="dossier du site en boucle (site/current = version servie)")
    ap.add_argument("--boucle", type=float, nargs="?", const=float(os.environ.get("SCOPE_INTERVAL") or 3),
                    metavar="SECONDES", help="régénère en boucle (SCOPE_INTERVAL, défaut 3 s)")
    ap.add_argument("--servir", type=int, metavar="PORT", help="sert <site>/current sur 127.0.0.1:PORT")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    racine = args.racine.expanduser()
    cfg = Config(racine, args.profondeur, args.projets, github_depuis_env())

    if args.boucle is None:
        generer(cfg, args.out or Path("site"))
        return 0
    if not args.site:
        ap.error("--boucle demande --site")
    if args.boucle <= 0:
        ap.error("--boucle : intervalle > 0 attendu")
    gh = f", GitHub toutes les {cfg.github.intervalle:g} s" if cfg.github else ", sans token GitHub"
    print(f"SCOPE : lecture de {racine} toutes les {args.boucle:g} s{gh}", flush=True)
    if args.servir:
        args.site.mkdir(parents=True, exist_ok=True)
        cycle(args.site, cfg, args.boucle)
        servir(args.site, args.servir)
        print(f"Aperçu : http://localhost:{args.servir}  (Ctrl+C pour arrêter)", flush=True)
    try:
        boucle(args.site, cfg, args.boucle)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
