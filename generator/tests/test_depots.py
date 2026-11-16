"""Source « depots » : PR ouvertes, dernier commit, version déployée."""

import pytest

from scope_gen.backends import GitHubBackend, LocalBackend
from scope_gen.cli import build
from scope_gen.config import ConfigError, load_project
from scope_gen.models import DeployTarget, Project
from scope_gen.sources import DepotsSource
from scope_gen.sources.depots import lookup
from tests.test_github_backend import FakeSession


def test_lookup():
    assert lookup({"image": {"tag": "abc"}}, "image.tag") == "abc"
    assert lookup({"image": {}}, "image.tag") is None
    assert lookup(None, "image.tag") is None


def test_depots_en_local(local_repos, projects_dir, tmp_path):
    data = build(projects_dir, tmp_path / "site", LocalBackend(local_repos))
    demo = next(pd for pd in data if pd.project.name == "demo")
    by = {d.name: d for d in demo.depots}
    assert list(by) == ["demo-front", "demo-api", "demo-deploy"]

    front = by["demo-front"]
    assert front.default_branch == "main"
    assert front.last_commit.message == "feat(front): en-tête et navigation"
    assert front.last_commit.date is not None
    assert front.open_prs is None  # inconnu en local
    assert front.deploy.environnement == "local"
    assert front.deploy.en_attente == 1  # déployé : main~1
    assert front.deploy.source_url.endswith("/acme/demo-deploy/blob/main/environments/local/demo-front.yaml")

    assert by["demo-api"].deploy.en_attente == 0
    assert by["demo-deploy"].deploy is None

    page = (tmp_path / "site" / "demo" / "index.html").read_text()
    assert 'id="sidebar"' in page and 'data-filter-repo="demo-front"' in page
    assert "1 commit(s) à déployer" in page and "à jour" in page
    assert "1 à déployer" in page  # résumé du projet

    fantome = next(pd for pd in data if pd.project.name == "fantome")
    assert fantome.depots[0].error  # clone absent : erreur affichée, pas d'exception


def test_deploiement_fichier_ou_cle_absents(local_repos):
    backend = LocalBackend(local_repos)
    st = DepotsSource.status(
        "acme/demo-front", DeployTarget("acme/demo-deploy", "absent.yaml"), backend
    )
    assert "introuvable" in st.deploy.error
    st = DepotsSource.status(
        "acme/demo-front", DeployTarget("acme/demo-deploy", "environments/local/demo-front.yaml", cle="x.y"), backend
    )
    assert "clé x.y absente" in st.deploy.error


def test_config_deploiements(tmp_path):
    f = tmp_path / "p.yml"
    f.write_text("name: p\nrepos: [o/a]\ndeploiements:\n  o/a: {depot: o/deploy, fichier: env/a.yaml}\n")
    t = load_project(f).deploiements["o/a"]
    assert (t.depot, t.fichier, t.cle, t.environnement, t.ref) == ("o/deploy", "env/a.yaml", "image.tag", "local", None)
    for bad in (
        "deploiements:\n  o/b: {depot: o/deploy, fichier: x}\n",  # dépôt hors projet
        "deploiements:\n  o/a: {depot: o/deploy}\n",  # fichier manquant
        "deploiements:\n  o/a: {depot: pas-un-repo, fichier: x}\n",
        "deploiements: [1]\n",
    ):
        f.write_text("name: p\nrepos: [o/a]\n" + bad)
        with pytest.raises(ConfigError):
            load_project(f)


def test_depots_github():
    api = "/repos/o/app"
    routes = {
        (api, None): (200, {"default_branch": "develop"}, None),
        (f"{api}/pulls", None): (200, [{"head": {}}, {"head": {}}, {"head": {}}], None),
        (f"{api}/commits/develop", None): (
            200,
            {"sha": "c" * 40, "html_url": "https://github.com/o/app/commit/ccc",
             "commit": {"message": "feat: x\n\ncorps", "committer": {"date": "2026-11-16T15:00:00Z"}}},
            None,
        ),
        ("/repos/o/deploy", None): (200, {"default_branch": "develop"}, None),
        ("/repos/o/deploy/contents/env/app.yaml", "develop"): (200, "image:\n  tag: " + "d" * 40 + "\n", None),
        (f"{api}/compare/{'d' * 40}...develop", None): (200, {"ahead_by": 4}, None),
    }
    backend = GitHubBackend("t", session=FakeSession(routes))
    project = Project("p", "P", ["o/app"], {"o/app": DeployTarget("o/deploy", "env/app.yaml")})
    (st,) = DepotsSource().collect(project, backend)
    assert st.error is None
    assert st.open_prs == 3 and not st.open_prs_capped
    assert st.last_commit.sha == "c" * 40 and st.last_commit.message == "feat: x"
    assert st.last_commit.date.isoformat() == "2026-11-16T15:00:00+00:00"
    assert st.deploy.version == "d" * 40 and st.deploy.en_attente == 4
    assert st.deploy.source_url == "https://github.com/o/deploy/blob/develop/env/app.yaml"


def test_commit_title():
    from scope_gen.models import commit_title

    assert commit_title("feat: x\n\ncorps") == "feat: x"
    assert commit_title("Merge pull request #14 from o/test/x\n\nAjout des tests front") == "Ajout des tests front (#14)"
    assert commit_title("Merge pull request #14 from o/test/x") == "Merge pull request #14 from o/test/x"
    assert commit_title("") is None and commit_title(None) is None



def test_config_sante(tmp_path):
    f = tmp_path / "p.yml"
    f.write_text("name: p\nrepos: [o/a]\nsante: http://app.local/health\n")
    assert load_project(f).sante == "http://app.local/health"
    f.write_text("name: p\nrepos: [o/a]\nsante: {url: https://app.example/health}\n")
    assert load_project(f).sante == "https://app.example/health"
    for bad in ("javascript:alert(1)", "app.local/health", '"http://x/<script>"'):
        f.write_text(f"name: p\nrepos: [o/a]\nsante: {bad}\n")
        with pytest.raises(ConfigError):
            load_project(f)


def test_bandeau_projet(local_repos, projects_dir, tmp_path):
    build(projects_dir, tmp_path / "site", LocalBackend(local_repos))
    page = (tmp_path / "site" / "demo" / "index.html").read_text()
    head = page.split('<div class="layout"')[0]
    assert '<div class="project-head">' in head and "Dernier prompt" in head
    assert "1 commit(s) · 1 dépôt(s)" in head  # À déployer
    assert 'id="health" data-url="http://localhost:8080/sante-demo.json"' in head
    assert "PR ouvertes" not in head  # inconnu en local
    assert 'data-repo-name="demo-api"' in page and 'class="live" hidden' in page
