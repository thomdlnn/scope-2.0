"""Source « rapports » : lit .scope/rapports/ et relie chaque rapport à son
commit et à sa PR."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..backends import Backend, BackendError
from ..models import STATUT_ILLISIBLE, Project, PullRequestInfo, Report
from ..parser import dedupe, parse_report
from .base import Source

log = logging.getLogger(__name__)
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


@dataclass
class ReportsResult:
    reports: list[Report] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # erreurs d'accès aux dépôts

    def count(self, *statuts: str) -> int:
        return sum(1 for r in self.reports if r.statut in statuts)

    @property
    def last_date(self) -> datetime | None:
        dates = [r.date for r in self.reports if r.date]
        return max(dates) if dates else None

    @property
    def latest(self) -> Report | None:
        """Le rapport valide le plus récent (celui du dernier prompt)."""
        valid = [r for r in self.reports if r.valid and r.date]
        return max(valid, key=lambda r: (r.date, r.filename)) if valid else None


class ReportsSource(Source):
    name = "rapports"

    def collect(self, project: Project, backend: Backend) -> ReportsResult:
        result = ReportsResult()
        for repo in project.repos:
            try:
                raws = dedupe(backend.list_reports(repo))
            except BackendError as exc:
                log.warning("%s : %s", repo, exc)
                result.errors.append(f"{repo} : {exc}")
                continue
            for raw in raws:
                report = parse_report(raw)
                if report.valid:
                    self.enrich(report, backend)
                result.reports.append(report)
        result.reports.sort(key=lambda r: (r.date or _EPOCH, r.filename), reverse=True)
        return result

    @staticmethod
    def enrich(report: Report, backend: Backend) -> None:
        """Résout le commit (celui qui a ajouté le fichier) et la PR associée.
        Les valeurs écrites par l'IA servent de secours."""
        try:
            report.commit = backend.commit_adding(report.repo, report.path, report.ref)
        except BackendError as exc:
            log.warning("%s %s : commit introuvable : %s", report.repo, report.filename, exc)
        if report.commit and not report.commit.message:
            report.commit.message = report.commit_message

        pr: PullRequestInfo | None = None
        try:
            if report.commit:
                prs = backend.pulls_for_commit(report.repo, report.commit.sha)
                pr = next((p for p in prs if p.number == report.pr_numero), prs[0] if prs else None)
            if pr is None and report.pr_numero:
                pr = backend.pull(report.repo, report.pr_numero)
        except BackendError as exc:
            log.warning("%s %s : PR introuvable : %s", report.repo, report.filename, exc)
        if pr is None and (report.pr_numero or report.pr_titre):
            pr = PullRequestInfo(
                number=report.pr_numero,
                title=report.pr_titre,
                state=None,
                url=backend.github_pr_url(report.repo, report.pr_numero) if report.pr_numero else None,
            )
        report.pr = pr

    def to_json(self, result: ReportsResult):
        return {
            "total": len(result.reports),
            "illisibles": result.count(STATUT_ILLISIBLE),
            "dernier_statut": result.latest.statut if result.latest else None,
            "erreurs": result.errors,
            "rapports": [r.to_dict() for r in result.reports],
        }
