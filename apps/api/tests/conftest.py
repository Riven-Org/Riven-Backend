from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from riven_api.config import get_settings
from riven_api.db import _sessionmaker, get_engine
from riven_api.main import create_app


def _clear_caches() -> None:
    for cached in (get_settings, get_engine, _sessionmaker):
        cached.cache_clear()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """An API client backed by a fresh SQLite database file."""
    monkeypatch.setenv("RIVEN_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    _clear_caches()
    with TestClient(create_app()) as c:  # runs the lifespan, which creates the tables
        yield c
    _clear_caches()
