"""Parsing des rapports .scope/rapports/*.md.

Règle d'or : ne jamais lever d'exception. Un rapport invalide devient un
`Report(valid=False, error=...)`, affiché comme « rapport illisible ».
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

import yaml

from .models import STATUTS, RawReport, Report

CHAMPS_OBLIGATOIRES = ("date", "projet", "repo", "agent", "statut")
FILENAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})(\d{2})-[a-z0-9][a-z0-9-]*\.md$")

SECTIONS = {
    "resume court": "resume",
    "detail": "detail_md",
    "prochaine etape": "prochaine_etape_md",
}


class ReportError(ValueError):
    pass


def date_from_filename(filename: str) -> datetime | None:
    m = FILENAME_RE.match(filename)
    if not m:
        return None
    try:
        return datetime(*(int(x) for x in m.groups()), tzinfo=timezone.utc)
    except ValueError:
        return None


def _normalize_heading(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def split_front_matter(text: str) -> tuple[dict, str]:
    text = text.lstrip("﻿")
    if not text.startswith("---"):
        raise ReportError("en-tête YAML absent (le fichier doit commencer par ---)")
    lines = text.splitlines()
    if lines[0].strip() != "---":
        raise ReportError("première ligne invalide : '---' attendu")
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            header = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            break
    else:
        raise ReportError("en-tête YAML non fermé (second '---' manquant)")
    try:
        data = yaml.safe_load(header) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (ligne {mark.line + 2})" if mark else ""
        raise ReportError(f"YAML invalide{where} : {getattr(exc, 'problem', exc)}") from None
    if not isinstance(data, dict):
        raise ReportError("l'en-tête YAML doit être un dictionnaire")
    return data, body


def split_sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            key = SECTIONS.get(_normalize_heading(line[3:]))
            current = key
            if key:
                sections.setdefault(key, [])
            continue
        if current:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _parse_date(value) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ReportError(f"date invalide : {value!r} (ISO 8601 attendu)") from None
    else:
        raise ReportError(f"date invalide : {value!r} (ISO 8601 attendu)")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _opt_str(data: dict, key: str) -> str | None:
    v = data.get(key)
    if v is None:
        return None
    return str(v).strip() or None


def parse_report(raw: RawReport) -> Report:
    """Transforme un fichier brut en Report. Ne lève jamais d'exception."""
    base = dict(repo=raw.repo, path=raw.path, ref=raw.ref)
    try:
        return _parse(raw, base)
    except ReportError as exc:
        return Report(**base, valid=False, error=str(exc), date=date_from_filename(raw.filename))
    except Exception as exc:  # garde-fou : un rapport ne casse jamais la génération
        return Report(
            **base,
            valid=False,
            error=f"erreur inattendue : {type(exc).__name__}: {exc}",
            date=date_from_filename(raw.filename),
        )


def _parse(raw: RawReport, base: dict) -> Report:
    data, body = split_front_matter(raw.content)
    manquants = [k for k in CHAMPS_OBLIGATOIRES if data.get(k) in (None, "")]
    if manquants:
        raise ReportError("champs obligatoires manquants : " + ", ".join(manquants))

    statut = str(data["statut"]).strip()
    if statut not in STATUTS:
        raise ReportError(f"statut inconnu : {statut!r} (attendu : {' | '.join(STATUTS)})")

    pr_numero = data.get("pr_numero")
    if pr_numero not in (None, ""):
        try:
            pr_numero = int(str(pr_numero).lstrip("#"))
        except ValueError:
            raise ReportError(f"pr_numero invalide : {pr_numero!r}") from None
    else:
        pr_numero = None

    sections = split_sections(body)
    resume = sections.get("resume")
    if not resume:
        raise ReportError("section « ## Résumé court » manquante ou vide")

    known = set(CHAMPS_OBLIGATOIRES) | {"branche", "commit_message", "pr_titre", "pr_numero"}
    extra = {k: v for k, v in data.items() if k not in known}

    return Report(
        **base,
        valid=True,
        date=_parse_date(data["date"]),
        projet=_opt_str(data, "projet"),
        agent=_opt_str(data, "agent"),
        branche=_opt_str(data, "branche"),
        statut=statut,
        commit_message=_opt_str(data, "commit_message"),
        pr_titre=_opt_str(data, "pr_titre"),
        pr_numero=pr_numero,
        resume=" ".join(resume.split()),
        detail_md=sections.get("detail_md") or None,
        prochaine_etape_md=sections.get("prochaine_etape_md") or None,
        extra={k: v if isinstance(v, (str, int, float, bool, type(None))) else str(v) for k, v in extra.items()},
    )


def dedupe(raws: list[RawReport]) -> list[RawReport]:
    """Dédoublonne par (repo, nom de fichier). Le premier vu gagne : les
    backends listent la branche par défaut en premier."""
    seen: set[tuple[str, str]] = set()
    out = []
    for r in raws:
        key = (r.repo, r.filename)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out
