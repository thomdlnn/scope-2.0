"""Une demande = un rapport `.scope/rapports/*.md`, lu sur le disque.

Le parser accepte les clés et les titres en français et en anglais, ainsi que
l'ancien format (statut `bloque`, « Résumé court », « Prochaine étape »).

Règle d'or : ne jamais lever d'exception. Un rapport invalide devient une
`Demande(valide=False, erreur=...)`, affichée « illisible ».
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

EN_COURS, ATTENTE, TERMINE, ECHEC, ILLISIBLE = "en-cours", "attente", "termine", "echec", "illisible"
STATUTS = (EN_COURS, ATTENTE, TERMINE, ECHEC)
ACTIONS = ("code", "commit", "push", "pr", "deploy", "hors-depot")
QUESTION, REMARQUE = "question", "remarque"

#: Taille maximale d'un rapport lu (au-delà : illisible).
TAILLE_MAX = 256 * 1024

FILENAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})(\d{2})-[A-Za-z0-9][A-Za-z0-9_-]*\.md$")


def norm(text: Any) -> str:
    """Minuscules, sans accents, espaces et soulignés réduits à un tiret."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_]+", "-", text.strip().lower())


# Clés de l'en-tête : variante normalisée → clé canonique.
CLES = {
    "projet": "projet", "project": "projet",
    "repo": "repo", "depot": "repo", "repository": "repo",
    "agent": "agent",
    "branche": "branche", "branch": "branche",
    "demande": "demande", "request": "demande", "prompt": "demande",
    "statut": "statut", "status": "statut",
    "actions": "actions",
    "debut": "debut", "start": "debut", "started": "debut", "started-at": "debut",
    "maj": "maj", "mise-a-jour": "maj", "updated": "maj", "updated-at": "maj", "update": "maj",
    "pr": "pr", "pr-numero": "pr", "pr-number": "pr",
    "date": "date",
}

# Statuts : variante normalisée → statut canonique.
STATUT_ALIAS = {
    "en-cours": EN_COURS, "in-progress": EN_COURS, "running": EN_COURS, "working": EN_COURS,
    "attente": ATTENTE, "en-attente": ATTENTE, "waiting": ATTENTE, "bloque": ATTENTE, "blocked": ATTENTE,
    "termine": TERMINE, "done": TERMINE, "completed": TERMINE, "finished": TERMINE, "pr-ouverte": TERMINE,
    "echec": ECHEC, "failed": ECHEC, "failure": ECHEC, "error": ECHEC,
}

ACTION_ALIAS = {a: a for a in ACTIONS} | {
    "deploiement": "deploy", "deployment": "deploy", "hors-du-depot": "hors-depot",
    "outside-repo": "hors-depot", "external": "hors-depot", "pull-request": "pr",
}

# Titres de section : variante normalisée → section canonique.
SECTIONS = {
    "resume": "resume", "summary": "resume", "resume-court": "resume", "short-summary": "resume",
    "pour-vous": "pour_vous", "for-you": "pour_vous",
    "prochaine-etape": "pour_vous", "next-step": "pour_vous", "next-steps": "pour_vous",
    "detail": "detail", "details": "detail",
}

PREFIXES = {
    "question": QUESTION, "q": QUESTION,
    "remarque": REMARQUE, "remark": REMARQUE, "note": REMARQUE, "info": REMARQUE,
    "attention": REMARQUE, "warning": REMARQUE, "a-savoir": REMARQUE,
}
PREFIX_RE = re.compile(r"^\s*(?:\*\*|__)?([A-Za-zÀ-ÿ' -]{1,20}?)(?:\*\*|__)?\s*:\s*(?:\*\*|__)?\s*")
ITEM_RE = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?")


class RapportError(ValueError):
    pass


@dataclass
class Point:
    """Un élément de « Pour vous » : question ou remarque (Markdown)."""

    nature: str  # question | remarque
    texte: str


