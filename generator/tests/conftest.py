from pathlib import Path

import pytest

from tests.fixtures.make_repos import build

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def local_repos(tmp_path_factory) -> Path:
    return build(tmp_path_factory.mktemp("repos"))


@pytest.fixture
def projects_dir() -> Path:
    return FIXTURES / "projects"
