# SCOPE

[English](README.md) · **Français**

**Supervision, Coordination & Observation Platform Engine**

SCOPE affiche, projet par projet, ce que les assistants de code IA (Claude Code, Cursor, GitHub Copilot, Codex…) ont fait sur vos dépôts GitHub.

À la fin de chaque prompt, l'assistant dépose un court rapport Markdown dans `.scope/rapports/` du dépôt. SCOPE lit ces rapports avec **un token en lecture seule** et publie une page par projet :
- **en tête de page**, un bandeau : pull requests ouvertes, commits à déployer, statut du dernier prompt et santé de l'application ;
- **le fil des rapports** : ce qui a été fait, avec quel commit et quelle pull request, et ce qu'il reste à faire ;
- **pour chaque dépôt** : pull requests ouvertes, dernier commit, version déployée et version réellement en production.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/scope-dark.png">
  <img alt="Page d'un projet dans SCOPE : bandeau (PR ouvertes, commits à déployer, dernier prompt, santé), panneau des dépôts et fil des rapports" src="docs/images/scope-light.png">
</picture>

## Principes

- **Simple.** Un nom de projet et un token suffisent pour ajouter un projet.
- **Lecture seule.** Le token de SCOPE ne fait que lire les dépôts du projet.
- **Léger.** Pas de base de données, pas de serveur applicatif, pas d'IA dans SCOPE : un générateur produit un site statique, servi par nginx.
- **Universel.** Fonctionne avec tout assistant capable de suivre une consigne écrite : le contrat est un fichier Markdown.
- **Vérifiable.** SCOPE ne se fie pas aux références écrites par l'IA : il retrouve lui-même le commit et la pull request via l'API GitHub.

## Votre copie, vos données

**Ce dépôt ne contient que le code.** SCOPE n'envoie et ne stocke rien ici : vos projets (`projects/*.yml`), vos tokens et la page générée restent dans **votre** copie.

| Mode | Copie à utiliser | Où vivent vos données |
| --- | --- | --- |
| **Local** (Docker Compose) | un simple `git clone` de ce dépôt | sur votre machine : `projects/*.yml` et `.env` sont ignorés par git, rien n'est poussé |
| **Kubernetes** (GitHub Actions) | **votre propre dépôt privé** : bouton **Use this template**, puis *Private* | dans votre dépôt privé : fichiers projet, secrets Actions, branche `scope-site` |

> **Ne forkez pas ce dépôt pour le mode Kubernetes.** Le fork d'un dépôt public est public : la branche `scope-site` publierait vos rapports, les titres de vos PR et les noms de vos dépôts. Utilisez **Use this template** (ou un clone poussé vers un nouveau dépôt privé).

Pour récupérer les nouvelles versions : `git pull` en mode local. Pour une copie créée depuis le template, ajoutez ce dépôt comme remote `upstream` et fusionnez `upstream/main`.

## Démarrage rapide (Docker Compose)

