"""Génération du site statique : index.html, <projet>/index.html, data.json, etat.json."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from html import escape
from importlib import resources
from pathlib import Path
from string import Template
from typing import Any

from . import __version__
from .demandes import ATTENTE, ECHEC, EN_COURS, ILLISIBLE, TERMINE, Demande
from .locale import Projet, silencieuse
from .models import RepoStatus
from .markdown_safe import render_markdown

def _empreinte_code() -> str:
    """Empreinte du code du générateur (Python, gabarits, CSS, JS) : une mise à jour
    de SCOPE régénère le site même si aucun rapport n'a changé."""
    racine = Path(__file__).parent
    h = hashlib.sha256()
    for f in sorted(racine.rglob("*")):
        if f.is_file() and f.suffix in {".py", ".html", ".css", ".js"}:
            h.update(f.relative_to(racine).as_posix().encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


CODE = _empreinte_code()

STATUT_LABELS = {
    EN_COURS: "En cours",
    ATTENTE: "Attend votre réponse",
    TERMINE: "Terminé",
    ECHEC: "Échec",
    ILLISIBLE: "Illisible",
}
ACTION_LABELS = {
    "code": "code",
    "commit": "commit",
    "push": "push",
    "pr": "PR",
    "deploy": "déploiement",
    "hors-depot": "hors dépôt",
}


def e(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return '<span class="muted">date inconnue</span>'
    txt = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f'<time datetime="{e(iso(dt))}">{e(txt)}</time>'


def render_inline(text: str | None) -> str:
    """Markdown d'une ligne (code, gras, liens), sans paragraphe englobant."""
    html = render_markdown(text)
    if html.startswith("<p>") and html.endswith("</p>") and html.count("<p>") == 1:
        html = html[3:-4]
    return html


def badge(statut: str) -> str:
    return f'<span class="badge s-{e(statut)}">{e(STATUT_LABELS.get(statut, statut))}</span>'


def _tpl(name: str) -> Template:
    return Template(resources.files("scope_gen.templates").joinpath(name).read_text(encoding="utf-8"))


def page(title: str, body: str, root: str, generated: datetime, empreinte: str, intervalle: float, wide: bool = False) -> str:
    return _tpl("layout.html").substitute(
        main_class="wide" if wide else "",
        title=e(title),
        body=body,
        root=root,
        generated=fmt_dt(generated),
        version=e(__version__),
        empreinte=e(empreinte),
        code=e(CODE),
        intervalle=e(f"{intervalle:g}"),
    )


# --- Une demande -------------------------------------------------------------------
def _points_html(d: Demande) -> str:
    if not d.points:
        return ""
    lis = []
    for p in d.points:
        # Une attente de l'ancien format levée n'est plus une question ouverte.
        nature = "remarque" if d.attente_levee else p.nature
        label = "Question" if nature == "question" else "Remarque"
        lis.append(f'<li class="pt pt-{e(nature)}"><span class="k">{label}</span><div class="md">{render_markdown(p.texte)}</div></li>')
    return f'<ul class="pour-vous" aria-label="Pour vous">{"".join(lis)}</ul>'


def _demande_html(d: Demande, maintenant: datetime, avec_projet: str | None = None) -> str:
    attrs = f'id="{e(d.ident)}" data-depot="{e(d.depot)}" data-statut="{e(d.etat)}"'
    fichier = f"{d.depot_chemin}/.scope/rapports/{d.fichier}"
    if not d.valide:
        return f"""<article class="card demande invalid" {attrs}>
  <header class="meta">{fmt_dt(d.date)} <span class="depot">{e(d.depot)}</span> {badge(ILLISIBLE)}</header>
  <p class="summary">Rapport illisible : <code>{e(fichier)}</code></p>
  <p class="error">{e(d.erreur)}</p>
</article>"""
    actions = "".join(
        f'<span class="action a-{e(a)}">{e(f"PR #{d.pr}" if a == "pr" and d.pr else ACTION_LABELS[a])}</span>'
        for a in d.actions
    )
    if d.pr and "pr" not in d.actions:
        actions += f'<span class="action a-pr">PR #{d.pr}</span>'
    silence = (
        f'<p class="silence">Sans nouvelles depuis {fmt_dt(d.date)}</p>' if silencieuse(d, maintenant) else ""
    )
    projet = f'<span class="projet">{e(avec_projet)}</span>' if avec_projet else ""
    branche = f'<span class="branche"><code>{e(d.branche)}</code></span>' if d.branche else ""
    agent = f'<span class="agent">{e(d.agent)}</span>' if d.agent else ""
    demande = f'<p class="requete">« {e(d.demande)} »</p>' if d.demande else ""
    avert = (
        '<p class="warning">' + " · ".join(e(a) for a in d.avertissements) + "</p>" if d.avertissements else ""
    )
    detail_md = f'<div class="md">{render_markdown(d.detail_md)}</div>' if d.detail_md else ""
    debut = f"Commencée {fmt_dt(d.debut)} · " if d.debut and d.debut != d.maj else ""
    return f"""<article class="card demande" {attrs}>
  <header class="meta">{fmt_dt(d.date)} {projet}<span class="depot">{e(d.depot)}</span> {branche} {agent} {badge(d.etat)}</header>
  {demande}
  <p class="summary">{render_inline(d.resume)}</p>
  {f'<p class="actions" aria-label="Actions">{actions}</p>' if actions else ''}
  {silence}
  {_points_html(d)}
  {avert}
  <details id="{e(d.ident)}-detail"><summary>Détail</summary>{detail_md}
    <p class="fichier muted">{debut}<code>{e(fichier)}</code></p></details>
</article>"""


def _section(ident: str, titre: str, demandes: list[Demande], maintenant: datetime, projets: dict[int, str] | None = None, vide: str = "", cls: str = "") -> str:
    if not demandes and not vide:
        return ""
    cards = "\n".join(_demande_html(d, maintenant, (projets or {}).get(id(d))) for d in demandes)
    n = f' <span class="n">{len(demandes)}</span>' if demandes else ""
    contenu = cards or f'<p class="empty">{e(vide)}</p>'
    return f"""<section class="bloc {cls}" id="{ident}" aria-labelledby="{ident}-titre">
  <h2 id="{ident}-titre">{e(titre)}{n}</h2>
  {contenu}
</section>"""


def _trier(demandes: list[Demande]) -> list[Demande]:
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(demandes, key=lambda d: (d.date or epoch, d.fichier), reverse=True)


# --- Accueil ------------------------------------------------------------------------
def en_attente_texte(n: int) -> str:
    """« Aucune action en attente », « 1 action en attente », « 3 actions en attente »."""
    if not n:
        return "Aucune action en attente"
    return f"{n} action{'s' if n > 1 else ''} en attente"


def _section_attente(ident: str, demandes: list[Demande], maintenant: datetime) -> str:
    """Bloc des attentes : le titre donne le compte, vide il ne montre que ce titre."""
    cards = "\n".join(_demande_html(d, maintenant) for d in demandes)
    cls = "attente" if demandes else "attente calme"
    return f"""<section class="bloc {cls}" id="{ident}" aria-labelledby="{ident}-titre">
  <h2 id="{ident}-titre">{e(en_attente_texte(len(demandes)))}</h2>
  {cards}
</section>"""


def _ordre_projets(projets: list[Projet]) -> list[Projet]:
    """Projets qui attendent quelque chose d'abord, puis en cours, puis par activité récente."""
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(projets, key=lambda p: (not p.attente, not p.en_cours, -(p.derniere or epoch).timestamp(), p.slug))


def _projet_accueil(p: Projet, generated: datetime) -> str:
    extra = []
    if p.illisibles:
        extra.append(f'<span class="badge s-illisible">{len(p.illisibles)} illisible(s)</span>')
    if p.etats is not None:
        extra.append(f'<span class="badge">{p.prs_ouvertes} PR ouverte(s)</span>')
        erreurs = sum(1 for _r, st in p.etats if st and st.error)
        if erreurs:
            extra.append(f'<a class="badge s-echec" href="{e(p.slug)}/">{erreurs} dépôt(s) en erreur</a>')
    blocs = []
    if p.attente:
        blocs.append(_section_attente(f"attente-{p.slug}", _trier(p.attente), generated))
    if p.en_cours:
        blocs.append(_section(f"en-cours-{p.slug}", "En cours", _trier(p.en_cours), generated, cls="en-cours"))
    recentes = p.recentes(generated)
    if recentes:
        blocs.append(
            f"""<details class="bloc recentes" id="recentes-{e(p.slug)}"><summary>7 derniers jours ({len(recentes)})</summary>
  {"".join(_demande_html(d, generated) for d in recentes)}
</details>"""
        )
    if not blocs:
        blocs.append('<p class="empty">Rien depuis 7 jours.</p>')
    return f"""<section class="projet-bloc" id="projet-{e(p.slug)}" aria-labelledby="projet-{e(p.slug)}-titre">
  <header class="projet-entete">
    <h2 id="projet-{e(p.slug)}-titre"><a class="projet-link" href="{e(p.slug)}/">{e(p.titre)}</a></h2>
    <span class="badge {"s-attente" if p.attente else ""}">{e(en_attente_texte(len(p.attente)))}</span>
    {" ".join(extra)}
    <p class="muted">{len(p.demandes)} demande(s) · dernière activité {fmt_dt(p.derniere) if p.derniere else "—"} ·
      {" ".join(f"<code>{e(x.nom)}</code>" for x in p.depots)}</p>
  </header>
  {"".join(blocs)}
</section>"""


def render_home(projets: list[Projet], generated: datetime, empreinte: str, intervalle: float, alertes: list[str] | None = None) -> str:
    n = sum(len(p.attente) for p in projets)
    if projets:
        resume = f'<p class="resume-attente {"attente" if n else "calme"}" id="attente">{e(en_attente_texte(n))}'
        if n:
            resume += " : " + ", ".join(
                f'<a href="#projet-{e(p.slug)}">{e(p.titre)} ({len(p.attente)})</a>' for p in _ordre_projets(projets) if p.attente
            )
        resume += "</p>"
        liste = "\n".join(_projet_accueil(p, generated) for p in _ordre_projets(projets))
    else:
        resume = ""
        liste = (
            '<p class="empty">Aucun rapport trouvé. Installez la consigne dans un dépôt avec '
            "<code>./scope.sh init &lt;projet&gt; &lt;dossier-du-clone&gt;</code>, puis demandez quelque chose à votre agent.</p>"
        )
    alerte = (
        '<div class="card error-box"><strong>Réglages ignorés (projects/*.yml)</strong><ul>'
        + "".join(f"<li>{e(a)}</li>" for a in alertes)
        + "</ul></div>"
        if alertes
        else ""
    )
    body = f"""{alerte}
{resume}
{liste}"""
    return page("SCOPE", body, ".", generated, empreinte, intervalle)


# --- Dépôts GitHub (avec token) -----------------------------------------------------
def _ext(url: str | None, label_html: str, cls: str = "") -> str:
    if not url:
        return label_html
    c = f' class="{cls}"' if cls else ""
    return f'<a href="{e(url)}"{c} rel="noopener noreferrer" target="_blank">{label_html}</a>'


def _repo_html(repo: str, st: RepoStatus | None, clones: list[str]) -> str:
    nom = repo.rsplit("/", 1)[-1]
    url = f"https://github.com/{repo}"
    rows = []
    if st is None:
        rows.append('<p class="muted">lecture en cours…</p>')
    elif st.error:
        rows.append(f'<p class="error">{e(st.error)}</p>')
    else:
        if st.warning:
            rows.append(f'<p class="warning">{e(st.warning)}</p>')
        if st.prs is not None:
            n = f"{len(st.prs)}+" if st.prs_capped else str(len(st.prs))
            items = "".join(
                f'<li>{_ext(pr.url, f"#{pr.number} {e(pr.title)}")}'
                f'{" <span class=badge>brouillon</span>" if pr.brouillon else ""}'
                f'{f" <span class=muted>· {e(pr.auteur)}</span>" if pr.auteur else ""}</li>'
                for pr in st.prs
            )
            liste = f'<ul class="prs">{items}</ul>' if items else ""
            rows.append(f'<div><dt>PR ouvertes</dt><dd>{_ext(url + "/pulls", f"<strong>{e(n)}</strong>")}{liste}</dd></div>')
        c = st.last_commit
        if c:
            branch = f' <span class="muted">sur <code>{e(st.default_branch)}</code></span>' if st.default_branch else ""
            rows.append(
                f'<div><dt>Dernier commit</dt><dd>{_ext(c.url, f"<code>{e(c.short)}</code>")} '
                f'{fmt_dt(c.date) if c.date else ""}{branch}<span class="commit-msg">{e(c.message or "")}</span></dd></div>'
            )
        d = st.deploy
        if d:
            if d.error:
                state, version = f'<span class="badge" title="{e(d.error)}">version illisible</span>', ""
            else:
                version = _ext(d.source_url, f"<code>{e(d.short)}</code>")
                if d.en_attente == 0:
                    state = '<span class="badge s-termine">à jour</span>'
                elif d.en_attente:
                    state = f'<span class="badge s-attente">{d.en_attente} commit(s) à déployer</span>'
                else:
                    state = '<span class="badge">écart inconnu</span>'
            rows.append(f"<div><dt>Déployé ({e(d.environnement)})</dt><dd>{version} {state}</dd></div>")
    last_sha = st.last_commit.sha if st and st.last_commit else ""
    deploy_sha = st.deploy.version if st and st.deploy and st.deploy.version else ""
    rows.append('<div class="live" hidden><dt>En production</dt><dd></dd></div>')
    filtres = " ".join(
        f'<button type="button" class="chip" data-filtre-depot="{e(c)}" title="Afficher les demandes de ce clone">{e(c)}</button>'
        for c in clones
    )
    return f"""<li class="repo-card" data-repo-name="{e(nom)}" data-last-sha="{e(last_sha)}" data-deploy-sha="{e(deploy_sha)}">
      <div class="repo-head">{_ext(url, e(repo), "repo-link")}</div>
      <p class="chips">{filtres}</p>
      <dl class="repo-facts">{"".join(rows)}</dl>
    </li>"""


def _panneau_html(p: Projet) -> str:
    if p.etats is None:
        return ""
    clones: dict[str, list[str]] = {}
    for d in p.depots:
        if d.github:
            clones.setdefault(d.github, []).append(d.nom)
    cartes = "".join(_repo_html(r, st, clones.get(r, [])) for r, st in p.etats)
    hors = "".join(
        f'<li class="repo-card"><div class="repo-head"><strong>{e(d.nom)}</strong></div>'
        f'<p class="muted">pas de remote origin sur GitHub</p>'
        f'<p class="chips"><button type="button" class="chip" data-filtre-depot="{e(d.nom)}">{e(d.nom)}</button></p></li>'
        for d in p.sans_github
    )
    return f"""<aside class="sidebar" id="sidebar" aria-label="Dépôts du projet">
  <div class="sidebar-head">
    <h2>Dépôts</h2>
    <button type="button" class="toggle" id="sidebar-toggle" aria-controls="sidebar-body" aria-expanded="true" title="Replier le panneau"><span aria-hidden="true">«</span><span class="sr-only">Replier le panneau</span></button>
  </div>
  <div class="sidebar-body" id="sidebar-body"><ul class="repo-list">{cartes}{hors}</ul></div>
</aside>"""


def _kpis_html(p: Projet) -> str:
    items = []
    if p.etats is not None:
        n = p.prs_ouvertes or 0
        q = "+".join(["is:pr", "is:open"] + [f"repo:{r}" for r in p.repos_github])
        items.append(f'<li class="kpi"><span class="k">PR ouvertes</span>{_ext("https://github.com/pulls?q=" + q, f"<strong>{n}</strong>")}</li>')
        deployed = [st for _r, st in p.etats if st and st.deploy and not st.deploy.error]
        if deployed:
            commits = sum(st.deploy.en_attente or 0 for st in deployed)
            val = (
                f'<span class="badge s-attente">{commits} commit(s)</span>'
                if commits
                else '<span class="badge s-termine">tout est déployé</span>'
            )
            items.append(f'<li class="kpi"><span class="k">À déployer</span>{val}</li>')
        erreurs = sum(1 for _r, st in p.etats if st and st.error)
        if erreurs:
            items.append(f'<li class="kpi"><span class="k">Dépôts en erreur</span><span class="badge s-echec">{erreurs}</span></li>')
    sante = p.reglages.sante if p.reglages else None
    if sante:
        items.append(
            f'<li class="kpi" id="health" data-url="{e(sante)}"><span class="k">Santé</span>'
            f'<a class="badge" href="{e(sante)}" rel="noopener noreferrer" target="_blank">vérification…</a></li>'
        )
    return f'<ul class="kpis" aria-label="Résumé du projet">{"".join(items)}</ul>' if items else ""


# --- Page projet -------------------------------------------------------------------
def render_project(p: Projet, generated: datetime, empreinte: str, intervalle: float) -> str:
    depots = sorted({d.depot for d in p.demandes} | {x.nom for x in p.depots})
    statuts = [s for s in (ATTENTE, EN_COURS, TERMINE, ECHEC, ILLISIBLE) if any(d.etat == s for d in p.demandes)]
    depot_opts = "".join(f'<option value="{e(r)}">{e(r)}</option>' for r in depots)
    statut_opts = "".join(f'<option value="{e(s)}">{e(STATUT_LABELS[s])}</option>' for s in statuts)
    chips = " ".join(
        f'<button type="button" class="chip" data-filtre-depot="{e(x.nom)}" title="{e(x.relatif)}">{e(x.nom)}</button>'
        for x in p.depots
    )
    anciennes = p.anciennes(generated)
    plus = (
        f"""<details class="bloc anciennes" id="anciennes"><summary>Plus anciennes ({len(anciennes)})</summary>
  {"".join(_demande_html(d, generated) for d in anciennes)}
</details>"""
        if anciennes
        else ""
    )
    panneau = _panneau_html(p)
    body = f"""<nav class="crumbs"><a href="../">Accueil</a> / <span>{e(p.titre)}</span></nav>
<div class="project-head"><h1>{e(p.titre)}</h1>{_kpis_html(p)}</div>
{'<div class="layout" id="layout">' + panneau + '<div class="content">' if panneau else '<div class="content">'}
<form class="filters" id="filters" aria-label="Filtres">
  <label>Dépôt <select name="depot"><option value="">Tous</option>{depot_opts}</select></label>
  <label>Statut <select name="statut"><option value="">Tous</option>{statut_opts}</select></label>
  <span class="count" id="count" aria-live="polite">{len(p.demandes)} demande(s)</span>
  {f'<p class="chips">{chips}</p>' if chips and p.etats is None else ''}
</form>
{_section_attente("attente", p.attente, generated)}
{_section("en-cours", "En cours", p.en_cours, generated, cls="en-cours")}
{_section("recentes", "7 derniers jours", p.recentes(generated), generated)}
{plus}
{_section("illisibles", "Rapports illisibles", p.illisibles, generated, cls="illisibles")}
<p class="empty" id="no-match" hidden>Aucune demande ne correspond aux filtres.</p>
</div>{'</div>' if panneau else ''}"""
    return page(f"{p.titre} — SCOPE", body, "..", generated, empreinte, intervalle, wide=bool(panneau))


# --- Données et écriture -------------------------------------------------------------
def donnees(projets: list[Projet]) -> list[dict]:
    return [
        {
            "slug": p.slug,
            "titre": p.titre,
            "depots": [{"nom": x.nom, "chemin": x.relatif} for x in p.depots],
            "demandes": [d.to_dict() for d in p.demandes],
            "github": None if p.etats is None else [
                {"repo": r, "etat": st.to_dict() if st else None} for r, st in p.etats
            ],
            "sante": p.reglages.sante if p.reglages else None,
        }
        for p in projets
    ]


def calculer_empreinte(projets: list[Projet], maintenant: datetime, alertes: list[str] | None = None) -> str:
    """Change dès que l'affichage change : contenu des rapports, mais aussi
    demandes qui deviennent silencieuses ou sortent des 7 derniers jours."""
    etat = {
        "v": __version__,
        "code": CODE,
        "p": donnees(projets),
        "alertes": alertes or [],
        "silence": sorted(d.ident for p in projets for d in p.demandes if silencieuse(d, maintenant)),
        "recentes": sorted(d.ident for p in projets for d in p.recentes(maintenant)),
    }
    return hashlib.sha256(json.dumps(etat, sort_keys=True, default=str).encode()).hexdigest()[:16]


def ecrire_etat(out: Path, empreinte: str, verifie: datetime, intervalle: float) -> None:
    """etat.json : petit fichier relu par la page toutes les quelques secondes."""
    tmp = out / ".etat.json.tmp"
    tmp.write_text(
        json.dumps({"empreinte": empreinte, "code": CODE, "verifie_a": iso(verifie), "intervalle": intervalle}), encoding="utf-8"
    )
    tmp.replace(out / "etat.json")


def write_site(
    out: Path,
    projets: list[Projet],
    generated: datetime | None = None,
    empreinte: str | None = None,
    intervalle: float = 0,
    alertes: list[str] | None = None,
) -> str:
    """Écrit le site dans `out` (qui doit être vide ou absent). Renvoie l'empreinte."""
    generated = generated or datetime.now(timezone.utc)
    empreinte = empreinte or calculer_empreinte(projets, generated, alertes)
    (out / "assets").mkdir(parents=True, exist_ok=True)
    static = resources.files("scope_gen.static")
    for name in ("style.css", "app.js"):
        (out / "assets" / name).write_text(static.joinpath(name).read_text(encoding="utf-8"), encoding="utf-8")
    (out / "index.html").write_text(render_home(projets, generated, empreinte, intervalle, alertes), encoding="utf-8")
    for p in projets:
        d = out / p.slug
        d.mkdir(exist_ok=True)
        (d / "index.html").write_text(render_project(p, generated, empreinte, intervalle), encoding="utf-8")
    data = {"genere_a": iso(generated), "version": __version__, "empreinte": empreinte, "projets": donnees(projets)}
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    ecrire_etat(out, empreinte, generated, intervalle)
    return empreinte