@dataclass
class Demande:
    chemin: Path  # fichier sur le disque
    depot: str  # nom du dossier du dépôt
    depot_chemin: str  # chemin du dépôt, relatif à la racine SCOPE
    valide: bool = True
    erreur: str | None = None
    statut: str = ILLISIBLE
    projet: str | None = None
    repo: str | None = None  # valeur écrite par l'agent (affichage seulement)
    agent: str | None = None
    branche: str | None = None
    demande: str | None = None
    actions: list[str] = field(default_factory=list)
    debut: datetime | None = None
    maj: datetime | None = None
    pr: int | None = None
    resume: str | None = None
    points: list[Point] = field(default_factory=list)
    detail_md: str | None = None
    ancien_format: bool = False
    avertissements: list[str] = field(default_factory=list)
    attente_levee: bool = False  # ancien format : une réponse plus récente existe sur la branche

    @property
    def fichier(self) -> str:
        return self.chemin.name

    @property
    def questions(self) -> list[Point]:
        return [p for p in self.points if p.nature == QUESTION]

    @property
    def remarques(self) -> list[Point]:
        return [p for p in self.points if p.nature == REMARQUE]

    @property
    def date(self) -> datetime | None:
        """Date de tri : dernière mise à jour, sinon début."""
        return self.maj or self.debut

    @property
    def etat(self) -> str:
        """Statut affiché : une attente de l'ancien format levée devient « terminé »."""
        return TERMINE if self.attente_levee else self.statut

    @property
    def ident(self) -> str:
        """Identifiant HTML stable (ancres, sections dépliées conservées)."""
        h = hashlib.sha1(f"{self.depot_chemin}/{self.fichier}".encode()).hexdigest()[:8]
        stem = re.sub(r"[^A-Za-z0-9_-]", "-", self.fichier.removesuffix(".md"))
        return f"d-{stem}-{h}"

    def to_dict(self) -> dict[str, Any]:
        iso = lambda d: d.isoformat().replace("+00:00", "Z") if d else None  # noqa: E731
        return {
            "id": self.ident,
            "fichier": self.fichier,
            "depot": self.depot,
            "depot_chemin": self.depot_chemin,
            "valide": self.valide,
            "erreur": self.erreur,
            "statut": self.etat,
            "projet": self.projet,
            "repo": self.repo,
            "agent": self.agent,
            "branche": self.branche,
            "demande": self.demande,
            "actions": self.actions,
            "debut": iso(self.debut),
            "maj": iso(self.maj),
            "pr": self.pr,
            "resume": self.resume,
            "questions": [p.texte for p in self.questions],
            "remarques": [p.texte for p in self.remarques],
            "detail": self.detail_md,
            "ancien_format": self.ancien_format,
            "avertissements": self.avertissements,
        }


# --- Lecture -------------------------------------------------------------------
def date_from_filename(filename: str) -> datetime | None:
    m = FILENAME_RE.match(filename)
    if not m:
        return None
    try:
        return datetime(*(int(x) for x in m.groups()), tzinfo=timezone.utc)
    except ValueError:
        return None


def split_front_matter(text: str) -> tuple[dict, str]:
    text = text.lstrip("﻿")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise RapportError("en-tête YAML absent (le fichier doit commencer par ---)")
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            header, body = "\n".join(lines[1:i]), "\n".join(lines[i + 1 :])
            break
    else:
        raise RapportError("en-tête YAML non fermé (second '---' manquant)")
    try:
        data = yaml.safe_load(header) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (ligne {mark.line + 2})" if mark else ""
        raise RapportError(f"YAML invalide{where} : {getattr(exc, 'problem', exc)}") from None
    if not isinstance(data, dict):
        raise RapportError("l'en-tête YAML doit être un dictionnaire")
    return data, body


def split_sections(body: str) -> tuple[dict[str, str], set[str]]:
    """Sections connues (## …), et les titres normalisés rencontrés."""
    sections: dict[str, list[str]] = {}
    titres: set[str] = set()
    current: str | None = None
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        if not in_fence and re.match(r"^#{1,3} ", line):
            titre = norm(line.lstrip("#"))
            titres.add(titre)
            current = SECTIONS.get(titre)
            if current:
                sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}, titres


def parse_points(md: str | None, defaut: str = REMARQUE) -> list[Point]:
    """Découpe « Pour vous » en points. Chaque élément de liste (ou paragraphe)
    est une question s'il commence par « Question : », une remarque sinon."""
    if not md:
        return []
    blocs: list[list[str]] = []
    in_fence = False
    for line in md.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        if not in_fence and ITEM_RE.match(line):
            blocs.append([ITEM_RE.sub("", line, count=1)])
        elif not in_fence and not line.strip():
            if blocs and blocs[-1] and blocs[-1][-1] != "":
                blocs[-1].append("")
        elif blocs and (in_fence or line.startswith((" ", "\t")) or blocs[-1][-1] != ""):
            blocs[-1].append(line.strip() if not in_fence else line)
        else:
            blocs.append([line.strip()])
    points = []
    for bloc in blocs:
        texte = "\n".join(bloc).strip()
        if not texte:
            continue
        nature = defaut
        m = PREFIX_RE.match(texte)
        if m and norm(m.group(1)) in PREFIXES:
            nature = PREFIXES[norm(m.group(1))]
            texte = texte[m.end() :].strip()
        if texte:
            points.append(Point(nature, texte))
    return points


