"""Génération du site statique : index.html, <projet>/index.html, data.json."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from importlib import resources
from pathlib import Path
from string import Template
from typing import Any

from . import __version__
from .markdown_safe import render_markdown
from .models import STATUT_ILLISIBLE, STATUTS, Project, RepoStatus, Report
from .sources import ReportsResult

STATUT_LABELS = {
    "termine": "Terminé",
    "pr-ouverte": "PR ouverte",
    "bloque": "Bloqué",
    "echec": "Échec",
    STATUT_ILLISIBLE: "Illisible",
}
PR_STATE_LABELS = {"open": "ouverte", "merged": "mergée", "closed": "fermée"}


@dataclass
class ProjectData:
    project: Project
    sources: dict[str, Any] = field(default_factory=dict)

    @property
    def rapports(self) -> ReportsResult:
        return self.sources.get("rapports") or ReportsResult()

    @property
    def depots(self) -> list[RepoStatus]:
        return self.sources.get("depots") or []


def _tpl(name: str) -> Template:
    return Template(resources.files("scope_gen.templates").joinpath(name).read_text(encoding="utf-8"))


def e(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return '<span class="muted">date inconnue</span>'
    iso = dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    txt = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f'<time datetime="{e(iso)}">{e(txt)}</time>'


def render_inline(text: str | None) -> str:
    """Markdown d'une ligne (code, gras, liens), sans paragraphe englobant."""
    html = render_markdown(text)
    if html.startswith("<p>") and html.endswith("</p>") and html.count("<p>") == 1:
        html = html[3:-4]
    return html


def badge(statut: str) -> str:
    return f'<span class="badge s-{e(statut)}">{e(STATUT_LABELS.get(statut, statut))}</span>'


def refresh_html(generated: datetime) -> str:
    """Âge de la page + bouton qui recharge la page courante (filtres conservés).
    Sans JavaScript, le lien recharge simplement la page."""
    return (
        f'<span class="age">Mis à jour {fmt_dt(generated)}</span> '
        '<a class="refresh" id="refresh" href="" title="Recharger la page avec les dernières données '
        '(régénérées automatiquement toutes les 15 min)">Actualiser</a>'
    )


def page(title: str, body: str, root: str, generated: datetime, wide: bool = False) -> str:
    return _tpl("layout.html").substitute(
        refresh=refresh_html(generated),
        main_class="wide" if wide else "",
        title=e(title),
        body=body,
        root=root,
        generated=fmt_dt(generated),
        version=e(__version__),
    )


# --- Accueil ------------------------------------------------------------------
def render_home(projects: list[ProjectData], generated: datetime) -> str:
    rows = []
    for pd in projects:
        rr = pd.rapports
        latest = rr.latest
        illisibles = rr.count(STATUT_ILLISIBLE)
        extra = []
        if illisibles:
            extra.append(f'<span class="badge s-illisible">{illisibles} illisible(s)</span>')
        if rr.errors:
            extra.append(f'<span class="badge s-echec">{len(rr.errors)} dépôt(s) en erreur</span>')
        rows.append(
            f"""<li class="card project">
  <a class="project-link" href="{e(pd.project.name)}/">
    <h2>{e(pd.project.title)}</h2>
  </a>
  <dl class="stats">
    <div><dt>Rapports</dt><dd>{len(rr.reports)}</dd></div>
    <div><dt>Dernier prompt</dt><dd>{fmt_dt(latest.date) if latest else '<span class="muted">aucun</span>'}</dd></div>
    <div><dt>Statut</dt><dd>{badge(latest.statut) if latest else '<span class="muted">—</span>'}</dd></div>
  </dl>
  <p class="repos">{" ".join(f'<code>{e(r)}</code>' for r in pd.project.repos)}</p>
  {'<p class="badges">' + " ".join(extra) + "</p>" if extra else ""}
</li>"""
        )
    body = f"""<h1>Projets</h1>
<ul class="projects">
{"".join(rows) if rows else '<li class="empty">Aucun projet configuré (projects/*.yml).</li>'}
</ul>"""
    return page("SCOPE", body, ".", generated)


