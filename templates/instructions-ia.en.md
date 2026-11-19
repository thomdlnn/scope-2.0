<!-- scope:start -->
## SCOPE — keep a live report for each request

This repository is followed by SCOPE (project `{{PROJET}}`). The human follows your work through these reports, live, while you work. What is not in the report, they do not see.

**When.** As soon as a request involves an action (code, commit, push, PR, deployment, anything outside the repo) or a question for the human, create its report **before you start**, with `status: in-progress`. A purely informative answer needs no report.

**One file per request**: `.scope/rapports/YYYY-MM-DD-HHMMSS-<slug>.md` (this folder name is the same in every language; UTC time, short kebab-case slug). **Update the same file** at each step: `status`, `actions`, `updated`, the sections. When the human answers you, keep updating the same file. A new request means a new file.

**Never commit or push the report** (`.scope/` is excluded from git). Never write a secret, token, password or personal data in it.

**Waiting for the human.** If you ask a question or need a decision, an access, a value or a manual action: write it as `- Question: …` under `## For you`, set `status: waiting`, then hand over. `waiting` ⇔ at least one question. A note the human should know (a URL to declare, a limit, a risk) is a `- Note: …` and does not put the request on hold.

```markdown
---
project: {{PROJET}}
repo: <repository name>
agent: claude-code        # claude-code | cursor | copilot | codex | other
branch: feat/login-google
request: "Login page with Google authentication"
status: waiting           # in-progress | waiting | done | failed
actions: [code, commit]   # code | commit | push | pr | deploy | outside-repo
started: 2026-11-17T10:30:00Z
updated: 2026-11-17T10:42:00Z
pr: 42                    # optional
---

## Summary
One line: where the request stands.

## For you
- Question: which Google Client ID should I use?
- Note: declare http://localhost:3000/auth/callback in the Google console.

## Details
Files changed, technical choices, tests run.
```

Before handing over, check that the report matches what you actually did: `status` and `actions` (only what was really done), `updated`, and that every open question is listed.
<!-- scope:end -->
