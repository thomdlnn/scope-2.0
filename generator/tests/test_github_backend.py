"""Backend GitHub contre une API simulée (aucun appel réseau)."""

import json
from urllib.parse import parse_qs, urlparse

import requests

from scope_gen.backends import GitHubBackend
from scope_gen.models import Project
from scope_gen.sources import ReportsSource

REPORT = """---
date: 2026-11-16T10:30:00Z
projet: demo
repo: front
agent: claude-code
commit_message: "feat: login (message IA)"
pr_titre: "Login"
statut: pr-ouverte
---

## Résumé court
Login.
"""


class FakeSession(requests.Session):
    def __init__(self, routes):
        super().__init__()
        self.routes = routes
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        q.update({k: str(v) for k, v in (params or {}).items()})
        key = (u.path, q.get("ref") or q.get("sha"))
        self.calls.append(key)
        status, body, links = self.routes.get(key, self.routes.get((u.path, None), (404, {"message": "Not Found"}, None)))
        r = requests.Response()
        r.status_code = status
        r.url = url
        r._content = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        if links:
            r.headers["Link"] = links
        return r


def routes():
    api = "/repos/o/front"
    listing = lambda ref: [{"name": "2026-11-16-103000-login.md", "type": "file", "path": ".scope/rapports/2026-11-16-103000-login.md"}]
    return {
        (api, None): (200, {"default_branch": "develop"}, None),
        (f"{api}/pulls", None): (200, [{"head": {"ref": "feat/login", "repo": {"full_name": "o/front"}}}], None),
        (f"{api}/contents/.scope/rapports", "develop"): (404, {}, None),
        (f"{api}/contents/.scope/rapports", "feat/login"): (200, listing("feat/login"), None),
        (f"{api}/contents/.scope/rapports/2026-11-16-103000-login.md", "feat/login"): (200, REPORT, None),
        (f"{api}/commits", "feat/login"): (
            200,
            [{"sha": "b" * 40, "html_url": "https://github.com/o/front/commit/bbb", "commit": {"message": "feat: x"}}],
            '<https://api.github.com/repos/o/front/commits?page=2>; rel="last"',
        ),
        (f"{api}/commits/{'a' * 40}/pulls", None): (
            200,
            [{"number": 7, "title": "Login", "state": "closed", "merged_at": "2026-11-16T12:00:00Z", "html_url": "https://github.com/o/front/pull/7"}],
            None,
        ),
    }


def test_lit_branches_de_pr_et_resout_commit_et_pr():
    r = routes()
    # Page « last » des commits (Link rel=last suivi) : le plus ancien (celui qui a ajouté le fichier) est le dernier.
    r[("/repos/o/front/commits", None)] = (
        200,
        [{"sha": "a" * 40, "html_url": "https://github.com/o/front/commit/aaa", "commit": {"message": "feat: login\n\ncorps"}}],
        None,
    )
    s = FakeSession(r)
    backend = GitHubBackend("t", session=s)
    assert s.headers["Authorization"] == "Bearer t"

    result = ReportsSource().collect(Project("demo", "Démo", ["o/front"]), backend)
    assert result.errors == []
    (rep,) = result.reports
    assert rep.valid and rep.ref == "feat/login"
    assert rep.commit.sha == "a" * 40 and rep.commit.message == "feat: login"
    assert rep.pr.number == 7 and rep.pr.state == "merged"


def test_depot_inaccessible_consigne_sans_casser():
    backend = GitHubBackend("t", session=FakeSession({}))
    result = ReportsSource().collect(Project("demo", "Démo", ["o/absent"]), backend)
    assert result.reports == [] and "HTTP 404" in result.errors[0]
