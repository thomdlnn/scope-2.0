"""Découverte des rapports sur le disque et regroupement par projet.

SCOPE parcourt un dossier racine (SCOPE_ROOT) sur quelques niveaux, repère les
dépôts git (dossier contenant `.git`) et lit leurs `.scope/rapports/*.md` tels
qu'ils sont dans l'arbre de travail : les rapports ne sont pas commités.

Projet d'un rapport : champ `projet` du rapport, sinon `.scope/projet` du dépôt
(écrit par `./scope.sh init`), sinon le nom du dossier du dépôt.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .demandes import ATTENTE, ECHEC, EN_COURS, ILLISIBLE, TERMINE, Demande, lire, norm
from .models import Project, RepoStatus

log = logging.getLogger(__name__)

GITHUB_RE = re.compile(r"github\.com[:/]+([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/*$")
RAPPORTS = Path(".scope") / "rapports"
FICHIER_PROJET = Path(".scope") / "projet"
PROFONDEUR = 4
#: Dossiers jamais parcourus (en plus des dossiers cachés).
IGNORES = {"node_modules", "venv", "__pycache__", "target", "dist", "build", "vendor", "site-packages"}
#: Noms de dossiers déjà pris dans le site.
RESERVES = {"assets"}
#: Au-delà, une demande en cours est signalée « sans nouvelles ».
SILENCE = timedelta(hours=1)
#: Fenêtre des demandes terminées ou en échec affichées.
RECENTES = timedelta(days=7)


@dataclass
class Depot:
    nom: str  # nom du dossier
    chemin: Path  # chemin absolu
    relatif: str  # chemin relatif à la racine (affichage)
    projet: str | None = None  # contenu de .scope/projet
    github: str | None = None  # owner/repo du remote origin, s'il est sur GitHub


@dataclass
class Projet:
    slug: str
    titre: str
    depots: list[Depot] = field(default_factory=list)
    demandes: list[Demande] = field(default_factory=list)
    reglages: Project | None = None  # projects/<projet>.yml (optionnel)
    #: (owner/repo, état) ; None sans token GitHub, état None tant qu'il n'est pas lu
    etats: list[tuple[str, RepoStatus | None]] | None = None

    @property
    def repos_github(self) -> list[str]:
        return sorted({d.github for d in self.depots if d.github})

    @property
    def sans_github(self) -> list[Depot]:
        return [d for d in self.depots if not d.github]

    @property
    def prs_ouvertes(self) -> int | None:
        if self.etats is None:
            return None
        return sum(len(st.prs) for _r, st in self.etats if st and st.prs)

    def _valides(self, *etats: str) -> list[Demande]:
        return [d for d in self.demandes if d.valide and d.etat in etats]

    @property
    def attente(self) -> list[Demande]:
        return self._valides(ATTENTE)

    @property
    def en_cours(self) -> list[Demande]:
        return self._valides(EN_COURS)

    def recentes(self, maintenant: datetime) -> list[Demande]:
        return [d for d in self._valides(TERMINE, ECHEC) if d.date and maintenant - d.date <= RECENTES]

    def anciennes(self, maintenant: datetime) -> list[Demande]:
        recentes = {id(d) for d in self.recentes(maintenant)}
        return [d for d in self._valides(TERMINE, ECHEC) if id(d) not in recentes]

    @property
    def illisibles(self) -> list[Demande]:
        return [d for d in self.demandes if d.statut == ILLISIBLE]

    @property
    def derniere(self) -> datetime | None:
        dates = [d.date for d in self.demandes if d.date]
        return max(dates) if dates else None


def decouvrir(racine: Path, profondeur: int = PROFONDEUR) -> list[Depot]:
    """Dépôts git sous `racine`, jusqu'à `profondeur` niveaux. Un dépôt n'est
    pas parcouru plus profondément (sous-modules ignorés)."""
    racine = racine.expanduser()
    depots: list[Depot] = []
    if not racine.is_dir():
        log.warning("racine introuvable : %s", racine)
        return depots

    def visiter(d: Path, niveau: int) -> None:
        if (d / ".git").exists():
            rel = d.relative_to(racine).as_posix() if d != racine else d.name
            depots.append(Depot(nom=d.name, chemin=d, relatif=rel, projet=_lire_projet(d), github=origine_github(d)))
            return
        if niveau >= profondeur:
            return
        try:
            enfants = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            return
        for e in enfants:
            if e.name.startswith(".") or e.name in IGNORES:
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    visiter(Path(e.path), niveau + 1)
            except OSError:
                continue

    visiter(racine, 0)
    return depots


def _lire_projet(d: Path) -> str | None:
    try:
        ligne = (d / FICHIER_PROJET).read_text(encoding="utf-8").strip().splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    return ligne[0].strip() if ligne and ligne[0].strip() else None


def lire_demandes(depot: Depot) -> list[Demande]:
    dossier = depot.chemin / RAPPORTS
    try:
        fichiers = sorted(p for p in dossier.glob("*.md") if p.is_file())
    except OSError:
        return []
    out = []
    for p in fichiers:
        d = lire(p, depot.nom, depot.relatif)
        if d.valide and not d.branche:
            d.branche = branche_courante(depot.chemin)
        out.append(d)
    return out


def _gitdir(depot: Path) -> Path:
    git = depot / ".git"
    if git.is_file():  # worktree : « gitdir: <chemin> »
        cible = git.read_text(encoding="utf-8").strip().removeprefix("gitdir:").strip()
        git = (depot / cible).resolve()
    return git


def branche_courante(depot: Path) -> str | None:
    """Branche courante, lue dans .git/HEAD (sans appeler git)."""
    try:
        head = (_gitdir(depot) / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return head.removeprefix("ref: refs/heads/") if head.startswith("ref: ") else None


def origine_github(depot: Path) -> str | None:
    """owner/repo du remote origin s'il pointe vers GitHub (lu dans .git/config,
    sans appeler git). D'éventuels identifiants dans l'URL ne sont jamais gardés."""
    try:
        gitdir = _gitdir(depot)
        common = gitdir / "commondir"  # worktree : la config est dans le dépôt principal
        if common.is_file():
            gitdir = (gitdir / common.read_text(encoding="utf-8").strip()).resolve()
        lignes = (gitdir / "config").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    section = None
    for ligne in lignes:
        ligne = ligne.strip()
        if ligne.startswith("["):
            section = re.sub(r"\s+", " ", ligne.strip("[]")).lower()
            continue
        if section == 'remote "origin"' and "=" in ligne:
            cle, _, valeur = ligne.partition("=")
            if cle.strip().lower() == "url":
                m = GITHUB_RE.search(valeur.strip().strip('"'))
                return f"{m.group(1)}/{m.group(2)}" if m else None
    return None


def slug(nom: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", norm(nom)).strip("-") or "projet"
    return f"{s}-projet" if s in RESERVES else s


def lever_attentes_anciennes(demandes: list[Demande]) -> None:
    """Ancien format (un rapport par réponse) : un rapport `bloque` n'est en
    attente que s'il est le plus récent du dépôt. Toutes les branches partagent
    le même dossier sur le disque : tout rapport plus récent lève l'attente."""
    datees = [d for d in demandes if d.valide and d.date]
    if not datees:
        return
    dernier = max(datees, key=lambda d: (d.date, d.fichier))
    for d in demandes:
        if d.ancien_format and d.statut == ATTENTE and d is not dernier:
            d.attente_levee = True


