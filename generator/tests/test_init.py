"""`./scope.sh init` : consigne, exclusion git, .scope/projet, hook. Idempotent."""

import json
import subprocess
from pathlib import Path

import pytest

from scope_gen import admin


def clone(tmp_path: Path, nom: str = "app") -> Path:
    d = tmp_path / nom
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    return d


def test_init_complet_puis_idempotent(tmp_path, capsys):
    d = clone(tmp_path)
    (d / "CLAUDE.md").write_text("# Mon projet\n\nRègles existantes.\n")
    assert admin.main(["boutique", str(d), "--lang", "fr"]) == 0

    claude = (d / "CLAUDE.md").read_text()
    assert claude.startswith("# Mon projet\n\nRègles existantes.\n\n<!-- scope:start -->")
    assert "projet `boutique`" in claude and "statut: attente" in claude
    assert (d / "AGENTS.md").read_text() == claude.split("\n\n", 2)[2]
    exclude = (d / ".git" / "info" / "exclude").read_text()
    assert ".scope/\n" in exclude and ".claude/settings.local.json" in exclude
    assert (d / ".scope" / "projet").read_text() == "boutique\n"
    assert (d / ".scope" / "rapports").is_dir()
    assert (d / ".scope" / "hooks" / "scope_hook.py").exists()
    settings = json.loads((d / ".claude" / "settings.local.json").read_text())
    stop = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert stop.endswith('.scope/hooks/scope_hook.py" fin --lang fr')

    # Rien n'est commité, et git ne voit ni .scope/ ni settings.local.json.
    status = subprocess.run(["git", "-C", str(d), "status", "--porcelain"], capture_output=True, text=True).stdout
    assert sorted(status.split()) == ["??", "??", "AGENTS.md", "CLAUDE.md"]
    assert "Rien n'a été commité" in capsys.readouterr().out

    suivis = [p for p in d.rglob("*") if p.is_file() and (".git" not in p.relative_to(d).parts or p.name == "exclude")]
    avant = {p: p.read_bytes() for p in suivis}
    assert admin.main(["boutique", str(d), "--lang", "fr"]) == 0
    apres = {p: p.read_bytes() for p in avant}
    assert apres == avant
    assert "CLAUDE.md : inchangé" in capsys.readouterr().out


def test_mise_a_jour_langue_et_projet(tmp_path):
    d = clone(tmp_path)
    admin.main(["boutique", str(d)])
    assert "project `boutique`" in (d / "CLAUDE.md").read_text()  # anglais par défaut
    admin.main(["boutique", str(d), "--lang", "fr"])
    claude = (d / "CLAUDE.md").read_text()
    assert claude.count("<!-- scope:start -->") == 1 and "projet `boutique`" in claude
    assert (d / ".scope" / "projet").read_text() == "boutique\n"
    settings = json.loads((d / ".claude" / "settings.local.json").read_text())
    assert len(settings["hooks"]["Stop"]) == 1 and "--lang fr" in settings["hooks"]["Stop"][0]["hooks"][0]["command"]


def test_hook_conserve_les_reglages_existants(tmp_path):
    d = clone(tmp_path)
    f = d / ".claude" / "settings.local.json"
    f.parent.mkdir()
    autre = {"hooks": [{"type": "command", "command": "echo autre"}]}
    f.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"Stop": [autre]}}))
    admin.main(["p", str(d)])
    s = json.loads(f.read_text())
    assert s["permissions"] == {"allow": ["Bash(ls)"]}
    assert s["hooks"]["Stop"][0] == autre and len(s["hooks"]["Stop"]) == 2
    assert len(s["hooks"]["UserPromptSubmit"]) == 1


def test_settings_invalide(tmp_path, capsys):
    d = clone(tmp_path)
    (d / ".claude").mkdir()
    (d / ".claude" / "settings.local.json").write_text("{pas du json")
    assert admin.main(["p", str(d)]) == 1
    assert "JSON invalide" in capsys.readouterr().out


def test_plusieurs_clones_et_erreurs(tmp_path, capsys):
    a, b = clone(tmp_path, "a"), clone(tmp_path, "b")
    pas_git = tmp_path / "c"
    pas_git.mkdir()
    assert admin.main(["p", str(a), str(b), str(pas_git), str(tmp_path / "absent")]) == 1
    out = capsys.readouterr().out
    assert out.count("ERREUR") == 2 and (a / "AGENTS.md").exists() and (b / "AGENTS.md").exists()


def test_signale_les_anciens_rapports_suivis(tmp_path, capsys):
    d = clone(tmp_path)
    (d / ".scope" / "rapports").mkdir(parents=True)
    (d / ".scope" / "rapports" / "x.md").write_text("x")
    subprocess.run(["git", "-C", str(d), "add", "-f", ".scope"], check=True)
    admin.main(["p", str(d)])
    assert "1 ancien(s) rapport(s) encore suivi(s)" in capsys.readouterr().out


def test_nom_de_projet_invalide(tmp_path):
    assert admin.main(["../x", str(clone(tmp_path))]) == 1


def test_upsert_block(tmp_path):
    f = tmp_path / "X.md"
    bloc = "<!-- scope:start -->\nA\n<!-- scope:end -->"
    assert admin.upsert_block(f, bloc) == "créé"
    assert admin.upsert_block(f, bloc) == "inchangé"
    assert admin.upsert_block(f, bloc.replace("A", "B")) == "remplacé"
    f.write_text("texte sans fin de ligne")
    assert admin.upsert_block(f, bloc) == "ajouté" and f.read_text().startswith("texte sans fin de ligne\n\n<!--")
    with pytest.raises(admin.AdminError):
        admin.upsert_block(f, "sans marqueurs")
