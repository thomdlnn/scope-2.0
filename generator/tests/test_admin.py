"""Tests de l'outil d'administration (./scope.sh init | consigne)."""

import subprocess
from pathlib import Path

import pytest
import yaml

from scope_gen import admin
from scope_gen.config import load_project

ROOT = Path(__file__).resolve().parents[2]
BLOCK = "<!-- scope:start -->\n## SCOPE\nv1\n<!-- scope:end -->\n"


def test_upsert_bloc_cree_ajoute_remplace_inchange(tmp_path):
    f = tmp_path / "CLAUDE.md"
    assert admin.upsert_block(f, BLOCK) == "créé"
    assert admin.upsert_block(f, BLOCK) == "inchangé"
    f.write_text("# Projet\n\nRègles existantes.")
    assert admin.upsert_block(f, BLOCK) == "ajouté"
    assert f.read_text() == "# Projet\n\nRègles existantes.\n\n" + BLOCK
    f.write_text(f.read_text() + "\n## Après\nreste\n")
    assert admin.upsert_block(f, BLOCK.replace("v1", "v2")) == "remplacé"
    text = f.read_text()
    assert "v2" in text and "v1" not in text and text.count("scope:start") == 1
    assert text.startswith("# Projet") and text.endswith("## Après\nreste\n")


def test_consigne_contient_le_projet():
    c = admin.consigne("boutique", ROOT)
    assert "projet `boutique`" in c and "{{PROJET}}" not in c
    assert c.startswith(admin.START) and c.rstrip().endswith(admin.END)


@pytest.mark.parametrize(
    "answer,expected",
    [("", [0, 1, 2, 3]), ("tous", [0, 1, 2, 3]), ("1,3", [0, 2]), ("2-4", [1, 2, 3]), (" 4, 1 ", [0, 3])],
)
def test_selection(answer, expected):
    assert admin.parse_selection(answer, 4) == expected


@pytest.mark.parametrize("answer", ["0", "5", "abc"])
def test_selection_invalide(answer):
    with pytest.raises((admin.AdminError, ValueError)):
        admin.parse_selection(answer, 4)


def test_secret_name():
    assert admin.secret_name("mon-projet") == "SCOPE_TOKEN_MON_PROJET"


def test_write_project_conserve_les_reglages(tmp_path):
    f = tmp_path / "p.yml"
    f.write_text(
        "name: p\ntitle: P\nrepos: [o/a, o/b]\n"
        "deploiements:\n  o/a: {depot: o/d, fichier: a.yaml}\n  o/b: {depot: o/d, fichier: b.yaml}\n"
    )
    admin.write_project(f, "p", "Projet P", ["o/a", "o/c"], "SCOPE_TOKEN_P")
    p = load_project(f)
    assert (p.title, p.repos, p.token) == ("Projet P", ["o/a", "o/c"], "SCOPE_TOKEN_P")
    assert list(p.deploiements) == ["o/a"]  # o/b retiré du projet
    admin.write_project(f, "p", "Projet P", ["o/c"], None)
    data = yaml.safe_load(f.read_text())
    assert "token" not in data and "deploiements" not in data


class FakeReader:
    def __init__(self, token):
        assert token == "tok"

    def readable_repos(self):
        return ["moi/boutique-api", "moi/boutique-front", "moi/autre"]

    def can_read(self, repo):
        return repo.startswith("moi/")


def _sandbox(tmp_path):
    root = tmp_path / "scope"
    (root / "templates").mkdir(parents=True)
    (root / "templates" / "instructions-ia.md").write_text((ROOT / "templates" / "instructions-ia.md").read_text())
    clones = tmp_path / "clones"
    for name in ("boutique-api", "boutique-front"):
        (clones / name).mkdir(parents=True)
    (clones / "boutique-front" / "AGENTS.md").write_text("# Règles front\n")
    return root, clones


def _args(root, clones, *extra):
    import argparse

    ns = argparse.Namespace(
        projet="boutique", titre="Boutique", repos=None, token_dedie=False, token_global=False,
        clones=str(clones), dry_run=True, offline=True, yes=False, root=str(root), env=None,
    )
    for k, v in extra:
        setattr(ns, k, v)
    return ns


