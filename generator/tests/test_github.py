"""Token optionnel : dépôts déduits des clones, état lu sur l'API GitHub (simulée)."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scope_gen import cli
from scope_gen.backends import GitHubBackend
from scope_gen.backends.github import REPO_DENIED, TOKEN_REFUSED
from scope_gen.config import ConfigError, load_project, load_projects
from scope_gen.locale import origine_github
from scope_gen.models import DeployTarget, commit_title
from scope_gen.render import write_site
from scope_gen.sources import EtatGitHub, collect, status
from scope_gen.sources.depots import lookup
from tests.fixtures.github import API_SHA, FRONT_DEPLOYE, FRONT_SHA, ROUTES, FakeSession
from tests.fixtures.racine import construire, depot

T = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
PROJETS = Path(__file__).parent / "fixtures" / "projects"


def backend(routes=None):
    return GitHubBackend("t", session=FakeSession(routes))


# --- Dépôts déduits des clones -------------------------------------------------------
@pytest.mark.parametrize(
    "url, attendu",
    [
        ("git@github.com:acme/app.git", "acme/app"),
        ("https://github.com/acme/app", "acme/app"),
        ("https://github.com/acme/app.git/", "acme/app"),
        ("ssh://git@github.com/acme/my.app.git", "acme/my.app"),
        ("https://user:jeton@github.com/acme/app.git", "acme/app"),
        ("git@gitlab.com:acme/app.git", None),
    ],
)
def test_origine_github(tmp_path, url, attendu):
    d = depot(tmp_path, "x", origin=url)
    assert origine_github(d) == attendu


def test_origine_absente_ou_worktree(tmp_path):
    assert origine_github(depot(tmp_path, "sans")) is None
    principal = depot(tmp_path, "principal", origin="git@github.com:acme/app.git")
    wtdir = principal / ".git" / "worktrees" / "wt"
    wtdir.mkdir(parents=True)
    (wtdir / "commondir").write_text("../..\n")
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {wtdir}\n")
    assert origine_github(wt) == "acme/app"


# --- Backend et état d'un dépôt ---------------------------------------------------------
def test_etat_complet_avec_prs_et_deploiement():
    st = status("acme/demo-front", DeployTarget("acme/demo-deploy", "environments/local/demo-front.yaml"), backend())
    assert st.error is None and st.warning is None and st.default_branch == "main"
    assert [(p.number, p.auteur, p.brouillon) for p in st.prs] == [(12, "alice", False), (13, "dependabot[bot]", True)]
    assert st.last_commit.sha == FRONT_SHA and st.last_commit.message == "feat(front): en-tête"
    assert st.deploy.version == FRONT_DEPLOYE and st.deploy.en_attente == 2
    assert st.deploy.source_url == "https://github.com/acme/demo-deploy/blob/main/environments/local/demo-front.yaml"
    d = st.to_dict()
    assert d["prs"][0]["maj"] == "2026-11-17T09:00:00Z" and d["last_commit"]["short"] == FRONT_SHA[:7]


def test_prs_illisibles_403_le_reste_est_lu():
    st = status("acme/demo-api", DeployTarget("acme/demo-deploy", "environments/local/demo-api.yaml"), backend())
    assert st.error is None and st.prs is None and "Pull requests" in st.warning
    assert st.last_commit.message == "Corrige la pagination (#4)"
    assert st.deploy.en_attente == 0


def test_depot_introuvable_et_token_refuse():
    assert status("acme/absent", None, backend()).error == REPO_DENIED
    refus = {k: (401, {"message": "Bad credentials"}) for k in ROUTES}
    assert status("acme/demo-front", None, backend(refus)).error == TOKEN_REFUSED


def test_deploiement_fichier_ou_cle_absents():
    b = backend()
    st = status("acme/demo-front", DeployTarget("acme/demo-deploy", "absent.yaml"), b)
    assert "introuvable" in st.deploy.error
    st = status("acme/demo-front", DeployTarget("acme/demo-deploy", "environments/local/demo-front.yaml", cle="x.y"), b)
    assert "clé x.y absente" in st.deploy.error


def test_collect_dedoublonne_et_cache_http():
    s = FakeSession()
    b = GitHubBackend("t", session=s)
    out = collect([("acme/demo-front", None), ("acme/demo-front", None), ("acme/demo-api", None)], b)
    assert len(out) == 2
    assert s.calls.count("/repos/acme/demo-front") == 1


def test_lookup_et_commit_title():
    assert lookup({"image": {"tag": "abc"}}, "image.tag") == "abc"
    assert lookup(None, "image.tag") is None
    assert commit_title("Merge pull request #14 from o/x") == "Merge pull request #14 from o/x"
    assert commit_title("") is None


# --- Tâche de fond ------------------------------------------------------------------------
def attendre(cond, timeout=5):
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_etat_en_tache_de_fond():
    appels = []

    def factory():
        appels.append(1)
        return backend()

    etat = EtatGitHub(factory, intervalle=3600)
    premier = etat.voir([("acme/demo-front", None)])
    assert list(premier) == [("acme/demo-front", None)]  # rendu tout de suite, lu ou non
    assert attendre(lambda: etat.voir([("acme/demo-front", None)])[("acme/demo-front", None)] is not None)
    # Un nouveau dépôt réveille la tâche de fond sans attendre l'intervalle.
    etat.voir([("acme/demo-front", None), ("acme/demo-api", None)])
    assert attendre(lambda: etat.voir([("acme/demo-front", None), ("acme/demo-api", None)])[("acme/demo-api", None)] is not None)
    assert len(appels) == 2


def test_sans_token_pas_de_github(monkeypatch):
    monkeypatch.delenv("SCOPE_GH_TOKEN", raising=False)
    assert cli.github_depuis_env() is None
    monkeypatch.setenv("SCOPE_GH_TOKEN", "t")
    monkeypatch.setenv("SCOPE_GH_INTERVAL", "120")
    assert cli.github_depuis_env().intervalle == 120


# --- Réglages optionnels ----------------------------------------------------------------
def test_reglages_optionnels():
    reglages, erreurs = load_projects(PROJETS)
    assert set(reglages) == {"demo"} and len(erreurs) == 1 and "casse.yml" in erreurs[0]
    assert reglages["demo"].sante == "http://127.0.0.1:9999/sante-demo.json"
    assert set(reglages["demo"].deploiements) == {"acme/demo-front", "acme/demo-api"}
    assert load_projects(PROJETS / "absent") == ({}, [])


def test_sante_valide(tmp_path):
    f = tmp_path / "p.yml"
    f.write_text("sante: {url: https://app.example/health}\n")
    assert load_project(f).sante == "https://app.example/health"
    for bad in ("javascript:alert(1)", "app.local/health", '"http://x/<script>"'):
        f.write_text(f"sante: {bad}\n")
        with pytest.raises(ConfigError):
            load_project(f)


# --- Page ---------------------------------------------------------------------------------
def preparer(tmp_path, avec_token=True):
    racine = construire(tmp_path / "racine", T)
    gh = EtatGitHub(backend) if avec_token else None
    return cli.preparer(cli.Config(racine, 4, PROJETS, gh), synchrone=True)


def test_sans_token_comme_en_phase_1(tmp_path):
    projets, erreurs = preparer(tmp_path, avec_token=False)
    demo = next(p for p in projets if p.slug == "demo")
    assert demo.etats is None and demo.reglages.sante
    write_site(tmp_path / "s", projets, T, alertes=erreurs)
    page = (tmp_path / "s" / "demo" / "index.html").read_text()
    assert 'id="sidebar"' not in page and "PR ouvertes" not in page
    assert 'id="health"' in page  # la santé ne dépend pas du token
    assert "Réglages ignorés" in (tmp_path / "s" / "index.html").read_text()


def test_avec_token_panneau_des_depots(tmp_path):
    projets, erreurs = preparer(tmp_path)
    demo = next(p for p in projets if p.slug == "demo")
    assert [r for r, _st in demo.etats] == ["acme/demo-api", "acme/demo-front"]
    assert demo.prs_ouvertes == 2
    outils = next(p for p in projets if p.slug == "outils")
    assert outils.etats == [] and [d.nom for d in outils.sans_github] == ["scope-cli"]

    out = tmp_path / "s"
    write_site(out, projets, T, alertes=erreurs)
    page = (out / "demo" / "index.html").read_text()
    assert 'id="sidebar"' in page and 'class="wide"' in page
    assert "#12 Page de login Google" in page and "dependabot[bot]" in page and ">brouillon<" in page
    assert "PR non lues" in page and "2 commit(s) à déployer" in page and "à jour" in page
    assert "Corrige la pagination (#4)" in page
    assert 'data-filtre-depot="demo-front"' in page
    assert "2 PR ouverte(s)" in (out / "index.html").read_text()
    data = json.loads((out / "data.json").read_text())
    gh = next(p for p in data["projets"] if p["slug"] == "demo")["github"]
    assert gh[1]["etat"]["last_commit"]["sha"] == FRONT_SHA
    assert gh[0]["etat"]["deploy"]["version"] == API_SHA
    for f in out.rglob("*"):
        if f.is_file():
            assert "SECRET" not in f.read_text(), f  # identifiants du remote jamais affichés


def test_cycle_avec_github_en_tache_de_fond(tmp_path):
    racine = construire(tmp_path / "racine", T)
    def lent():
        time.sleep(0.5)  # GitHub lent : le premier rendu n'attend pas
        return backend()

    cfg = cli.Config(racine, 4, PROJETS, EtatGitHub(lent, intervalle=3600))
    site = tmp_path / "site"
    site.mkdir()
    cli.cycle(site, cfg, 3)
    assert "lecture en cours" in (site / "current" / "demo" / "index.html").read_text()
    assert attendre(lambda: cli.cycle(site, cfg, 3) or "#12 Page de login" in (site / "current" / "demo" / "index.html").read_text())
