import json

from scope_gen.backends import LocalBackend
from scope_gen.cli import build, main


def test_backend_local_lit_branches_et_dedoublonne(local_repos):
    from scope_gen.parser import dedupe

    raws = dedupe(LocalBackend(local_repos).list_reports("acme/demo-front"))
    by_name = {r.filename: r.ref for r in raws}
    assert by_name == {
        "2026-11-14-090000-init-front.md": "main",
        "2026-11-15-143000-header.md": "main",  # présent sur 2 branches, gardé une fois
        "2026-11-16-103000-ajout-login.md": "feat/login",
    }


def test_generation_locale(local_repos, projects_dir, tmp_path):
    out = tmp_path / "site"
    data = build(projects_dir, out, LocalBackend(local_repos))

    assert (out / "index.html").exists()
    assert (out / "demo" / "index.html").exists()
    assert (out / "assets" / "style.css").exists() and (out / "assets" / "app.js").exists()

    demo = next(pd for pd in data if pd.project.name == "demo")
    reports = demo.rapports.reports
    assert len(reports) == 7
    # tri du plus récent au plus ancien
    dates = [r.date for r in reports]
    assert dates == sorted(dates, reverse=True)
    assert sum(not r.valid for r in reports) == 2

    login = next(r for r in reports if r.filename.endswith("ajout-login.md"))
    assert login.ref == "feat/login"
    assert login.commit and login.commit.message == "feat(front): ajout de la page de login"
    assert login.commit.url.startswith("https://github.com/acme/demo-front/commit/")
    assert login.pr.number == 42 and login.pr.state is None  # pas de PR en local : secours

    # le projet dont le clone est absent ne casse pas la génération
    fantome = next(pd for pd in data if pd.project.name == "fantome")
    assert fantome.rapports.errors and not fantome.rapports.reports

    home = (out / "index.html").read_text()
    assert "Démo" in home and "Projet fantôme" in home
    # accueil : statut du dernier prompt valide, pas de compteur bloqué/échec
    assert "Bloqué / échec" not in home and "bloqué/échec" not in home
    demo_card = home.split("Projet fantôme")[0]
    assert 'class="badge s-pr-ouverte">PR ouverte<' in demo_card
    page = (out / "demo" / "index.html").read_text()
    assert page.count('class="card report') == 7
    assert "Rapport illisible" in page and "YAML invalide" in page
    assert "<script>alert" not in page and "&lt;script&gt;alert" in page
    assert "javascript:" not in page
    assert '<details><summary>Détail</summary>' in page
    assert 'class="next"' in page
    assert 'data-repo="demo-api" data-statut="echec"' in page

    payload = json.loads((out / "data.json").read_text())
    p = next(x for x in payload["projets"] if x["name"] == "demo")
    assert p["rapports"]["total"] == 7 and p["rapports"]["illisibles"] == 2
    assert p["rapports"]["dernier_statut"] == "pr-ouverte"
    assert p["rapports"]["rapports"][0]["filename"] == "2026-11-16-103000-ajout-login.md"


def test_cli_local(local_repos, projects_dir, tmp_path, capsys):
    rc = main(["--local", str(local_repos), "--projects", str(projects_dir), "--out", str(tmp_path / "s")])
    assert rc == 0
    assert "2 projet(s), 7 rapport(s), 1 dépôt(s) en erreur" in capsys.readouterr().out


def test_cli_config_invalide(tmp_path):
    (tmp_path / "x.yml").write_text("name: x\nrepos: []\n")
    assert main(["--local", str(tmp_path), "--projects", str(tmp_path), "--out", str(tmp_path / "s")]) == 2
