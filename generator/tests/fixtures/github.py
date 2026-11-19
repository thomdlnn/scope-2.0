"""API GitHub simulée pour les dépôts de la fausse racine (tests/fixtures/racine.py).

Sert aux tests (FakeSession, sans réseau) et à la vérification navigateur
(serveur HTTP local, SCOPE_GH_API) :

    python tests/fixtures/github.py PORT
"""

from __future__ import annotations

import http.server
import json
import sys
from urllib.parse import parse_qs, urlparse

import requests

FRONT_SHA = "f" * 40
FRONT_DEPLOYE = "e" * 40
API_SHA = "a" * 40


def pr(n, titre, auteur, brouillon=False, repo="acme/demo-front"):
    return {"number": n, "title": titre, "html_url": f"https://github.com/{repo}/pull/{n}",
            "user": {"login": auteur}, "draft": brouillon, "updated_at": "2026-11-17T09:00:00Z"}


def commit(sha, message, date="2026-11-17T08:00:00Z", repo="acme/demo-front"):
    return {"sha": sha, "html_url": f"https://github.com/{repo}/commit/{sha}",
            "commit": {"message": message, "committer": {"date": date}}}


#: (chemin, ref) → (statut HTTP, corps). ref None : toute ref.
ROUTES: dict[tuple[str, str | None], tuple[int, object]] = {
    ("/repos/acme/demo-front", None): (200, {"default_branch": "main"}),
    ("/repos/acme/demo-front/pulls", None): (200, [
        pr(12, "Page de login Google", "alice"),
        pr(13, "WIP: thème sombre", "dependabot[bot]", brouillon=True),
    ]),
    ("/repos/acme/demo-front/commits/main", None): (200, commit(FRONT_SHA, "feat(front): en-tête\n\ncorps")),
    (f"/repos/acme/demo-front/compare/{FRONT_DEPLOYE}...main", None): (200, {"ahead_by": 2}),
    ("/repos/acme/demo-api", None): (200, {"default_branch": "develop"}),
    ("/repos/acme/demo-api/pulls", None): (403, {"message": "Resource not accessible by personal access token"}),
    ("/repos/acme/demo-api/commits/develop", None): (
        200, commit(API_SHA, "Merge pull request #4 from acme/fix\n\nCorrige la pagination", repo="acme/demo-api")),
    (f"/repos/acme/demo-api/compare/{API_SHA}...develop", None): (200, {"ahead_by": 0}),
    ("/repos/acme/demo-deploy", None): (200, {"default_branch": "main"}),
    ("/repos/acme/demo-deploy/contents/environments/local/demo-front.yaml", "main"): (
        200, f"image:\n  tag: {FRONT_DEPLOYE}\n"),
    ("/repos/acme/demo-deploy/contents/environments/local/demo-api.yaml", "main"): (200, f"image:\n  tag: {API_SHA}\n"),
}


#: Santé de l'application « demo » (projects/demo.yml : sante), servie avec CORS.
SANTE = {"status": "degraded", "services": {"demo-front": "ok", "demo-api": "unavailable"},
         "versions": {"demo-api": API_SHA, "demo-front": "0" * 40}}
ROUTES[("/sante-demo.json", None)] = (200, SANTE)


def repondre(path: str, query: dict) -> tuple[int, object]:
    ref = query.get("ref") or query.get("sha")
    return ROUTES.get((path, ref), ROUTES.get((path, None), (404, {"message": "Not Found"})))


class FakeSession(requests.Session):
    """Session requests qui répond depuis des routes, sans réseau."""

    def __init__(self, routes=None):
        super().__init__()
        self.routes = ROUTES if routes is None else routes
        self.calls: list[str] = []

    def get(self, url, params=None, headers=None, timeout=None):
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        q.update({k: str(v) for k, v in (params or {}).items()})
        self.calls.append(u.path)
        ref = q.get("ref") or q.get("sha")
        status, body = self.routes.get((u.path, ref), self.routes.get((u.path, None), (404, {"message": "Not Found"})))
        r = requests.Response()
        r.status_code = status
        r.url = url
        r._content = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        return r


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        status, body = repondre(u.path, {k: v[0] for k, v in parse_qs(u.query).items()})
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1] if len(sys.argv) > 1 else 9999)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler).serve_forever()
