# SCOPE

**Supervision, Coordination & Observation Platform Engine** · [Français](README.fr.md)

SCOPE keeps you on top of everything you have asked your AI coding agents (Claude Code, Cursor, Copilot, Codex…) **while you work**. For each request, one page shows:

- **what you asked**;
- **what the agent did**: code, commit, push, PR, deployment, depending on what you allowed it to do;
- above all, **what the agent is waiting for from you**: a question, a decision, or a note you should know about.

> *"Create a login page with Google."* SCOPE shows that the agent is waiting for an answer (*"Which Client ID?"*) and adds a note (*"Google requires the callback URL http://localhost:3000/auth/callback"*).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/accueil-sombre.png">
  <img alt="SCOPE home page: waiting actions, then one block per project" src="docs/img/accueil.png">
</picture>

## Quick start

Requirements: `git`, plus Docker with Compose, or Python ≥ 3.12 without Docker.

```bash
git clone https://github.com/thomdlnn/scope-2.0.git scope && cd scope
./scope.sh init my-project ~/Git/my-app ~/Git/my-api    # once per repository
./scope.sh up                                          # http://localhost:8080
```

Then ask your agent something in `my-app`. The request shows up within 3 seconds, without reloading the page.

`init` writes nothing to GitHub and commits nothing. In each clone, it:
1. adds the SCOPE instructions to `CLAUDE.md` and `AGENTS.md`, between `<!-- scope:start -->` and `<!-- scope:end -->` (run it again to update them). You decide whether to commit these files;
2. adds `.scope/` to `.git/info/exclude`, because reports are never committed;
3. writes the project name to `.scope/projet`;
4. installs a Claude Code hook in `.claude/settings.local.json` (see [the hook](#the-claude-code-hook)).

Use `--lang fr` for French instructions (default: `en`).

| Command | Purpose |
| --- | --- |
| `./scope.sh init <project> <clone>... [--lang en\|fr]` | Install or update SCOPE in local clones |
| `./scope.sh up` / `down` / `logs` | Start, stop, follow SCOPE (Docker Compose) |
| `./scope.sh apercu` | Same page without Docker (Python only), on http://localhost:8000 |

| Setting (environment or `.env`) | Default | Purpose |
| --- | --- | --- |
| `SCOPE_ROOT` | `~/Git` | Folder searched for repositories, mounted **read-only** |
| `SCOPE_DEPTH` | `4` | How many folder levels below `SCOPE_ROOT` are searched |
| `SCOPE_INTERVAL` | `3` | Seconds between two readings of the reports |
| `SCOPE_PORT` | `8080` | Local port of the page (bound to 127.0.0.1) |
| `SCOPE_GH_TOKEN` | — | Optional read-only GitHub token ([see below](#optional-a-github-token)) |
| `SCOPE_GH_INTERVAL` | `60` | Seconds between two readings of the GitHub API |

## How it works

```
your clones (SCOPE_ROOT, read-only)        generator (every 3 s)                nginx
~/Git/.../my-app/.scope/rapports/*.md ──▶  reads reports, groups by project ──▶ http://localhost:8080
         ▲                                 writes a static site, switches it     │
         └── written by your agents        atomically only if something changed  ▼
                                                                      the page polls etat.json
                                                                      and refreshes itself
```

- **Reports are not committed.** They are for live tracking; commits are already the history. They live in `.scope/rapports/` of your local clone, excluded from git.
- **SCOPE reads reports from your disk, not from GitHub.** It only sees agents running on your machine. This is by design: reports need no token and no network.
- **No AI, no database, no application server.** A Python script writes a static site; nginx serves it.
- **Universal.** Any agent that can follow written instructions works: the contract is a Markdown file.
- **Live.** The page checks `etat.json` every few seconds and replaces its content when something changes, keeping your filters and expanded sections. The header says when the reports were last checked, and turns orange if generation seems to have stopped.

The **home page** first states how many **actions are waiting** for you ("Aucune action en attente", or "2 actions en attente: my-project (1), …"), then shows **one block per project**, the ones waiting for you first: pending questions (with the repository and the request), requests **in progress** (flagged when the agent has not updated them for an hour) and, collapsed, those of **the last 7 days**. A **project page** shows the same blocks, with filters by repository and status, expandable details and actions as badges.

## The report

One file **per request**, created when the work starts and **updated** until the end: `.scope/rapports/YYYY-MM-DD-HHMMSS-<slug>.md`. The full instructions given to agents are in [templates/instructions-ia.en.md](templates/instructions-ia.en.md).

```markdown
---
project: my-project
repo: my-app
agent: claude-code
branch: feat/login-google
request: "Login page with Google authentication"
status: waiting            # in-progress | waiting | done | failed
actions: [code, commit]    # code | commit | push | pr | deploy | outside-repo
started: 2026-11-17T10:30:00Z
updated: 2026-11-17T10:42:00Z
pr: 42                     # optional
---

## Summary
One line: where the request stands.

## For you
- Question: which Google Client ID should I use?
- Note: declare http://localhost:3000/auth/callback in the Google console.

## Details
Files changed, technical choices, tests run.
```

- `waiting` ⇔ at least one `Question:` under *For you*. A note alone does not put a request on hold. SCOPE shows a warning when the two disagree.
- When you answer, the agent keeps updating **the same file**. A new request means a new file.
- **English and French** keys and headings are both accepted: `project`/`projet`, `status`/`statut`, `request`/`demande`, `branch`/`branche`, `started`/`debut`, `updated`/`maj`; `Summary`/`Résumé`, `For you`/`Pour vous`, `Details`/`Détail`; `in-progress`/`en-cours`, `waiting`/`attente`, `done`/`termine`, `failed`/`echec`.
- **Project:** the `project` field, otherwise `.scope/projet`, otherwise the repository folder name.
- **Old format** (one report per answer) is still read: `bloque` = `waiting`, `pr-ouverte` = `done` with a PR, `Résumé court` = summary, `Prochaine étape` = *For you*. An old `bloque` report only counts as waiting while it is the most recent report of its repository.
- **A malformed report** is shown as "unreadable", with the reason, and never breaks the page.
- **Never** put a secret, token, password or personal data in a report.

### The Claude Code hook

Agents sometimes forget the report. For Claude Code, `init` installs two hooks in `.claude/settings.local.json` (not committed), backed by `.scope/hooks/scope_hook.py`:
- when you send a prompt (`UserPromptSubmit`), it records the state of the repository;
- when the agent finishes its turn (`Stop`), if repository files changed (or a commit was made) and no report was created or updated during the turn, it blocks **once** with a reminder. It uses `stop_hook_active`, so it never blocks twice in a row.

Other agents rely on the instructions in `AGENTS.md`.

## Optional: a GitHub token

Without a token, SCOPE makes no network call. With a **read-only** GitHub token, each project page also gets a **Repositories** panel:

- repositories are **deduced from the clones** (`git remote get-url origin`), with nothing to list. Credentials in a remote URL are never shown;
- for each repository: **all open pull requests** (by anyone, drafts flagged), and the last commit of the default branch;
- the home page shows the number of open PRs per project.

```bash
cp .env.example .env    # then set SCOPE_GH_TOKEN=…
./scope.sh up
```

Create a [fine-grained token](https://github.com/settings/personal-access-tokens/new) with access to your projects' repositories, **Contents: Read-only** and **Pull requests: Read-only**, and an expiration date. It is the only token SCOPE uses. GitHub is read in the background every `SCOPE_GH_INTERVAL` seconds (default 60), so local reports keep updating every 3 seconds even if GitHub is slow. Token errors are shown on the page: *repository not found with this token* (add the repository to the token), *PRs not read* (add the Pull requests permission), *token refused* (invalid or expired).

### Deployed version and app health (optional)

`projects/<project>.yml` (the file name is the project name) adds what cannot be deduced:

```yaml
deploiements:                                  # needs the token
  <owner>/my-app:                              # application repository
    depot: <owner>/my-app-deploy               # GitOps repository (e.g. followed by ArgoCD)
    fichier: environments/local/my-app.yaml
    cle: image.tag                             # default: image.tag (SHA of the built commit)
    environnement: local                       # default: local
sante: http://my-app.local/health              # called by the browser, works without a token
```

- **`deploiements`**: SCOPE reads the version declared in the GitOps repository and counts the commits of the default branch not deployed yet.
- **`sante`**: the browser calls this URL every 60 seconds and understands `{"status": "ok", "services": {…}, "versions": {"my-app": "<sha>"}}`. The application must allow CORS (`Access-Control-Allow-Origin`), otherwise it shows "unreachable".

An invalid file is reported on the home page and ignored; the rest of the page keeps working.

## Development

```bash
python3 -m venv generator/.venv && generator/.venv/bin/pip install -r generator/requirements-dev.txt
(cd generator && .venv/bin/python -m pytest -q)        # tests
scripts/verifier-site.sh                              # headless Chromium (Docker), screenshots in out/captures/
PYTHONPATH=generator generator/.venv/bin/python -m scope_gen --racine ~/Git --out site   # one-off generation
```

```
scope.sh                    entry point (init, up, down, logs, apercu)
docker-compose.yml          generator + nginx; Dockerfile, docker/nginx.conf
templates/                  agent instructions (en, fr) and the Claude Code hook
generator/scope_gen/
  demandes.py               report → request (bilingual parser, never raises)
  locale.py                 finds repositories on disk, groups by project
  render.py, templates/, static/   hand-written HTML, CSS and JavaScript
  cli.py                    one-off generation, loop with atomic switch, preview server
  admin.py                  ./scope.sh init
  sources/depots.py, backends/   repository state from the GitHub API (optional token)
  config.py                 optional projects/*.yml settings
```

## Out of scope

Roadmap tracking, token usage, notifications, Kubernetes, GitHub Actions.

## Contributing

Issues and pull requests are welcome. Every change to `main` goes through a pull request, and CI (tests, browser check, shellcheck, Docker image) must pass.

## License

[MIT](LICENSE)
