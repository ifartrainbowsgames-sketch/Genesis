from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.server.app.desktop_auth import DesktopTokenMiddleware


TOKEN = "unit-test-desktop-token"
ORIGIN = "http://tauri.localhost"


def client() -> TestClient:
    inner = FastAPI()

    @inner.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @inner.api_route("/v1/private", methods=["GET", "OPTIONS"])
    async def private() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(DesktopTokenMiddleware(inner, TOKEN, ORIGIN))


def test_health_stays_available_without_desktop_token() -> None:
    response = client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_v1_rejects_missing_or_wrong_token() -> None:
    test_client = client()
    missing = test_client.get("/v1/private")
    wrong = test_client.get("/v1/private", headers={"X-Genesis-Token": "wrong"})

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.json()["detail"] == "Genesis desktop API authorization failed"


def test_v1_accepts_exact_launch_token() -> None:
    response = client().get("/v1/private", headers={"X-Genesis-Token": TOKEN})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_cors_preflight_is_not_blocked_by_token_layer() -> None:
    response = client().options("/v1/private", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_unauthorized_tauri_origin_response_keeps_cors_visibility() -> None:
    response = client().get("/v1/private", headers={"Origin": ORIGIN})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == ORIGIN
