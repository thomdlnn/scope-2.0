# SCOPE — instructions pour les agents IA

Dépôt du générateur SCOPE (Python 3.12, site statique). Voir README.md et docs/cahier-des-besoins.md.

<!-- scope:start -->
## SCOPE — rapport obligatoire après chaque action

Ce dépôt est suivi par SCOPE (projet `scope`). Après **chaque** action qui modifie le code, tu DOIS :

1. Créer un fichier `.scope/rapports/AAAA-MM-JJ-HHMMSS-<slug>.md` (date et heure UTC, slug court en kebab-case).
2. Le commiter **dans le même commit** que le travail (n'y mets pas le hash du commit : SCOPE le retrouve).
3. Renseigner `commit_message` avec le message de ce commit, et `pr_titre` avec le titre de la PR (ouverte ou à ouvrir).
4. Ne JAMAIS y écrire de secret, token, mot de passe ou donnée personnelle.

Format exact (en-tête YAML puis sections) :

```markdown
---
date: 2026-11-16T10:30:00Z
projet: scope
repo: nom-du-repo
agent: claude-code          # claude-code | cursor | copilot | codex | autre
branche: feat/login
commit_message: "feat(front): ajout de la page de login"
pr_titre: "Ajout de la page de login"
pr_numero: 42               # optionnel, si déjà connu
statut: termine             # termine | pr-ouverte | bloque | echec
---

## Résumé court
Une ligne : quoi, où, références.

## Détail
Fichiers modifiés, choix techniques, tests lancés, reste à faire.

## Prochaine étape
(optionnel) Ce que l'humain doit faire ensuite : PR à relire, choix à faire, prompt suggéré.
```

Utilise `bloque` si tu attends une décision humaine, `echec` si le travail n'a pas abouti. Un rapport par action, jamais de modification d'un rapport existant.
<!-- scope:end -->