# --- Page projet --------------------------------------------------------------
def _commit_html(r: Report) -> str:
    c = r.commit
    if c:
        msg = c.message or r.commit_message or ""
        sha = f'<a href="{e(c.url)}" rel="noopener noreferrer" target="_blank"><code>{e(c.short)}</code></a>' if c.url else f"<code>{e(c.short)}</code>"
        return f'<div class="ref"><span class="k">Commit</span> {sha} <span class="v">{e(msg)}</span></div>'
    if r.commit_message:
        return f'<div class="ref"><span class="k">Commit</span> <span class="v">{e(r.commit_message)}</span> <span class="muted">(non résolu)</span></div>'
    return ""


def _pr_html(r: Report) -> str:
    p = r.pr
    if not p:
        return ""
    num = f"#{p.number}" if p.number else ""
    label = f"{num} {p.title or ''}".strip()
    link = (
        f'<a href="{e(p.url)}" rel="noopener noreferrer" target="_blank">{e(label)}</a>' if p.url else e(label)
    )
    state = (
        f'<span class="badge pr-{e(p.state)}">{e(PR_STATE_LABELS.get(p.state, p.state))}</span>'
        if p.state
        else '<span class="badge pr-unknown">état inconnu</span>'
    )
    return f'<div class="ref"><span class="k">PR</span> {link} {state}</div>'


def _report_html(r: Report) -> str:
    attrs = f'data-repo="{e(r.repo_name)}" data-statut="{e(r.statut)}"'
    file_url = f"https://github.com/{r.repo}/blob/{r.ref}/{r.path}"
    head = f"""<header class="meta">
    {fmt_dt(r.date)}
    <span class="repo">{e(r.repo_name)}</span>
    {f'<span class="agent">{e(r.agent)}</span>' if r.agent else ''}
    {badge(r.statut)}
  </header>"""
    if not r.valid:
        return f"""<article class="card report invalid" {attrs}>
  {head}
  <p class="summary">Rapport illisible : <a href="{e(file_url)}" rel="noopener noreferrer" target="_blank"><code>{e(r.filename)}</code></a></p>
  <p class="error">{e(r.error)}</p>
</article>"""
    next_step = (
        f'<aside class="next"><h3>Prochaine étape</h3>{render_markdown(r.prochaine_etape_md)}</aside>'
        if r.prochaine_etape_md
        else ""
    )
    detail = (
        f'<details><summary>Détail</summary><div class="md">{render_markdown(r.detail_md)}</div></details>'
        if r.detail_md
        else ""
    )
    branch = f'<span class="muted">sur <code>{e(r.branche or r.ref)}</code></span>'
    return f"""<article class="card report" {attrs}>
  {head}
  <p class="summary">{render_inline(r.resume)}</p>
  <div class="refs">
    {_commit_html(r)}
    {_pr_html(r)}
    <div class="ref">{branch} · <a href="{e(file_url)}" rel="noopener noreferrer" target="_blank" class="muted">rapport</a></div>
  </div>
  {next_step}
  {detail}
</article>"""


def _ext(url: str | None, label_html: str, cls: str = "") -> str:
    if not url:
        return label_html
    c = f' class="{cls}"' if cls else ""
    return f'<a href="{e(url)}"{c} rel="noopener noreferrer" target="_blank">{label_html}</a>'


