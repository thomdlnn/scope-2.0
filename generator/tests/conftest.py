import os

import pytest


@pytest.fixture(autouse=True)
def sans_token(monkeypatch):
    """Les tests ne lisent jamais un vrai token de l'environnement."""
    for k in ("SCOPE_GH_TOKEN", "SCOPE_GH_API", "SCOPE_PROJECTS"):
        monkeypatch.delenv(k, raising=False)
    assert "SCOPE_GH_TOKEN" not in os.environ