Prérequis : Docker avec Compose, `python3` (≥ 3.12) et [`gh`](https://cli.github.com/) connecté (`gh auth login`).

```bash
git clone https://github.com/thomdlnn/scope-2.0.git scope && cd scope
./scope.sh init boutique --env     # 1 token en lecture, choix des dépôts, consigne IA déposée
./scope.sh up                      # http://localhost:8080
```

`init` :
1. **demande un token** GitHub en lecture, sans l'afficher ([voir ci-dessous](#le-token)) ;
2. **liste les dépôts** que ce token peut lire, puis vous choisissez ceux du projet ;
3. **écrit le token** dans `.env` (jamais commité) et le projet dans `projects/boutique.yml` ;
4. **dépose la consigne SCOPE** dans `CLAUDE.md` et `AGENTS.md` de chaque dépôt, par une pull request ouverte avec *vos* droits `gh`, jamais avec le token.

Mergez ces pull requests. Les rapports apparaissent ensuite au fil des prompts.

Le générateur tourne dans un conteneur et régénère la page toutes les 15 minutes. nginx la sert sur `127.0.0.1:8080`.

| Commande | Rôle |
| --- | --- |
| `./scope.sh init <projet>` | Ajoute ou met à jour un projet (`--env` : mode Docker Compose) |
| `./scope.sh consigne <projet>` | Redépose ou met à jour la consigne IA dans les dépôts d'un projet |
| `./scope.sh up` / `down` / `logs` | Démarre, arrête ou suit SCOPE en local |
| `./scope.sh refresh` | Régénère la page tout de suite |
| `./scope.sh apercu` | Génère la page une fois, sans Docker, et la sert sur http://localhost:8000 |
| `./scope.sh cluster` | Installe SCOPE sur un cluster Kubernetes avec ArgoCD |

Options utiles de `init` :

| Option | Effet |
| --- | --- |
| `--env [FICHIER]` | Mode Docker Compose : token écrit dans `.env` (par défaut) au lieu d'un secret GitHub |
| `--titre "Boutique"` | Titre affiché du projet |
| `--repos o/a,o/b` | Dépôts imposés, sans liste à choisir |
| `--token-dedie` | Token propre à ce projet (voir ci-dessous) |
| `--clones ~/src` | Écrit la consigne directement dans vos clones locaux (`~/src/<dépôt>`), sans ouvrir de PR |
| `--dry-run` | N'envoie rien : ni secret, ni push, ni PR |

### Le token

Créez un [token *fine-grained*](https://github.com/settings/personal-access-tokens/new) :
- **Repository access :** *Only select repositories*, en choisissant les dépôts du projet. Ajoutez le dépôt GitOps si vous affichez la version déployée ;
- **Permissions :** **Contents : Read-only** et **Pull requests : Read-only** (Metadata : Read-only est ajoutée d'office) ;
- **Expiration :** une date d'expiration.

**Un token pour tout, ou un token par projet.** Le premier token devient le token global, `SCOPE_GH_TOKEN`, qui doit alors lire les dépôts de tous les projets. Pour cloisonner, `--token-dedie` enregistre un token propre au projet, `SCOPE_TOKEN_<PROJET>`. Si un token global existe déjà, `init` vous propose ce choix.

### Rafraîchissement

La page est régénérée **toutes les 15 minutes** (`SCOPE_INTERVAL` dans `.env`). Pour aller plus vite :
- le bouton **Actualiser**, en haut de chaque page, recharge la page courante avec les dernières données générées, en conservant vos filtres ;
- `./scope.sh refresh` force une nouvelle génération sans attendre.

L'en-tête indique depuis combien de temps la page a été mise à jour. Au-delà de 30 minutes, l'indication passe en orange : la génération est probablement en échec, par exemple à cause d'un token expiré.

## Le rapport

À la fin de chaque prompt qui modifie le code, l'assistant crée `.scope/rapports/AAAA-MM-JJ-HHMMSS-<slug>.md` et le commite avec son travail. La consigne complète est dans [templates/instructions-ia.md](templates/instructions-ia.md).

```markdown
---
date: 2026-11-16T10:30:00Z
projet: boutique
repo: boutique-front
agent: claude-code
branche: feat/login
commit_message: "feat(front): ajout de la page de login"
pr_titre: "Ajout de la page de login"
statut: pr-ouverte     # termine | pr-ouverte | bloque | echec
---

## Résumé court
Page de login ajoutée au frontend, PR ouverte.

## Détail
Fichiers modifiés, choix techniques, tests lancés, reste à faire.

## Prochaine étape
(optionnel) Ce que vous devez faire ensuite : PR à relire, choix à faire, prompt suggéré.
```

| Champ | Obligatoire | Description |
| --- | --- | --- |
| `date`, `projet`, `repo`, `agent`, `statut` | oui | Date ISO 8601, projet SCOPE, dépôt, assistant, état du travail |
| `branche`, `commit_message`, `pr_titre`, `pr_numero` | non | Affichage et valeurs de secours |
| `## Résumé court` | oui | Ligne affichée dans le fil |
| `## Détail`, `## Prochaine étape` | non | Détail dépliable et encadré mis en évidence |

- **Commit et PR :** SCOPE retrouve le commit qui a ajouté le rapport, puis la pull request qui le contient.
- **Branches lues :** la branche par défaut et celles des pull requests ouvertes, sans doublon.
- **Rapport mal formé :** il est signalé comme « illisible » et n'interrompt jamais la génération.

## Options d'un projet

`projects/<projet>.yml` est écrit par `./scope.sh init`, qui conserve les options ajoutées à la main :

```yaml
name: boutique
title: Boutique
token: SCOPE_TOKEN_BOUTIQUE            # optionnel : token dédié (sinon SCOPE_GH_TOKEN)
repos:
  - <owner>/boutique-front
  - <owner>/boutique-deploy
sante: http://boutique.local/health    # optionnel : santé de l'application
deploiements:                          # optionnel : version déployée (GitOps)
  <owner>/boutique-front:
    depot: <owner>/boutique-deploy     # dépôt GitOps suivi par ArgoCD (le token doit le lire)
    fichier: environments/prod/boutique-front.yaml
    cle: image.tag                     # défaut : image.tag (SHA du commit construit)
    environnement: prod                # défaut : local
```

**Version déployée.** SCOPE lit la version *déclarée* dans le dépôt GitOps et compte les commits de la branche par défaut qui ne sont pas encore déployés. Il n'interroge pas le cluster.

**Santé.** Le navigateur appelle l'URL de `sante` toutes les 60 secondes. Il comprend une réponse JSON de la forme suivante :
- `status` : `ok`, `degraded`… ;
- `services` (optionnel) : état de chaque composant, affiché en info-bulle ;
- `versions` (optionnel) : version réellement en production par dépôt, affichée dans le panneau des dépôts.

```json
{"status": "ok", "services": {"boutique-api": "ok"}, "versions": {"boutique-front": "5c60f6c…"}}
```

L'application doit autoriser la lecture depuis la page SCOPE (en-tête `Access-Control-Allow-Origin`). Sans ça, l'état s'affiche « injoignable ».

## Déploiement sur Kubernetes (GitHub Actions + ArgoCD)

Dans ce mode, une GitHub Action génère la page et la publie sur la branche `scope-site` du dépôt SCOPE. Un pod nginx, avec un sidecar git-sync, la sert depuis votre cluster.

```
Dépôts du projet                    Dépôt SCOPE (GitHub Actions)               Cluster Kubernetes
.scope/rapports/*.md  ──lecture──▶  build-site (15 min · refresh · push)       pod scope
PR, commits, GitOps     (token)       python -m scope_gen                        git-sync ◀── scope-site (60 s)
                                             │                                     nginx ──▶ Ingress ──▶ navigateur
                                             ▼
                                    branche scope-site (HTML + data.json)
```

1. **Créez votre dépôt privé** depuis ce dépôt : **Use this template**, puis *Private* (voir [Votre copie, vos données](#votre-copie-vos-données)). La suite se passe dans ce dépôt privé.
2. **Adaptez les paramètres de votre instance :**
   - l'URL de votre dépôt privé (`OWNER/REPO`), le nom d'hôte et l'ingress class, dans le bloc `patches` de [deploy/k8s/kustomization.yaml](deploy/k8s/kustomization.yaml) ;
   - l'URL du dépôt et la branche, dans [deploy/argocd/application.yaml](deploy/argocd/application.yaml) ;
   - la branche par défaut (`main`), dans [.github/workflows/build-site.yml](.github/workflows/build-site.yml).
3. **Activez le workflow `build-site`** avec la variable de dépôt `SCOPE_MODE=actions` : `gh variable set SCOPE_MODE --body actions`.
4. **Ajoutez vos projets** sans `--env` : `./scope.sh init boutique`. Le token est enregistré en secret GitHub du dépôt, et `projects/boutique.yml` est proposé par pull request.
5. **Installez la page sur le cluster :**
   ```bash
   ./scope.sh cluster
   echo "127.0.0.1 scope.local" | sudo tee -a /etc/hosts    # si le nom n'est pas résolu
   ```
   Cette commande :
   - demande un token en lecture seule sur le dépôt SCOPE ;
   - crée les Secrets de git-sync (`scope/scope-git-credentials`) et d'ArgoCD (`argocd/repo-scope`) ;
   - applique l'Application ArgoCD, puis attend que le pod soit prêt.

| Secret | Emplacement | Usage |
| --- | --- | --- |
| `SCOPE_GH_TOKEN`, `SCOPE_TOKEN_<PROJET>` | Secrets Actions du dépôt SCOPE | Lecture des dépôts suivis |
| `scope-git-credentials` | Secret Kubernetes, namespace `scope` | git-sync lit la branche `scope-site` |
| `repo-scope` | Secret Kubernetes, namespace `argocd` | ArgoCD lit `deploy/k8s` |

Remarques :
- Le dépôt SCOPE lui-même peut être suivi sans token, avec `token: GITHUB_TOKEN` dans son fichier projet : c'est le token intégré de l'Action.
- Votre ingress controller doit surveiller le namespace `scope`. Par exemple, Traefik avec `providers.kubernetesIngress.namespaces` doit inclure `scope`.
- L'Action transmet les secrets du dépôt au générateur (`SCOPE_SECRETS`), pour lui permettre de lire les tokens dédiés. N'y stockez donc que des tokens SCOPE.

Pour le diagnostic : `kubectl -n scope get pods`, puis `kubectl -n scope logs deploy/scope -c git-sync`.

## Développement

```bash
python3 -m venv generator/.venv && generator/.venv/bin/pip install -r generator/requirements-dev.txt
(cd generator && .venv/bin/python -m pytest -q)        # tests
scripts/verifier-site.sh                              # navigateur headless (Docker), captures dans out/captures/
kubectl kustomize deploy/k8s                          # manifests

# Page générée depuis des clones locaux, sans token (DOSSIER/<dépôt>)
PYTHONPATH=generator generator/.venv/bin/python -m scope_gen --local ~/src --out site
```

```
scope.sh                  point d'entrée (init, consigne, up, refresh, apercu, cluster)
docker-compose.yml        mode local : générateur + nginx
Dockerfile, docker/       image du générateur (boucle de régénération)
projects/                 un fichier par projet suivi
templates/                consigne IA
generator/scope_gen/
  admin.py                ./scope.sh init | consigne | refresh
  parser.py               rapport → données (ne lève jamais d'exception)
  backends/               accès aux dépôts : API GitHub, clones locaux
  sources/                données collectées : rapports, état des dépôts
  render.py, templates/, static/   HTML, CSS et JavaScript écrits à la main
.github/workflows/        ci (tests, image, navigateur), build-site (mode Kubernetes)
deploy/                   kustomize (nginx + git-sync) et Application ArgoCD
scripts/                  installer-cluster.sh, verifier-site.sh
docs/                     cahier des besoins
```

**Ajouter une source de données :** créez une classe `Source` dans `generator/scope_gen/sources/` (avec `name` et `collect(project, backend)`). Ajoutez-la à `SOURCES`, puis affichez son résultat dans `render.py`. Il est exporté dans `data.json` sous la clé `name`.

## Feuille de route

- Vue « action requise » tous projets confondus.
- Signalement des commits sans rapport, et hook pour assistants qui impose le rapport.
- Statut des pull requests : CI, revue, conflits.
- Plusieurs environnements par dépôt.
- Consommation de tokens, roadmap par projet, notifications.

Le détail est dans le [cahier des besoins](docs/cahier-des-besoins.md).

## Contribuer

Les issues et les pull requests sont bienvenues. Toute modification de `main` passe par une pull request, et la CI (tests, image Docker, vérification navigateur) doit passer.

## Licence

[MIT](LICENSE)
