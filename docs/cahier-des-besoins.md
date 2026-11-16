# SCOPE — cahier des besoins

## Objectif

**SCOPE** — *Supervision, Coordination & Observation Platform Engine* : une vision globale sur les actions, les projets et les agents.

Après chaque prompt, SCOPE donne à la personne qui pilote l'IA un retour simple (réponse courte, détail en réponse longue), et ce qu'elle doit savoir pour écrire son prompt suivant.

- **Problème :** quand l'IA code à notre place, l'information est éparpillée entre le chat, GitHub, la CI et l'hébergement. On perd le fil.
- **Principe :** l'IA qui répond au prompt dépose un fichier de rapport à chaque réponse. Une GitHub Action récupère ces fichiers et génère une page web statique.
- **Léger :** le moins d'IA possible dans SCOPE, idéalement aucune. Toute l'intelligence est dans l'agent qui rédige le rapport ; SCOPE ne fait que lire, vérifier et afficher.
- **Universel :** fonctionne avec n'importe quel agent (Claude Code, Cursor, Copilot, Codex…), car il ne repose que sur un fichier Markdown et une consigne écrite.
- **Cible :** la personne qui écrit les prompts, sur un ou plusieurs dépôts.

## Fonctionnement

L'IA fait ce que demande le prompt, puis dépose un fichier de rapport dans le dossier `.scope/` du dépôt.

1. L'humain envoie un prompt (écrire, pousser, merger, déployer du code).
2. L'IA réalise le travail.
3. L'IA écrit `.scope/rapports/AAAA-MM-JJ-HHMMSS-<slug>.md` et le commite avec le reste.
4. Une GitHub Action récupère ces fichiers et régénère la page SCOPE.

Arborescence proposée :

```
# Dans chaque dépôt applicatif
.scope/
  rapports/
    2026-11-16-103000-ajout-login.md
    2026-11-16-141500-fix-api.md
  roadmap.md          # après le MVP

# Dans le dépôt scope
projects/
  boutique.yml        # nom du projet + liste de ses repos
  scope.yml           # SCOPE se suit lui-même
```

La consigne est un court texte copié dans le fichier d'instructions de chaque agent : `AGENTS.md`, `CLAUDE.md`, `.cursor/rules`, `.github/copilot-instructions.md`… C'est ce qui rend SCOPE universel. Quand l'agent le permet (hooks Claude Code par exemple), un hook peut en plus refuser de terminer une tâche sans rapport.

## Format du rapport

Chaque rapport a un en-tête structuré (lu par le backend sans IA), puis trois parties pour l'humain : réponse courte, réponse longue, et ce qu'il faut savoir pour le prochain prompt.

```markdown
---
id: 2026-11-16-1030-ajout-login
date: 2026-11-16T10:30:00Z
prompt: "Ajoute une page de login au frontend"
agent: claude-code          # cursor, copilot, codex...
model: claude-opus-5-5      # optionnel
repos: [boutique-front]
branch: feat/login
commits: [a1b2c3d]
pr: 42
status: pr-ouverte          # termine | pr-ouverte | bloque | echec
deploy: null
usage:                      # optionnel, si l'agent le connaît
  tokens_in: 48200
  tokens_out: 6100
  cost_usd: 0.92
  duration_s: 340
tags: [frontend, auth]
---

## Réponse courte
Page de login ajoutée au frontend — repo boutique-front, commit a1b2c3d, PR #42.

## Réponse longue
- Fichiers modifiés : ...
- Choix techniques : ...
- Tests lancés et résultats : ...

## Pour votre prochain prompt
- À faire par vous : relire et merger la PR #42 ; ajouter le secret AUTH_SECRET en staging
- Questions de l'IA : faut-il un lien « mot de passe oublié » ?
- Suite suggérée : « Ajoute la déconnexion et protège les routes /admin »
```

| Partie | Rôle |
| --- | --- |
| Réponse courte | Une ligne : quoi, où (repo), références (commit, PR) |
| Réponse longue | Le même contenu détaillé : fichiers, choix, tests |
| Pour votre prochain prompt | Ce que l'humain doit faire, les questions ouvertes, la suite logique : la base du prompt suivant |
| En-tête YAML | Permet au backend de filtrer, trier, relier aux PR et déploiements, et cumuler les tokens |
| `status` | Dit si l'humain doit agir (relire une PR, débloquer) |

> Note MVP : le prompt MVP fixe un format simplifié (champs `projet`, `repo`, `commit_message`, `pr_titre`, `statut`… et sections « Résumé court », « Détail », « Prochaine étape »). C'est ce format qui fait foi pour le MVP — voir `templates/instructions-ia.md`.

## Tableau de bord

Une page web unique répond à deux questions : qu'a fait l'IA, et que dois-je faire ensuite (nouveau prompt, PR à relire, choix à faire, mise en production).