def collecter(racine: Path, profondeur: int = PROFONDEUR) -> list[Projet]:
    """Parcourt la racine et renvoie les projets, triés par nom. Un dépôt sans
    rapport n'apparaît que s'il a été initialisé (.scope/projet)."""
    projets: dict[str, Projet] = {}

    def projet(nom: str) -> Projet:
        s = slug(nom)
        if s not in projets:
            projets[s] = Projet(slug=s, titre=nom)
        return projets[s]

    for depot in decouvrir(racine, profondeur):
        demandes = lire_demandes(depot)
        lever_attentes_anciennes(demandes)
        defaut = depot.projet or depot.nom
        if depot.projet:
            projet(depot.projet)
        for d in demandes:
            p = projet(d.projet or defaut)
            p.demandes.append(d)
            if depot not in p.depots:
                p.depots.append(depot)
        if depot.projet and depot not in projet(depot.projet).depots:
            projet(depot.projet).depots.append(depot)

    epoch = datetime.min.replace(tzinfo=timezone.utc)
    for p in projets.values():
        p.demandes.sort(key=lambda d: (d.date or epoch, d.fichier), reverse=True)
        p.depots.sort(key=lambda x: x.relatif)
    return sorted(projets.values(), key=lambda p: p.slug)


def silencieuse(d: Demande, maintenant: datetime) -> bool:
    return d.etat == EN_COURS and d.date is not None and maintenant - d.date > SILENCE