def _date(value: Any, champ: str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            raise RapportError(f"{champ} invalide : {value!r} (ISO 8601 attendu)") from None
    else:
        raise RapportError(f"{champ} invalide : {value!r} (ISO 8601 attendu)")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _str(v: Any) -> str | None:
    if v is None:
        return None
    return " ".join(str(v).split()) or None


def _actions(raw: Any, avert: list[str]) -> list[str]:
    if raw in (None, ""):
        return []
    items = raw if isinstance(raw, list) else re.split(r"[,\s]+", str(raw))
    out = []
    for it in items:
        if it in (None, ""):
            continue
        a = ACTION_ALIAS.get(norm(it))
        if a is None:
            avert.append(f"action inconnue ignorée : {it}")
        elif a not in out:
            out.append(a)
    return [a for a in ACTIONS if a in out]


def lire(chemin: Path, depot: str, depot_chemin: str) -> Demande:
    """Lit un rapport sur le disque. Ne lève jamais d'exception."""
    d = Demande(chemin=chemin, depot=depot, depot_chemin=depot_chemin)
    try:
        if chemin.stat().st_size > TAILLE_MAX:
            raise RapportError(f"fichier trop gros (> {TAILLE_MAX // 1024} Ko)")
        text = chemin.read_text(encoding="utf-8")
        _parse(d, text)
    except (RapportError, UnicodeDecodeError, OSError) as exc:
        _invalide(d, str(exc))
    except Exception as exc:  # garde-fou : un rapport ne casse jamais la génération
        _invalide(d, f"erreur inattendue : {type(exc).__name__}: {exc}")
    return d


def _invalide(d: Demande, erreur: str) -> None:
    d.valide, d.erreur, d.statut = False, erreur, ILLISIBLE
    d.points, d.actions = [], []
    d.debut = d.maj = date_from_filename(d.fichier) or _mtime(d.chemin)


def _mtime(p: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
    except OSError:
        return None


def _parse(d: Demande, text: str) -> None:
    raw, body = split_front_matter(text)
    data: dict[str, Any] = {}
    for k, v in raw.items():
        canon = CLES.get(norm(k))
        if canon and canon not in data:
            data[canon] = v

    if data.get("statut") in (None, ""):
        raise RapportError("champ « statut » (status) manquant")
    brut = norm(data["statut"])
    statut = STATUT_ALIAS.get(brut)
    if statut is None:
        raise RapportError(
            f"statut inconnu : {data['statut']!r} (attendu : en-cours | attente | termine | echec)"
        )

    sections, titres = split_sections(body)
    d.ancien_format = (
        brut in ("bloque", "pr-ouverte")
        or "resume-court" in titres
        or "prochaine-etape" in titres
        or ("date" in data and "maj" not in data and "debut" not in data)
    )
    resume = sections.get("resume") or _str(data.get("demande"))
    if not resume:
        raise RapportError("section « ## Résumé » (Summary) manquante ou vide")

    d.statut = statut
    d.projet = _str(data.get("projet"))
    d.repo = _str(data.get("repo"))
    d.agent = _str(data.get("agent"))
    d.branche = _str(data.get("branche"))
    d.demande = _str(data.get("demande"))
    d.resume = " ".join(resume.split())
    d.detail_md = sections.get("detail") or None
    d.actions = _actions(data.get("actions"), d.avertissements)
    if brut == "pr-ouverte" and "pr" not in d.actions:
        d.actions = [a for a in ACTIONS if a in {*d.actions, "pr"}]

    pr = data.get("pr")
    if pr not in (None, ""):
        try:
            d.pr = int(str(pr).strip().lstrip("#"))
        except ValueError:
            d.avertissements.append(f"numéro de PR invalide ignoré : {pr}")

    ancienne_date = _date(data["date"], "date") if data.get("date") not in (None, "") else None
    d.debut = _date(data["debut"], "debut") if data.get("debut") not in (None, "") else None
    d.maj = _date(data["maj"], "maj") if data.get("maj") not in (None, "") else None
    d.debut = d.debut or ancienne_date or date_from_filename(d.fichier) or _mtime(d.chemin)
    d.maj = d.maj or ancienne_date or d.debut

    # Ancien format : en attente, tout « Prochaine étape » est ce que l'humain doit faire.
    defaut = QUESTION if (d.ancien_format and statut == ATTENTE) else REMARQUE
    d.points = parse_points(sections.get("pour_vous"), defaut)
    if statut == ATTENTE and not d.questions:
        d.avertissements.append("statut « attente » sans question dans « Pour vous »")
    if statut != ATTENTE and d.questions:
        d.avertissements.append(f"question présente mais statut « {statut} »")
