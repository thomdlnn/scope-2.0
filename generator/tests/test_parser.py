from datetime import datetime, timezone

from scope_gen.models import RawReport
from scope_gen.parser import dedupe, parse_report

VALIDE = """---
date: 2026-11-16T10:30:00Z
projet: mon-projet
repo: mon-projet-front
agent: claude-code
branche: feat/login
commit_message: "feat(front): ajout de la page de login"
pr_titre: "Ajout de la page de login"
pr_numero: 42
statut: termine
---

## Résumé court
Une ligne : quoi, où,
références.

## Détail
- fichier `a.py`

```
## pas une section
```

## Prochaine étape
Relire la PR.
"""


def raw(content, name="2026-11-16-103000-test.md", ref="main"):
    return RawReport("o/mon-projet-front", f".scope/rapports/{name}", ref, content)


def test_rapport_valide():
    r = parse_report(raw(VALIDE))
    assert r.valid, r.error
    assert r.date == datetime(2026, 11, 16, 10, 30, tzinfo=timezone.utc)
    assert r.statut == "termine"
    assert r.agent == "claude-code"
    assert r.pr_numero == 42
    assert r.resume == "Une ligne : quoi, où, références."
    assert "## pas une section" in r.detail_md  # titres dans un bloc de code ignorés
    assert r.prochaine_etape_md == "Relire la PR."


def test_prochaine_etape_optionnelle():
    content = VALIDE.split("## Prochaine étape")[0]
    r = parse_report(raw(content))
    assert r.valid and r.prochaine_etape_md is None


def test_champs_manquants():
    r = parse_report(raw("---\ndate: 2026-11-16T09:15:00Z\nprojet: p\n---\n\n## Résumé court\nx\n"))
    assert not r.valid
    assert r.statut == "illisible"
    assert "repo" in r.error and "agent" in r.error and "statut" in r.error
    # la date de secours vient du nom de fichier
    assert r.date == datetime(2026, 11, 16, 10, 30, tzinfo=timezone.utc)


def test_yaml_casse():
    r = parse_report(raw('---\ndate: 2026-11-16\ncommit_message: "non fermé\nstatut: termine\n---\n'))
    assert not r.valid
    assert r.error.startswith("YAML invalide")


def test_sans_entete():
    r = parse_report(raw("## Résumé court\nrien\n"))
    assert not r.valid and "en-tête YAML absent" in r.error


def test_entete_non_ferme():
    r = parse_report(raw("---\ndate: 2026-11-16T10:00:00Z\n"))
    assert not r.valid and "non fermé" in r.error


def test_statut_inconnu():
    r = parse_report(raw(VALIDE.replace("statut: termine", "statut: fini")))
    assert not r.valid and "statut inconnu" in r.error


def test_resume_manquant():
    r = parse_report(raw(VALIDE.replace("## Résumé court", "## Autre")))
    assert not r.valid and "Résumé court" in r.error


def test_date_invalide():
    r = parse_report(raw(VALIDE.replace("2026-11-16T10:30:00Z", "demain")))
    assert not r.valid and "date invalide" in r.error


def test_titres_sans_accents_acceptes():
    r = parse_report(raw(VALIDE.replace("Résumé court", "Resume court").replace("Détail", "Detail")))
    assert r.valid and r.detail_md


def test_jamais_d_exception():
    for content in ["", "---", "---\n---\n", "---\n- liste\n---\n", "\x00\xff", "---\n[\n---\n"]:
        r = parse_report(raw(content))
        assert not r.valid and r.error


def test_dedoublonnage_par_nom_de_fichier():
    a = raw(VALIDE, "2026-11-16-103000-a.md", ref="main")
    a_pr = raw(VALIDE, "2026-11-16-103000-a.md", ref="feat/x")
    b_pr = raw(VALIDE, "2026-11-16-110000-b.md", ref="feat/x")
    other_repo = RawReport("o/autre", ".scope/rapports/2026-11-16-103000-a.md", "main", VALIDE)
    out = dedupe([a, a_pr, b_pr, other_repo])
    assert [(r.repo, r.filename, r.ref) for r in out] == [
        ("o/mon-projet-front", "2026-11-16-103000-a.md", "main"),
        ("o/mon-projet-front", "2026-11-16-110000-b.md", "feat/x"),
        ("o/autre", "2026-11-16-103000-a.md", "main"),
    ]
