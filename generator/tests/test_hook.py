"""Hook Claude Code : rappel à la fin d'un tour qui modifie le dépôt sans rapport."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "templates" / "hooks" / "scope_hook.py"


@pytest.fixture
def depot(tmp_path):
    d = tmp_path / "app"
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    (d / ".git" / "info" / "exclude").write_text(".scope/\n")
    (d / "a.txt").write_text("a")
    subprocess.run(["git", "-C", str(d), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], check=True
    )
    (d / ".scope" / "rapports").mkdir(parents=True)
    return d


def hook(depot: Path, phase: str, lang: str = "fr", **entree) -> str:
    entree.setdefault("session_id", "s1")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(depot)}
    res = subprocess.run(
        [sys.executable, str(HOOK), phase, "--lang", lang],
        input=json.dumps(entree), capture_output=True, text=True, env=env, check=True,
    )
    return res.stdout.strip()


def test_tour_sans_changement(depot):
    hook(depot, "debut")
    assert hook(depot, "fin") == ""


def test_changement_sans_rapport_bloque_une_fois(depot):
    hook(depot, "debut")
    (depot / "a.txt").write_text("modifié")
    out = json.loads(hook(depot, "fin"))
    assert out["decision"] == "block" and ".scope/rapports/" in out["reason"]
    assert hook(depot, "fin", stop_hook_active=True) == ""


def test_rappel_en_anglais(depot):
    hook(depot, "debut", "en")
    (depot / "nouveau.txt").write_text("x")
    assert "no report was created" in json.loads(hook(depot, "fin", "en"))["reason"]


def test_fichier_deja_modifie_puis_remodifie(depot):
    (depot / "a.txt").write_text("v1")
    hook(depot, "debut")
    time.sleep(0.01)
    (depot / "a.txt").write_text("v2 plus longue")
    assert json.loads(hook(depot, "fin"))["decision"] == "block"


def test_commit_pendant_le_tour(depot):
    hook(depot, "debut")
    (depot / "b.txt").write_text("b")
    subprocess.run(["git", "-C", str(depot), "add", "."], check=True)
    subprocess.run(["git", "-C", str(depot), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "b"], check=True)
    assert json.loads(hook(depot, "fin"))["decision"] == "block"


def test_rapport_mis_a_jour_pendant_le_tour(depot):
    hook(depot, "debut")
    (depot / "a.txt").write_text("modifié")
    (depot / ".scope" / "rapports" / "2026-11-17-100000-x.md").write_text("---\nstatut: termine\n---\n")
    assert hook(depot, "fin") == ""


def test_debut_inconnu_ou_hors_depot(depot, tmp_path):
    (depot / "a.txt").write_text("modifié")
    assert hook(depot, "fin", session_id="autre") == ""
    ailleurs = tmp_path / "pas-git"
    ailleurs.mkdir()
    assert hook(ailleurs, "debut") == "" and hook(ailleurs, "fin") == ""


def test_entree_invalide_ne_casse_rien(depot):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(depot)}
    res = subprocess.run([sys.executable, str(HOOK), "fin"], input="pas du json", capture_output=True, text=True, env=env)
    assert res.returncode == 0 and res.stdout == ""
