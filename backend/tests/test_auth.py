import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings
from app.models import User, UserRole
from app.schemas.auth import SignupRequest
from app.services import auth_service

PASSWORD = "correct-horse"
SIGNUP = {"login_id": "Alice", "email": "Alice@Example.com", "password": PASSWORD}


def signup(client: TestClient, **overrides):
    return client.post("/api/auth/signup", json={**SIGNUP, **overrides})


def login(client: TestClient, identifier: str = "alice", password: str = PASSWORD):
    return client.post(
        "/api/auth/login", json={"identifier": identifier, "password": password}
    )


def auth_header(client: TestClient) -> dict[str, str]:
    signup(client)
    token = login(client).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- service / model level ---


def test_create_user_defaults(db: Session) -> None:
    user = auth_service.signup(db, SignupRequest(**SIGNUP))
    assert user.id is not None and user.created_at is not None
    assert user.login_id == "alice" and user.email == "alice@example.com"
    assert user.role == UserRole.STAFF


def test_password_is_stored_hashed(db: Session) -> None:
    auth_service.signup(db, SignupRequest(**SIGNUP))
    stored = db.scalar(select(User.password_hash))
    assert stored != PASSWORD and PASSWORD not in stored


def test_password_verification() -> None:
    hashed = security.hash_password(PASSWORD)
    assert security.verify_password(PASSWORD, hashed)
    assert not security.verify_password("wrong-password", hashed)


def test_duplicate_login_id_rejected(db: Session) -> None:
    auth_service.signup(db, SignupRequest(**SIGNUP))
    other = SignupRequest(**{**SIGNUP, "email": "other@example.com", "login_id": "ALICE"})
    with pytest.raises(auth_service.DuplicateUserError) as exc:
        auth_service.signup(db, other)
    assert exc.value.field == "login_id"


def test_duplicate_email_rejected(db: Session) -> None:
    auth_service.signup(db, SignupRequest(**SIGNUP))
    other = SignupRequest(**{**SIGNUP, "login_id": "bob", "email": "ALICE@example.com"})
    with pytest.raises(auth_service.DuplicateUserError) as exc:
        auth_service.signup(db, other)
    assert exc.value.field == "email"


# --- signup API ---


def test_signup_response_hides_password_hash(client: TestClient) -> None:
    response = signup(client)
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "login_id", "email", "role", "created_at"}
    assert body["role"] == "staff"
    assert "password" not in response.text


def test_signup_duplicates_return_409(client: TestClient) -> None:
    signup(client)
    assert signup(client, email="new@example.com").status_code == 409
    assert signup(client, login_id="bob").status_code == 409


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short"},
        {"email": "not-an-email"},
        {"login_id": "  "},
        {"login_id": "has space"},
    ],
)
def test_signup_validation(client: TestClient, overrides: dict) -> None:
    assert signup(client, **overrides).status_code == 422


def test_signup_ignores_client_supplied_role(client: TestClient) -> None:
    assert signup(client, role="admin").json()["role"] == "staff"


# --- login / me ---


def test_login_returns_token_and_user(client: TestClient) -> None:
    signup(client)
    for identifier in ("alice", "ALICE", "alice@example.com"):
        response = login(client, identifier)
        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] and body["token_type"] == "bearer"
        assert body["user"]["login_id"] == "alice"
        assert "password" not in response.text


def test_invalid_login_rejected(client: TestClient) -> None:
    signup(client)
    wrong_password = login(client, password="wrong-password")
    unknown_user = login(client, identifier="nobody")
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()


def test_me_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_valid_token(client: TestClient) -> None:
    response = client.get("/api/auth/me", headers=auth_header(client))
    assert response.status_code == 200
    assert response.json()["login_id"] == "alice"
    assert "password_hash" not in response.json()


def test_me_rejects_invalid_token(client: TestClient) -> None:
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401


def test_me_rejects_reset_token_and_foreign_signature(
    client: TestClient, settings: Settings
) -> None:
    signup(client)
    reset = security.create_reset_token(settings, 1, "hash")
    forged = security.create_access_token(
        settings.model_copy(update={"secret_key": "another-secret-key-of-32-bytes-long!!"}), 1
    )
    for token in (reset, forged):
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def test_me_rejects_expired_token(client: TestClient, settings: Settings) -> None:
    signup(client)
    expired = security.create_access_token(
        settings.model_copy(update={"access_token_expire_minutes": -1}), 1
    )
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


# --- password reset ---


def test_forgot_password_does_not_reveal_accounts(
    client: TestClient, sent_resets: list
) -> None:
    signup(client)
    known = client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert [email for email, _ in sent_resets] == ["alice@example.com"]
    assert "token" not in known.text


def test_reset_password_flow_and_single_use(client: TestClient, sent_resets: list) -> None:
    signup(client)
    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    token = sent_resets[0][1]

    ok = client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "brand-new-pass"}
    )
    assert ok.status_code == 200
    assert login(client, password=PASSWORD).status_code == 401
    assert login(client, password="brand-new-pass").status_code == 200

    replay = client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "another-pass-1"}
    )
    assert replay.status_code == 400


def test_reset_password_rejects_bad_token(client: TestClient, settings: Settings) -> None:
    signup(client)
    access = security.create_access_token(settings, 1)
    for token in ("garbage", access):
        response = client.post(
            "/api/auth/reset-password", json={"token": token, "new_password": "brand-new-pass"}
        )
        assert response.status_code == 400
