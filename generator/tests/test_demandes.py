"""Parser des rapports : français, anglais, ancien format, rapports cassés."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from scope_gen.demandes import ATTENTE, EN_COURS, ECHEC, ILLISIBLE, TERMINE, lire, parse_points


def ecrire(tmp_path: Path, texte: str, nom: str = "2026-11-17-103000-login.md") -> Path:
    f = tmp_path / nom
    f.write_text(texte, encoding="utf-8")
    return f


def parse(tmp_path, texte, nom="2026-11-17-103000-login.md"):
    return lire(ecrire(tmp_path, texte, nom), "boutique-front", "acme/boutique-front")


FR = """---
projet: boutique
repo: boutique-front
agent: claude-code
branche: feat/login-google
demande: "Page de login avec authentification Google"
statut: attente
actions: [code, commit]
debut: 2026-11-17T10:30:00Z
maj: 2026-11-17T10:42:00Z
pr: 42
---

## Résumé
Page codée, il manque le Client ID.

## Pour vous
- Question : quel Client ID Google dois-je utiliser ?
- Remarque : déclarez http://localhost:3000/auth/callback dans la console Google.

## Détail
Fichiers modifiés.
"""


def test_format_francais(tmp_path):
    d = parse(tmp_path, FR)
    assert d.valide and d.statut == ATTENTE and not d.ancien_format
    assert (d.projet, d.repo, d.agent, d.branche) == ("boutique", "boutique-front", "claude-code", "feat/login-google")
    assert d.demande == "Page de login avec authentification Google"
    assert d.actions == ["code", "commit"] and d.pr == 42
    assert d.debut == datetime(2026, 11, 17, 10, 30, tzinfo=timezone.utc)
    assert d.maj == datetime(2026, 11, 17, 10, 42, tzinfo=timezone.utc)
    assert [q.texte for q in d.questions] == ["quel Client ID Google dois-je utiliser ?"]
    assert [r.texte for r in d.remarques] == ["déclarez http://localhost:3000/auth/callback dans la console Google."]
    assert d.detail_md == "Fichiers modifiés." and d.avertissements == []


def test_format_anglais(tmp_path):
    d = parse(tmp_path, """---
project: boutique
Status: Waiting
request: Login page
actions: code, Commit, pull-request
started: 2026-11-17T10:30:00Z
updated: 2026-11-17T10:31:00+01:00
branch: main
---

## Summary
Waiting for the client id.

## For you
- Question: which Client ID?
- Note: the callback URL must be declared.

## Details
Some details.
""")
    assert d.valide and d.statut == ATTENTE and d.projet == "boutique" and d.branche == "main"
    assert d.actions == ["code", "commit", "pr"]
    assert d.maj == datetime(2026, 11, 17, 9, 31, tzinfo=timezone.utc)
    assert len(d.questions) == 1 and len(d.remarques) == 1 and d.detail_md == "Some details."


@pytest.mark.parametrize(
    "brut, attendu",
    [("en-cours", EN_COURS), ("in-progress", EN_COURS), ("En cours", EN_COURS), ("waiting", ATTENTE),
     ("bloque", ATTENTE), ("bloqué", ATTENTE), ("done", TERMINE), ("terminé", TERMINE),
     ("pr-ouverte", TERMINE), ("failed", ECHEC), ("échec", ECHEC)],
)
def test_alias_de_statut(tmp_path, brut, attendu):
    d = parse(tmp_path, f"---\nstatut: {brut}\n---\n## Résumé\nx\n")
    assert d.valide and d.statut == attendu


def test_ancien_format(tmp_path):
    d = parse(tmp_path, """---
date: 2026-11-16T10:30:00Z
projet: boutique
repo: boutique-front
agent: claude-code
branche: feat/login
commit_message: "feat: login"
pr_titre: "Login"
pr_numero: "#12"
statut: bloque
---

## Résumé court
Il faut un token.

## Détail
x

