"""Découverte des dépôts sur le disque et regroupement par projet."""

from datetime import datetime, timedelta, timezone

import pytest

from scope_gen.demandes import ATTENTE, TERMINE
from scope_gen.locale import branche_courante, collecter, decouvrir, silencieuse, slug
from tests.fixtures.racine import construire, depot, rapport

T = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def racine(tmp_path):
    return construire(tmp_path / "racine", T)


def test_decouverte(racine):
    rel = sorted(d.relatif for d in decouvrir(racine))
    assert rel == ["demo/demo-api", "demo/demo-front", "outils/scope-cli", "perso/notes"]
    assert sorted(d.relatif for d in decouvrir(racine, profondeur=6))[0] == "a/b/c/d/trop-profond"
    assert decouvrir(racine / "absent") == []


def test_racine_qui_est_un_depot(tmp_path):
    d = depot(tmp_path, "seul", projet="solo")
    (found,) = decouvrir(d)
    assert found.relatif == "seul" and found.projet == "solo"


def test_regroupement(racine):
    projets = {p.slug: p for p in collecter(racine)}
    assert list(projets) == ["demo", "outils"]  # perso/notes : ni rapport, ni init
    demo = projets["demo"]
    assert [x.relatif for x in demo.depots] == ["demo/demo-api", "demo/demo-front"]
    assert len(demo.demandes) == 10
    assert [d.fichier for d in demo.attente] == [d.fichier for d in demo.demandes if d.etat == ATTENTE]
    assert [d.demande for d in demo.attente] == ["Page de login avec authentification Google"]
    assert {d.demande for d in demo.en_cours} == {"Add rate limiting to the public API", "Migration de la base"}
    assert [d.resume for d in demo.recentes(T)] == [
        "En-tête ajouté et déployé.",
        "Le build échoue toujours : dépendance introuvable.",
        "PR ouverte pour le token.",
        "Il faut un token.",
    ]
    assert [d.resume for d in demo.anciennes(T)] == ["Initialisation du front."]
    assert len(demo.illisibles) == 2
    # Tri : plus récent d'abord.
    dates = [d.date for d in demo.demandes]
    assert dates == sorted(dates, reverse=True)


def test_attente_ancien_format_levee_par_un_rapport_plus_recent(racine):
    projets = {p.slug: p for p in collecter(racine)}
    ancien = next(d for d in projets["demo"].demandes if d.fichier.endswith("ancien-bloque.md"))
    assert ancien.statut == ATTENTE and ancien.attente_levee and ancien.etat == TERMINE
    (q,) = projets["outils"].attente  # seul rapport du dépôt : toujours en attente
    assert q.ancien_format and [p.texte for p in q.questions] == ["Choisissez entre `scope` et `sc`."]


def test_projet_par_defaut(tmp_path):
    d = depot(tmp_path, "x/mon-depot")
    rapport(d, T, "a", "---\nstatut: termine\n---\n## Résumé\nx\n")
    d2 = depot(tmp_path, "x/autre", projet="Mon Projet")
    rapport(d2, T, "b", "---\nstatut: termine\n---\n## Résumé\ny\n")
    rapport(d2, T, "c", "---\nprojet: mon-depot\nstatut: termine\n---\n## Résumé\nz\n")
    projets = {p.slug: p for p in collecter(tmp_path)}
    assert set(projets) == {"mon-depot", "mon-projet"}
    assert projets["mon-projet"].titre == "Mon Projet"
    assert sorted(d.resume for d in projets["mon-depot"].demandes) == ["x", "z"]
    assert [x.nom for x in projets["mon-depot"].depots] == ["autre", "mon-depot"]


def test_depot_initialise_sans_rapport(tmp_path):
    depot(tmp_path, "neuf", projet="neuf")
    (p,) = collecter(tmp_path)
    assert p.slug == "neuf" and p.demandes == [] and [x.nom for x in p.depots] == ["neuf"]


def test_branche_par_defaut_lue_dans_git_head(racine):
    projets = {p.slug: p for p in collecter(racine)}
    mig = next(d for d in projets["demo"].demandes if d.demande == "Migration de la base")
    assert mig.branche == "main"  # absente du rapport : branche courante du clone
    assert branche_courante(racine / "demo" / "demo-front") == "feat/login-google"


def test_branche_worktree(tmp_path):
    vrai = tmp_path / "gitdir"
    vrai.mkdir()
    (vrai / "HEAD").write_text("ref: refs/heads/feat/wt\n")
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {vrai}\n")
    assert branche_courante(wt) == "feat/wt"


def test_silencieuse(racine):
    projets = {p.slug: p for p in collecter(racine)}
    sil = [d.demande for d in projets["demo"].en_cours if silencieuse(d, T)]
    assert sil == ["Migration de la base"]
    assert not silencieuse(projets["demo"].en_cours[0], T - timedelta(hours=5))


def test_slug():
    assert slug("Boutique Front") == "boutique-front"
    assert slug("Équipe/Été") == "equipe-ete"
    assert slug("assets") == "assets-projet"
    assert slug("!!!") == "projet"