def _repo_html(st: RepoStatus) -> str:
    rows = []
    if st.error:
        rows.append(f'<p class="error">{e(st.error)}</p>')
    else:
        if st.open_prs is not None:
            n = f"{st.open_prs}+" if st.open_prs_capped else str(st.open_prs)
            rows.append(
                f'<div class="inline"><dt>PR ouvertes</dt><dd>{_ext(st.url + "/pulls", f"<strong>{e(n)}</strong>")}</dd></div>'
            )
        c = st.last_commit
        if c:
            branch = f' <span class="muted">sur <code>{e(st.default_branch)}</code></span>' if st.default_branch else ""
            rows.append(
                f"""<div><dt>Dernier commit</dt><dd>{_ext(c.url, f"<code>{e(c.short)}</code>")} {fmt_dt(c.date) if c.date else ""}{branch}
          <span class="commit-msg">{e(c.message or "")}</span></dd></div>"""
            )
        d = st.deploy
        if d:
            if d.error:
                state = f'<span class="badge pr-unknown" title="{e(d.error)}">version illisible</span>'
                version = ""
            else:
                version = _ext(d.source_url, f"<code>{e(d.short)}</code>")
                if d.en_attente == 0:
                    state = '<span class="badge s-termine">à jour</span>'
                elif d.en_attente:
                    state = f'<span class="badge s-bloque">{d.en_attente} commit(s) à déployer</span>'
                else:
                    state = '<span class="badge pr-unknown">écart inconnu</span>'
            rows.append(f"<div><dt>Déployé ({e(d.environnement)})</dt><dd>{version} {state}</dd></div>")
    last_sha = st.last_commit.sha if st.last_commit else ""
    deploy_sha = st.deploy.version if st.deploy and st.deploy.version else ""
    # Ligne « En production » remplie par le navigateur depuis l'URL de santé (versions).
    rows.append('<div class="live" hidden><dt>En production</dt><dd></dd></div>')
    return f"""<li class="repo-card" data-repo-name="{e(st.name)}" data-last-sha="{e(last_sha)}" data-deploy-sha="{e(deploy_sha)}">
      <div class="repo-head">
        {_ext(st.url, e(st.name), "repo-link")}
        <button type="button" class="chip" data-filter-repo="{e(st.name)}" title="Afficher les rapports de ce dépôt">rapports</button>
      </div>
      <dl class="repo-facts">{"".join(rows)}</dl>
    </li>"""


def _sidebar_html(pd: ProjectData) -> str:
    depots = pd.depots or [RepoStatus(repo=r, url=f"https://github.com/{r}") for r in pd.project.repos]
    attente = sum(1 for d in depots if d.deploy and d.deploy.en_attente)
    facts = [f"{len(depots)} dépôt(s)"]
    if any(d.open_prs is not None for d in depots):
        facts.append(f"{sum(d.open_prs or 0 for d in depots)} PR ouverte(s)")
    if any(d.deploy for d in depots):
        facts.append(f"{attente} à déployer" if attente else "tout est déployé")
    return f"""<aside class="sidebar" id="sidebar" aria-label="Dépôts du projet">
  <div class="sidebar-head">
    <h2>Dépôts</h2>
    <button type="button" class="toggle" id="sidebar-toggle" aria-controls="sidebar-body" aria-expanded="true" title="Replier le panneau"><span aria-hidden="true">«</span><span class="sr-only">Replier le panneau</span></button>
  </div>
  <div class="sidebar-body" id="sidebar-body">
    <p class="facts">{" · ".join(e(f) for f in facts)}</p>
    <ul class="repo-list">
    {"".join(_repo_html(d) for d in depots)}
    </ul>
  </div>
</aside>"""


def _kpis_html(pd: ProjectData) -> str:
    """Rappel en tête de projet : PR ouvertes, déploiements en attente, dernier
    prompt, santé de l'application (remplie par le navigateur)."""
    depots = pd.depots
    items = []
    if any(d.open_prs is not None for d in depots):
        n = sum(d.open_prs or 0 for d in depots)
        q = "+".join(["is:pr", "is:open"] + [f"repo:{d.repo}" for d in depots])
        items.append(
            f'<li class="kpi"><span class="k">PR ouvertes</span>'
            f'{_ext("https://github.com/pulls?q=" + q, f"<strong>{n}</strong>")}</li>'
        )
    deployed = [d for d in depots if d.deploy and not d.deploy.error]
    if deployed:
        commits = sum(d.deploy.en_attente or 0 for d in deployed)
        repos = sum(1 for d in deployed if d.deploy.en_attente)
        val = (
            f'<span class="badge s-bloque">{commits} commit(s) · {repos} dépôt(s)</span>'
            if commits
            else '<span class="badge s-termine">tout est déployé</span>'
        )
        items.append(f'<li class="kpi"><span class="k">À déployer</span>{val}</li>')
    latest = pd.rapports.latest
    if latest:
        items.append(
            f'<li class="kpi"><span class="k">Dernier prompt</span>{badge(latest.statut)} '
            f'<span class="muted">{fmt_dt(latest.date)} · {e(latest.repo_name)}</span></li>'
        )
    illisibles = pd.rapports.count(STATUT_ILLISIBLE)
    if illisibles:
        items.append(f'<li class="kpi"><span class="k">Rapports illisibles</span><span class="badge s-illisible">{illisibles}</span></li>')
    if pd.project.sante:
        items.append(
            f'<li class="kpi" id="health" data-url="{e(pd.project.sante)}"><span class="k">Santé</span>'
            f'<a class="badge pr-unknown" href="{e(pd.project.sante)}" rel="noopener noreferrer" target="_blank">vérification…</a></li>'
        )
    return f'<ul class="kpis" aria-label="Résumé du projet">{"".join(items)}</ul>' if items else ""


