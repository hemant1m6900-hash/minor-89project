from __future__ import annotations

from fastapi.testclient import TestClient


def test_register_login_and_me(client: TestClient) -> None:
    reg = client.post(
        "/api/auth/register",
        json={"full_name": "Auth User", "email": "auth_user@example.com", "password": "password123"},
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "auth_user@example.com"

    dup = client.post(
        "/api/auth/register",
        json={"full_name": "Auth User", "email": "auth_user@example.com", "password": "password123"},
    )
    assert dup.status_code == 409

    bad_login = client.post(
        "/api/auth/login",
        json={"email": "auth_user@example.com", "password": "wrongpassword"},
    )
    assert bad_login.status_code == 401


def test_auth_alias_routes_work(client: TestClient) -> None:
    reg = client.post(
        "/auth/register",
        json={"full_name": "Alias User", "email": "alias_user@example.com", "password": "password123"},
    )
    assert reg.status_code == 201
    data = reg.json()
    assert data["access_token"]
    assert data["user"]["email"] == "alias_user@example.com"

    login = client.post(
        "/auth/login",
        json={"email": "alias_user@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["full_name"] == "Alias User"
