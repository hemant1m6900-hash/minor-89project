from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

# Configure isolated test environment before importing backend modules
_TMP_DIR = tempfile.TemporaryDirectory()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_TMP_DIR.name) / 'test_suite.db'}")
os.environ.setdefault("UPLOAD_DIR", str(Path(_TMP_DIR.name) / "uploads"))
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-for-automated-pytest-run-only-32")

from backend.database import Base, engine  # noqa: E402
from backend.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    _TMP_DIR.cleanup()


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def register_and_login(client: TestClient, email: str, password: str = "secret123", full_name: str = "Test Analyst") -> dict:
    resp = client.post(
        "/api/auth/register",
        json={"full_name": full_name, "email": email, "password": password},
    )
    if resp.status_code == 409:
        resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code in (200, 201), resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
