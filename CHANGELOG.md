# Changelog

## 1.1.0 — 2026-11-19

Token GitHub optionnel. Sans token, tout fonctionne comme en 1.0.0.

### Ajouté
- `SCOPE_GH_TOKEN` (un seul token, lecture seule, dans `.env`) : panneau **Dépôts** par projet, avec toutes les PR ouvertes (auteur, brouillons) et le dernier commit de la branche par défaut. Dépôts déduits du remote `origin` des clones, sans liste à écrire ; identifiants éventuels de l'URL jamais affichés.
- API GitHub lue en tâche de fond toutes les `SCOPE_GH_INTERVAL` secondes (défaut 60) : la lecture locale reste à 3 s.
- `projects/<projet>.yml` devient optionnel et ne sert qu'à `deploiements` (version déclarée dans le dépôt GitOps, commits à déployer) et `sante`. Un fichier invalide est signalé sur l'accueil sans casser la page.
- Accueil **par projet** : le nombre d'actions en attente en tête (« Aucune action en attente », « 2 actions en attente »), puis un bloc par projet (attentes, en cours, 7 derniers jours repliés), les projets qui attendent quelque chose en premier. Nouvelle accroche : « La supervision de vos agents IA ».
- Erreurs de token affichées clairement : dépôt introuvable (404), PR non lues (403), token refusé (401).

### Corrigé
- Après une mise à jour de SCOPE, le site est régénéré même si aucun rapport n'a changé, et une page ouverte se recharge seule (nouveaux CSS et JS).

### Retiré
- Fichiers `projects/*.yml` d'exemple devenus inutiles.
- Lecture des rapports via l'API GitHub, résolution du commit et de la PR d'un rapport, parcours des branches, ancien parser et backend local.

## 1.0.0 — 2026-11-18

SCOPE devient un outil local, en direct, sans token.

### Ajouté
- Lecture des rapports **sur le disque** : le générateur parcourt `SCOPE_ROOT` (défaut `~/Git`, profondeur `SCOPE_DEPTH`) et lit `.scope/rapports/*.md` dans l'arbre de travail, fichiers non commités compris. Regroupement par projet : champ `projet`, sinon `.scope/projet`, sinon nom du dossier.
- Nouveau format de rapport : **un fichier par demande**, mis à jour jusqu'à la fin (`demande`, `statut: en-cours | attente | termine | echec`, `actions`, `debut`, `maj`, sections Résumé, Pour vous, Détail). Parser **bilingue** (clés et titres en français et en anglais) ; l'ancien format reste lu.
- Accueil : **En attente de vous** tous projets confondus, **En cours** (signalées sans nouvelles après 1 h), **7 derniers jours**, projets. Page projet : mêmes blocs, filtres par dépôt et statut, actions en badges, demandes plus anciennes repliées.
- **Mise à jour en direct** : régénération toutes les 3 s (`SCOPE_INTERVAL`) par sondage, bascule atomique seulement si l'affichage change ; la page relit `etat.json` et se met à jour seule en gardant filtres et sections dépliées.
- **Docker Compose** (générateur + nginx sur `127.0.0.1:8080`, `SCOPE_ROOT` en lecture seule) : `./scope.sh up | down | logs` ; `./scope.sh apercu` sans Docker.
- `./scope.sh init <projet> <clone>... [--lang en|fr]` : consigne dans `CLAUDE.md` et `AGENTS.md`, `.scope/` exclu de git, sans token, sans `gh`, sans commit.
- **Hook Claude Code** (`UserPromptSubmit` + `Stop`) : rappel unique quand un tour modifie le dépôt sans mettre à jour de rapport.
- Consigne en anglais et en français ; README en anglais et en français.
- CI : tests, vérification navigateur (Playwright), shellcheck, image Docker.

### Retiré
- Déploiement Kubernetes (`deploy/`, `scripts/installer-cluster.sh`, `./scope.sh cluster`, git-sync, ArgoCD), `./scope.sh refresh` et `./scope.sh consigne`.
- Les rapports ne sont plus commités : `.scope/` est exclu de git.