## Prochaine étape
- Ajouter le token dans .env
- Relancer
""")
    assert d.valide and d.ancien_format and d.statut == ATTENTE
    assert d.debut == d.maj == datetime(2026, 11, 16, 10, 30, tzinfo=timezone.utc)
    assert d.resume == "Il faut un token."
    # En attente, tout « Prochaine étape » est ce que l'humain doit faire.
    assert [q.texte for q in d.questions] == ["Ajouter le token dans .env", "Relancer"]
    assert d.pr == 12


def test_ancien_pr_ouverte_devient_termine_avec_action_pr(tmp_path):
    d = parse(tmp_path, "---\ndate: 2026-11-16T10:30:00Z\nstatut: pr-ouverte\n---\n## Résumé court\nPR ouverte.\n")
    assert d.statut == TERMINE and d.actions == ["pr"] and d.ancien_format


def test_dates_par_defaut_depuis_le_nom_du_fichier(tmp_path):
    d = parse(tmp_path, "---\nstatut: en-cours\n---\n## Résumé\nx\n", "2026-11-15-080910-x.md")
    assert d.debut == d.maj == datetime(2026, 11, 15, 8, 9, 10, tzinfo=timezone.utc)


def test_resume_absent_mais_demande_presente(tmp_path):
    d = parse(tmp_path, "---\nstatut: en-cours\ndemande: Créer la page\n---\n")
    assert d.valide and d.resume == "Créer la page"


def test_avertissements(tmp_path):
    d = parse(tmp_path, "---\nstatut: attente\nactions: [code, danse]\npr: abc\n---\n## Résumé\nx\n## Pour vous\n- Remarque : r\n")
    assert d.valide and d.actions == ["code"]
    assert any("danse" in a for a in d.avertissements)
    assert any("PR invalide" in a for a in d.avertissements)
    assert any("sans question" in a for a in d.avertissements)
    d = parse(tmp_path, "---\nstatut: termine\n---\n## Résumé\nx\n## Pour vous\n- Question : ok ?\n")
    assert any("question présente" in a for a in d.avertissements)


@pytest.mark.parametrize(
    "texte, erreur",
    [
        ("pas d'en-tête", "en-tête YAML absent"),
        ("---\nstatut: termine\n", "non fermé"),
        ("---\nstatut: [termine\n---\n## Résumé\nx\n", "YAML invalide"),
        ("---\n- a\n- b\n---\n", "dictionnaire"),
        ("---\nprojet: x\n---\n## Résumé\nx\n", "statut"),
        ("---\nstatut: peut-etre\n---\n## Résumé\nx\n", "statut inconnu"),
        ("---\nstatut: termine\n---\nrien\n", "Résumé"),
        ("---\nstatut: termine\nmaj: hier\n---\n## Résumé\nx\n", "maj invalide"),
    ],
)
def test_rapports_illisibles(tmp_path, texte, erreur):
    d = parse(tmp_path, texte)
    assert not d.valide and d.statut == ILLISIBLE and erreur in d.erreur
    assert d.debut is not None  # date tirée du nom de fichier


def test_fichier_binaire_ou_enorme(tmp_path):
    f = tmp_path / "2026-11-17-103000-bin.md"
    f.write_bytes(b"\xff\xfe\x00")
    assert not lire(f, "r", "r").valide
    f.write_text("---\nstatut: termine\n---\n## Résumé\n" + "x" * 300_000)
    assert "trop gros" in lire(f, "r", "r").erreur


def test_points_multilignes_et_paragraphes():
    pts = parse_points("""Un paragraphe d'introduction.

- **Question :** faut-il
  un lien « mot de passe oublié » ?
- [ ] Q: autre ?
1. Note: numérotée
- simple ligne

```
- pas un point
```""")
    assert [(p.nature, p.texte) for p in pts] == [
        ("remarque", "Un paragraphe d'introduction."),
        ("question", "faut-il\nun lien « mot de passe oublié » ?"),
        ("question", "autre ?"),
        ("remarque", "numérotée"),
        ("remarque", "simple ligne\n\n```\n- pas un point\n```"),
    ]


def test_to_dict(tmp_path):
    d = parse(tmp_path, FR).to_dict()
    assert d["statut"] == "attente" and d["questions"] and d["maj"] == "2026-11-17T10:42:00Z"
    assert d["id"].startswith("d-2026-11-17-103000-login-")
