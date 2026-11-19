<!-- scope:start -->
## SCOPE — un rapport tenu à jour pour chaque demande

Ce dépôt est suivi par SCOPE (projet `{{PROJET}}`). L'humain suit ton travail en direct par ces rapports : ce qui n'y est pas, il ne le voit pas.

**Quand.** Dès qu'une demande implique une action (code, commit, push, PR, déploiement, action hors du dépôt) ou une question à l'humain, crée son rapport **avant de commencer**, avec `statut: en-cours`. Une réponse purement informative n'en demande pas.

**Un fichier par demande** : `.scope/rapports/AAAA-MM-JJ-HHMMSS-<slug>.md` (heure UTC, slug court en kebab-case). **Mets à jour ce même fichier** à chaque étape : `statut`, `actions`, `maj`, les sections. Quand l'humain te répond, continue dans le même fichier. Nouvelle demande = nouveau fichier.

**Ne commite et ne pousse jamais le rapport** (`.scope/` est exclu de git). N'y écris jamais de secret, token, mot de passe ni donnée personnelle.

**Attente de l'humain.** Si tu poses une question ou attends une décision, un accès, une valeur ou une action manuelle : écris-la en `- Question : …` sous `## Pour vous`, passe `statut: attente`, puis rends la main. `attente` ⇔ au moins une question. Une information utile à l'humain (URL à déclarer, limite, risque) est une `- Remarque : …` et ne met pas en attente.

```markdown
---
projet: {{PROJET}}
repo: <nom du dépôt>
agent: claude-code        # claude-code | cursor | copilot | codex | autre
branche: feat/login-google
demande: "Page de login avec authentification Google"
statut: attente           # en-cours | attente | termine | echec
actions: [code, commit]   # code | commit | push | pr | deploy | hors-depot
debut: 2026-11-17T10:30:00Z
maj: 2026-11-17T10:42:00Z
pr: 42                    # optionnel
---

## Résumé
Une ligne : où en est la demande.

## Pour vous
- Question : quel Client ID Google dois-je utiliser ?
- Remarque : déclarez http://localhost:3000/auth/callback dans la console Google.

## Détail
Fichiers modifiés, choix techniques, tests lancés.
```

Avant de rendre la main, vérifie que le rapport correspond à ce que tu as fait : `statut` et `actions` (seulement ce qui a vraiment été fait), `maj`, et que chaque question ouverte y figure.
<!-- scope:end -->