def render_project(pd: ProjectData, generated: datetime) -> str:
    rr = pd.rapports
    repos = sorted({r.rsplit("/", 1)[-1] for r in pd.project.repos})
    present = {r.statut for r in rr.reports}
    statuts = [s for s in (*STATUTS, STATUT_ILLISIBLE) if s in present]
    repo_opts = "".join(f'<option value="{e(r)}">{e(r)}</option>' for r in repos)
    statut_opts = "".join(f'<option value="{e(s)}">{e(STATUT_LABELS[s])}</option>' for s in statuts)
    errors = (
        '<div class="card error-box"><strong>Dépôts inaccessibles</strong><ul>'
        + "".join(f"<li>{e(x)}</li>" for x in rr.errors)
        + "</ul></div>"
        if rr.errors
        else ""
    )
    items = "\n".join(_report_html(r) for r in rr.reports)
    body = f"""<nav class="crumbs"><a href="../">Projets</a> / <span>{e(pd.project.title)}</span></nav>
<div class="project-head">
  <h1>{e(pd.project.title)}</h1>
  {_kpis_html(pd)}
</div>
<div class="layout" id="layout">
{_sidebar_html(pd)}
<div class="content">
{errors}
<form class="filters" id="filters" aria-label="Filtres">
  <label>Repo <select name="repo"><option value="">Tous</option>{repo_opts}</select></label>
  <label>Statut <select name="statut"><option value="">Tous</option>{statut_opts}</select></label>
  <span class="count" id="count" aria-live="polite">{len(rr.reports)} rapport(s)</span>
</form>
<section class="feed" id="feed">
{items if items else '<p class="empty">Aucun rapport pour l’instant.</p>'}
<p class="empty" id="no-match" hidden>Aucun rapport ne correspond aux filtres.</p>
</section>
</div>
</div>"""
    return page(f"{pd.project.title} — SCOPE", body, "..", generated, wide=True)


# --- Écriture du site -----------------------------------------------------------
def build_data_json(projects: list[ProjectData], generated: datetime, sources) -> dict:
    by_name = {s.name: s for s in sources}
    return {
        "generated_at": generated.isoformat().replace("+00:00", "Z"),
        "version": __version__,
        "projets": [
            {
                "name": pd.project.name,
                "title": pd.project.title,
                "repos": pd.project.repos,
                **{k: by_name[k].to_json(v) if k in by_name else v for k, v in pd.sources.items()},
            }
            for pd in projects
        ],
    }


def write_site(
    out: Path,
    projects: list[ProjectData],
    sources,
    generated: datetime | None = None,
) -> None:
    generated = generated or datetime.now(timezone.utc)
    if out.exists():
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    static = resources.files("scope_gen.static")
    for name in ("style.css", "app.js"):
        (out / "assets" / name).write_text(static.joinpath(name).read_text(encoding="utf-8"), encoding="utf-8")
    (out / "index.html").write_text(render_home(projects, generated), encoding="utf-8")
    for pd in projects:
        d = out / pd.project.name
        d.mkdir()
        (d / "index.html").write_text(render_project(pd, generated), encoding="utf-8")
    data = build_data_json(projects, generated, sources)
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
