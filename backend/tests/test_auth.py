"""Тесты аутентификации: вход, JWT, защита личных эндпоинтов."""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.auth import create_access_token, hash_password, verify_password


def test_login_returns_token_and_user(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"username": "demo", "password": "demo12345"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"].count(".") == 2, "JWT состоит из трёх частей"
    assert body["expires_in"] > 0
    assert body["user"]["username"] == "demo"
    assert body["user"]["display_name"]


def test_login_is_case_insensitive_for_username(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"username": " DEMO ", "password": "demo12345"})
    assert response.status_code == 200


def test_wrong_password_and_unknown_user(client: TestClient) -> None:
    wrong = client.post("/api/auth/login", json={"username": "demo", "password": "wrong-pass"})
    assert wrong.status_code == 401
    unknown = client.post("/api/auth/login", json={"username": "nobody", "password": "demo12345"})
    assert unknown.status_code == 401
    # Сообщения одинаковые: ответ не должен подсказывать, существует ли логин.
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_me_requires_token(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get("/api/auth/me").status_code == 401
    response = client.get("/api/auth/me", headers=auth)
    assert response.status_code == 200
    assert response.json()["username"] == "demo"


def test_broken_and_expired_tokens_are_rejected(client: TestClient) -> None:
    broken = {"Authorization": "Bearer not-a-jwt"}
    assert client.get("/api/auth/me", headers=broken).status_code == 401

    # Токен с прошедшим сроком жизни подписан тем же секретом, но уже невалиден.
    expired, _ = create_access_token("demo", ttl_minutes=-1)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401

    # Подпись другого секрета не подходит.
    import jwt

    from config import get_settings

    forged = jwt.encode({"sub": "demo"}, "another-secret", algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    assert get_settings().jwt_secret


def test_password_hashing_roundtrip() -> None:
    stored = hash_password("s3cret!")
    assert stored.startswith("pbkdf2_sha256$")
    assert "s3cret!" not in stored, "пароль не должен лежать в открытом виде"
    assert verify_password("s3cret!", stored)
    assert not verify_password("s3cret", stored)
    assert not verify_password("s3cret!", "broken")

    # Одинаковые пароли дают разные хеши: соль случайная.
    assert hash_password("same") != hash_password("same")