La page d'accueil liste les projets (par exemple « Boutique », ou SCOPE lui-même). Chaque projet a sa propre page avec les vues ci-dessous, limitées à ses repos. Initialiser un projet demande trois choses : son nom, la liste de ses repos, et le bloc d'instructions IA à poser dans chacun.

| Vue | Contenu | Source | Priorité |
| --- | --- | --- | --- |
| Prochain prompt | Actions à faire, questions de l'IA, suite suggérée, issues du dernier rapport de chaque repo | `.scope/rapports/` | Haute |
| Fil d'activité | Retour de chaque prompt, du plus récent au plus ancien ; réponse courte, dépliable en longue | `.scope/rapports/` | Haute |
| Pull requests | PR ouvertes : à relire, prêtes à merger (CI verte, approuvée), en conflit | API GitHub | Haute |
| Mise en production | Par app et environnement : version déployée, version déployable (dernier tag ou `main`), nombre de commits d'écart → « MEP à faire » | API GitHub (Deployments, tags, compare) | Haute |
| Consommation | Tokens, coût et durée par prompt, par jour, par projet | Champ `usage` des rapports | Moyenne |
| Roadmap | Avancement de la checklist | `.scope/roadmap.md` | Moyenne |
| Santé | Statut OK / KO des apps déployées | `/health`, lu par le navigateur | Bonus |

Pas de suivi en temps réel : une page rafraîchie toutes les 15 minutes, et à chaque nouveau rapport, suffit.

## Roadmap

La roadmap est une checklist Markdown dans `.scope/roadmap.md`, que l'humain et l'IA modifient tous les deux.

```markdown
## Phase 1 — MVP
- [x] Page de login (#42, prompt 2026-11-16-1030)
- [ ] Endpoint /health sur l'API
- [ ] Déploiement auto en staging
```

- L'IA coche une case quand un prompt la termine, et met le lien vers le rapport et la PR.
- SCOPE calcule l'avancement par phase et montre les tâches sans activité récente.

## Est-ce léger ?

Oui : SCOPE n'a ni serveur applicatif, ni base de données, ni IA. Une GitHub Action génère une page statique, et un simple serveur web la sert.

| Pièce | Rôle | IA ? |
| --- | --- | --- |
| Consigne dans l'agent | Fait écrire le rapport à chaque réponse | Celle de l'agent déjà utilisé, rien à ajouter |
| GitHub Action | Toutes les 15 min et à chaque rapport : lit les repos via l'API GitHub, génère la page | Non |
| Stockage | Les fichiers dans Git, rien d'autre | Non |
| Page web | HTML statique servi par nginx (Kubernetes local) ou GitHub Pages | Non |

- **Ce qui pourrait alourdir :** l'historique long terme, l'authentification multi-utilisateurs, les notifications. À garder pour plus tard.
- **Le seul coût caché :** l'agent consomme un peu plus de tokens par réponse pour rédiger le rapport.

## Avis

L'idée est bonne et répond à un vrai manque : les outils actuels suivent le code, pas l'intention (le prompt) qui l'a produit.

**Points forts**

- Les rapports vivent dans le dépôt : versionnés, sans base de données, indépendants de l'outil d'IA utilisé.
- Le lien prompt → commit → PR → déploiement → santé n'existe nulle part aujourd'hui.
- Format Markdown : lisible même sans SCOPE, directement sur GitHub.

**Points d'attention**

- **Fiabilité :** l'IA peut oublier le rapport ou se tromper sur un hash de commit. Il faut un hook qui l'oblige à l'écrire, et SCOPE doit vérifier les références auprès de GitHub plutôt que leur faire confiance.
- **Bruit dans l'historique :** un fichier par prompt pollue les commits et les PR. Option : une branche dédiée `scope`, ou des rapports envoyés directement à l'API de SCOPE.
- **Conflits de merge :** plusieurs agents en parallèle écrivent dans `roadmap.md`. Les noms de fichiers horodatés évitent le problème pour les prompts, pas pour la roadmap.
- **Prompts sensibles :** un prompt peut contenir un secret ou une donnée client. Prévoir un masquage avant commit.
- **Projets multi-dépôts :** un prompt peut toucher 3 repos. Il faut décider où vit le rapport (un dépôt « projet » central ?).

## Fonctionnalités supplémentaires proposées

Toutes restent sans IA côté SCOPE : elles lisent les rapports et les API, rien de plus. Les plus utiles d'abord.

