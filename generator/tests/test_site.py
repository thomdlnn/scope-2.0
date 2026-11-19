"""Génération du site : pages, échappement, data.json, boucle et bascule."""

import json
import os
from datetime import datetime, timezone

from scope_gen import cli
from scope_gen.locale import collecter
from scope_gen.render import calculer_empreinte, write_site
from tests.fixtures.racine import construire, depot, rapport

T = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def site(tmp_path):
    racine = construire(tmp_path / "racine", T)
    out = tmp_path / "site"
    projets = collecter(racine)
    write_site(out, projets, T, intervalle=3)
    return out, projets


def test_accueil(tmp_path):
    out, projets = site(tmp_path)
    home = (out / "index.html").read_text()
    n = sum(len(p.attente) for p in projets)
    assert f'id="attente">{n} actions en attente : ' in home and "Rien ne vous attend" not in home
    # Un bloc par projet, ceux qui attendent quelque chose d'abord.
    demo = home[home.index('id="projet-demo"') :]
    assert '<a class="projet-link" href="demo/">' in demo
    attente = demo[demo.index('id="attente-demo"') : demo.index('id="en-cours-demo"')]
    assert "quel Client ID Google dois-je utiliser ?" in attente
    assert "Page de login avec authentification Google" in attente and "demo-front" in attente
    assert "Il faut un token." not in attente  # attente levée
    en_cours = demo[demo.index('id="en-cours-demo"') : demo.index('id="recentes-demo"')]
    assert "Sans nouvelles depuis" in en_cours and en_cours.count('class="card demande"') == 2
    assert "Initialisation du front." not in home  # plus de 7 jours
    assert '<meta name="scope-intervalle" content="3">' in home


def test_en_attente_texte():
    from scope_gen.render import en_attente_texte

    assert [en_attente_texte(n) for n in (0, 1, 3)] == [
        "Aucune action en attente", "1 action en attente", "3 actions en attente"]


def test_accueil_sans_attente(tmp_path):
    racine = tmp_path / "r"
    d = depot(racine, "p/app", projet="p")
    rapport(d, T, "x", "---\nstatut: termine\n---\n## Résumé\nFini\n")
    write_site(tmp_path / "s", collecter(racine), T)
    home = (tmp_path / "s" / "index.html").read_text()
    assert "Aucune action en attente" in home and 'id="recentes-p"' in home
    page = (tmp_path / "s" / "p" / "index.html").read_text()
    assert '<h2 id="attente-titre">Aucune action en attente</h2>' in page


def test_page_projet(tmp_path):
    out, _ = site(tmp_path)
    page = (out / "demo" / "index.html").read_text()
    assert '<option value="demo-front">' in page and 'data-filtre-depot="demo-api"' in page
    assert 'class="action a-deploy">déploiement</span>' in page and "PR #42" in page
    assert "Plus anciennes (1)" in page and "Initialisation du front." in page
    assert 'id="illisibles"' in page and "YAML invalide" in page
    assert page.count("<details id=") == 8  # une section Détail par demande valide
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "<script>alert" not in page
    assert "demo/demo-front/.scope/rapports/" in page


def test_data_json(tmp_path):
    out, projets = site(tmp_path)
    data = json.loads((out / "data.json").read_text())
    assert data["empreinte"] == calculer_empreinte(projets, T)
    demo = next(p for p in data["projets"] if p["slug"] == "demo")
    assert {x["statut"] for x in demo["demandes"]} == {"attente", "en-cours", "termine", "echec", "illisible"}
    etat = json.loads((out / "etat.json").read_text())
    assert etat["empreinte"] == data["empreinte"] and etat["intervalle"] == 3


def test_sans_projet(tmp_path):
    write_site(tmp_path / "s", [], T)
    assert "./scope.sh init" in (tmp_path / "s" / "index.html").read_text()


def test_empreinte_stable_puis_change(tmp_path):
    racine = construire(tmp_path / "r", T)
    a = calculer_empreinte(collecter(racine), T)
    assert a == calculer_empreinte(collecter(racine), T)
    f = next((racine / "demo" / "demo-api" / ".scope" / "rapports").glob("*rate-limit.md"))
    f.write_text(f.read_text().replace("status: in-progress", "status: done"))
    assert calculer_empreinte(collecter(racine), T) != a


def test_boucle_bascule_seulement_si_changement(tmp_path):
    racine = tmp_path / "r"
    d = depot(racine, "p/app", projet="p")
    sitedir = tmp_path / "site"
    sitedir.mkdir()
    assert cli.cycle(sitedir, cli.Config(racine), 3) is True
    premier = os.readlink(sitedir / "current")
    assert (sitedir / "current" / "index.html").exists()
    assert cli.cycle(sitedir, cli.Config(racine), 3) is False  # rien n'a changé
    assert os.readlink(sitedir / "current") == premier
    rapport(d, T, "x", "---\nstatut: en-cours\n---\n## Résumé\nNouveau\n")
    assert cli.cycle(sitedir, cli.Config(racine), 3) is True
    assert os.readlink(sitedir / "current") != premier
    assert sorted(p.name for p in sitedir.glob("build-*")) == sorted([premier, os.readlink(sitedir / "current")])
    rapport(d, T, "y", "---\nstatut: termine\n---\n## Résumé\nEncore\n")
    cli.cycle(sitedir, cli.Config(racine), 3)
    assert premier not in [p.name for p in sitedir.glob("build-*")]  # seuls les deux derniers restent
    assert "Nouveau" in (sitedir / "current" / "p" / "index.html").read_text()


def test_boucle_survit_a_une_erreur(tmp_path, monkeypatch):
    appels = []

    def casse(*a):
        appels.append(1)
        raise RuntimeError("boum")

    monkeypatch.setattr(cli, "cycle", casse)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    cli.boucle(tmp_path / "s", cli.Config(tmp_path), 0.01, tours=2)
    assert len(appels) == 2


def test_cli_une_fois(tmp_path, capsys):
    racine = construire(tmp_path / "r", T)
    assert cli.main(["--racine", str(racine), "--out", str(tmp_path / "o"), "--projets", str(tmp_path / "aucun")]) == 0
    assert "2 projet(s)" in capsys.readouterr().out
    assert '<meta name="scope-intervalle" content="0">' in (tmp_path / "o" / "index.html").read_text()


def test_empreinte_change_avec_le_code(tmp_path, monkeypatch):
    from scope_gen import render

    projets = collecter(construire(tmp_path / "r", T))
    a = calculer_empreinte(projets, T)
    monkeypatch.setattr(render, "CODE", "autre-version-du-code")
    assert calculer_empreinte(projets, T) != a