def test_init_choix_des_depots_et_consigne(tmp_path, monkeypatch, capsys):
    root, clones = _sandbox(tmp_path)
    monkeypatch.setenv("SCOPE_TOKEN", "tok")
    monkeypatch.setenv("SCOPE_REPO", "moi/scope")
    monkeypatch.setattr("builtins.input", lambda _prompt: "1,2")
    assert admin.cmd_init(_args(root, clones), reader_factory=FakeReader) == 0

    p = load_project(root / "projects" / "boutique.yml")
    assert p.repos == ["moi/boutique-api", "moi/boutique-front"] and p.token is None  # pas de global : token global
    for name in ("boutique-api", "boutique-front"):
        assert (clones / name / ".scope" / "rapports" / ".gitkeep").exists()
        assert "projet `boutique`" in (clones / name / "CLAUDE.md").read_text()
    agents = (clones / "boutique-front" / "AGENTS.md").read_text()
    assert agents.startswith("# Règles front") and "scope:start" in agents
    out = capsys.readouterr().out
    assert "(dry-run) secret SCOPE_GH_TOKEN" in out and "AGENTS.md ajouté" in out


def test_init_token_dedie_et_depot_illisible(tmp_path, monkeypatch, capsys):
    root, clones = _sandbox(tmp_path)
    monkeypatch.setenv("SCOPE_TOKEN", "tok")
    monkeypatch.setenv("SCOPE_REPO", "moi/scope")
    args = _args(root, clones, ("repos", "moi/boutique-api"), ("token_dedie", True))
    assert admin.cmd_init(args, reader_factory=FakeReader) == 0
    assert load_project(root / "projects" / "boutique.yml").token == "SCOPE_TOKEN_BOUTIQUE"

    args = _args(root, clones, ("repos", "autre/prive"))
    with pytest.raises(admin.AdminError, match="ne lit pas"):
        admin.cmd_init(args, reader_factory=FakeReader)


def test_scope_sh_aide():
    res = subprocess.run([str(ROOT / "scope.sh"), "help"], capture_output=True, text=True)
    assert res.returncode == 0 and "./scope.sh init <projet>" in res.stdout and "./scope.sh up" in res.stdout
    assert subprocess.run([str(ROOT / "scope.sh"), "inconnue"], capture_output=True).returncode == 2


def test_apply_consigne_supprime_les_fichiers_obsoletes(tmp_path):
    wf = tmp_path / ".github" / "workflows" / "notify-scope.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text("ancien")
    changes = admin.apply_consigne(tmp_path, BLOCK)
    assert not wf.exists() and changes[".github/workflows/notify-scope.yml"] == "supprimé (obsolète)"
    assert admin.apply_consigne(tmp_path, BLOCK) == {"CLAUDE.md": "inchangé", "AGENTS.md": "inchangé"}


def test_init_mode_env(tmp_path, monkeypatch, capsys):
    root, clones = _sandbox(tmp_path)
    env = root / ".env"
    env.write_text("# commentaire\nSCOPE_PORT=8080\nSCOPE_GH_TOKEN=ancien\n")
    monkeypatch.setenv("SCOPE_TOKEN", "tok")
    monkeypatch.delenv("SCOPE_REPO", raising=False)
    args = _args(root, clones, ("repos", "moi/boutique-api"), ("env", str(env)), ("yes", True))
    assert admin.cmd_init(args, reader_factory=FakeReader) == 0
    # un global existe déjà et --yes : token dédié, global conservé
    assert admin.read_env(env) == {"SCOPE_PORT": "8080", "SCOPE_GH_TOKEN": "ancien", "SCOPE_TOKEN_BOUTIQUE": "tok"}
    assert env.stat().st_mode & 0o777 == 0o600
    assert load_project(root / "projects" / "boutique.yml").token == "SCOPE_TOKEN_BOUTIQUE"
    out = capsys.readouterr().out
    assert f"SCOPE_TOKEN_BOUTIQUE enregistré dans {env}" in out and "./scope.sh up" in out
    assert "secret " not in out  # aucun secret GitHub en mode .env


def test_write_env_remplace(tmp_path):
    env = tmp_path / ".env"
    admin.write_env(env, "A", "1")
    admin.write_env(env, "B", "2")
    admin.write_env(env, "A", "3")
    assert env.read_text() == "A=3\nB=2\n"
