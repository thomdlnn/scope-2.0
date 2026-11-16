"""Token par projet (avec repli sur le token global) et bouton « Actualiser »."""

import json

from scope_gen import cli
from scope_gen.backends import LocalBackend
from scope_gen.models import Project


def test_secret_env_puis_scope_secrets(monkeypatch):
    monkeypatch.delenv("SCOPE_TOKEN_X", raising=False)
    monkeypatch.setenv("SCOPE_SECRETS", json.dumps({"SCOPE_TOKEN_X": "depuis-secrets"}))
    assert cli.secret("SCOPE_TOKEN_X") == "depuis-secrets"
    monkeypatch.setenv("SCOPE_TOKEN_X", "depuis-env")
    assert cli.secret("SCOPE_TOKEN_X") == "depuis-env"
    monkeypatch.setenv("SCOPE_SECRETS", "pas du json")
    monkeypatch.delenv("SCOPE_TOKEN_X")
    assert cli.secret("SCOPE_TOKEN_X") is None


def test_token_dedie_ou_global(monkeypatch):
    monkeypatch.setenv("SCOPE_GH_TOKEN", "global")
    monkeypatch.setenv("SCOPE_SECRETS", json.dumps({"SCOPE_TOKEN_A": "dedie-a"}))
    for_project = cli.github_backend_factory()
    token = lambda p: for_project(p).s.headers["Authorization"]  # noqa: E731
    assert token(Project("a", "A", ["o/a"], token="SCOPE_TOKEN_A")) == "Bearer dedie-a"
    assert token(Project("b", "B", ["o/b"])) == "Bearer global"
    assert token(Project("c", "C", ["o/c"], token="SCOPE_TOKEN_ABSENT")) == "Bearer global"  # repli
    # un backend (et son cache) par token
    assert for_project(Project("b", "B", ["o/b"])) is for_project(Project("c", "C", ["o/c"]))


def test_bouton_actualiser_recharge_la_page(local_repos, projects_dir, tmp_path):
    cli.build(projects_dir, tmp_path / "a", LocalBackend(local_repos))
    for page in ("index.html", "demo/index.html"):
        html = (tmp_path / "a" / page).read_text()
        assert '<a class="refresh" id="refresh" href=""' in html
        assert "github.com" not in html.split("</header>")[0]
        assert 'class="age"' in html


def test_projet_scope_lu_avec_le_token_de_l_action(monkeypatch):
    monkeypatch.setenv("SCOPE_GH_TOKEN", "global")
    monkeypatch.setenv("GITHUB_TOKEN", "action")
    monkeypatch.delenv("SCOPE_SECRETS", raising=False)
    backend = cli.github_backend_factory()(Project("scope", "SCOPE", ["o/scope"], token="GITHUB_TOKEN"))
    assert backend.s.headers["Authorization"] == "Bearer action"