| Fonctionnalité | Ce que ça apporte | Priorité |
| --- | --- | --- |
| Prochain prompt | En haut de page : ce que l'humain doit faire, les questions de l'IA, la suite suggérée | Haute |
| « Action requise » | Liste de ce qui attend l'humain sur tous les projets : PR à relire, agent bloqué, question posée | Haute |
| Consommation | Tokens, coût et durée par prompt, cumulés par jour, projet et agent | Haute |
| Contrôle des rapports | Le backend vérifie le format et les références (commit, PR existent ?) et signale un commit sans rapport | Haute |
| Lien santé ↔ prompt | Quand une app passe KO, afficher les derniers prompts déployés dessus | Moyenne |
| Notifications | Alerte (mail, Slack, mobile) quand une app passe KO ou qu'une action est requise | Moyenne |
| Résumé du jour / de la semaine | Simple liste des réponses courtes de la période, sans réécriture par IA | Moyenne |
| Fichiers et doc modifiés | Fichiers touchés par prompt, et alerte si le code change sans que la doc suive | Basse |
| Recherche | Retrouver « quel prompt a modifié ce fichier ? » | Basse |
| Comparaison d'agents | Tokens, coût et taux d'échec par agent ou modèle | Basse |

## Architecture

Recommandation : une GitHub Action génère la page, et votre Kubernetes local la sert. Pas de serveur applicatif à coder ni à maintenir.

**Les pièces**

1. **Un dépôt `scope` central :** `config.yml` (liste des repos, apps, environnements), le script générateur, le workflow.
2. **Le workflow GitHub Actions** se déclenche toutes les 15 minutes (`schedule`), à la demande (`workflow_dispatch`), et quand un repo pousse un rapport (`repository_dispatch`, 5 lignes à ajouter dans chaque repo).
3. **Le script** (Python ou Node, quelques centaines de lignes) lit via l'API GitHub les rapports `.scope/`, les PR ouvertes, les déploiements et les tags. Il produit un `index.html` + un `data.json`, poussés sur une branche `scope-site`.
4. **L'hébergement**, sur votre Kubernetes local : un pod nginx avec un sidecar `git-sync` qui tire la branche `scope-site`. Le tout est déployé par ArgoCD, comme vos autres apps. La page reste sur votre réseau, donc vos prompts restent privés.

**Comment SCOPE sait qu'une MEP est à faire**

- *Version déployée :* ArgoCD connaît le commit synchronisé de chaque Application. Après le MVP, un petit CronJob dans le cluster le publiera pour SCOPE, puisque les runners GitHub ne voient pas le cluster.
- *Version déployable :* le dernier tag ou release, ou la tête de `main`.
- *Écart :* l'API GitHub `compare` donne le nombre de commits entre les deux. Plus de 0 = « MEP à faire », avec la liste des rapports concernés.

**Points d'attention**

- Les runners GitHub ne voient pas votre réseau local : ils ne peuvent pas interroger vos apps. D'où la déclaration du déploiement côté pipeline.
- GitHub Pages est plus simple que Kubernetes, mais la page y serait publique (sauf offre Enterprise), avec vos prompts dedans.
- Bonus santé : la page, ouverte depuis votre réseau, peut appeler directement les `/health` depuis le navigateur. Il faut juste autoriser CORS sur ces endpoints.
- Alternative 100 % locale : le même script en `CronJob` Kubernetes, sans GitHub Actions. Utile si vos repos ne sont pas sur GitHub.

## Estimation

Tout le périmètre (santé incluse) représente environ 8 à 9 jours pour un développeur seul, ou 2 à 3 jours en le faisant coder par un agent IA, relecture comprise. Ce sont des ordres de grandeur, à ajuster selon le nombre de repos et vos façons de déployer.

| Lot | Contenu | Développeur seul | Avec un agent IA |
| --- | --- | --- | --- |
| 1. Convention | Modèle de rapport, consigne pour les agents, exemple | 0,5 j | 1 h |
| 2. Script générateur | Config, lecture des rapports, PR, calcul des écarts de version | 3 j | 0,5 j |
| 3. Page web | Les vues du tableau de bord, filtre par projet | 2 j | 0,5 j |
| 4. Workflow GitHub Actions | Planification + déclenchement depuis les repos | 0,5 j | 1 h |
| 5. Hébergement Kubernetes | nginx + git-sync, manifests | 0,5 j | 1 h |
| 6. Déclaration des déploiements | Une étape dans chaque type de pipeline | 0,5 j | 1 h |
| 7. Bonus santé | Appels `/health` depuis la page, CORS | 0,5 j | 1 h |
| 8. Tests et réglages | Essais sur les vrais repos, corrections | 1 j | 0,5 j |

Ordre conseillé : lot 1 tout de suite (utile sans rien d'autre), puis 2 + 3 + 4 + 5 pour un premier MVP « rapports + PR », puis 6 pour la vue Mise en production, et 7 en dernier.

## Questions ouvertes

- [ ] Usage personnel seulement, ou outil partagé / produit pour d'autres équipes ?
- [ ] Quels agents tester en premier avec la convention (Claude Code, Cursor, Copilot, Codex…) ?
- [ ] Rapports commités dans chaque repo, ou centralisés dans un dépôt « projet » ?
- [ ] Déploiement par ArgoCD (décidé) : après le MVP, choisir comment exposer à SCOPE la version synchronisée de chaque app.
- [ ] Version déployable = dernier tag / release, ou tête de `main` ?
- [ ] Langage du script générateur (Python ou Node) ?
