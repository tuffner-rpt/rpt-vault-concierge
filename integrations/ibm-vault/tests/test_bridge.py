import base64
import json
from urllib.parse import urlsplit, parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from api import index as bridge

ORIGIN = "https://bridge.example.com"
KEY = "a" * 64
HEADERS = {"Origin": ORIGIN}


@pytest.fixture(autouse=True)
def config(monkeypatch):
    for key, value in {"APP_ORIGIN": ORIGIN, "VAULT_ADDR": "https://vault.example.com:8200", "VAULT_NAMESPACE": "engineering", "PLAN_SIGNING_KEY": "s" * 64, "WXO_BRIDGE_API_KEY": KEY, "ALLOWED_MOUNT_PREFIX": "onboard-"}.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def client():
    with TestClient(bridge.app) as client:
        yield client


def plan_input(**changes):
    return {"action": "enable_engine", "engine": "kv-v2", "mount": "onboard-payments", "description": "Payments development", **changes}


def ticket(client, **changes):
    result = client.post("/api/plans", headers={"x-api-key": KEY}, json=plan_input(**changes))
    assert result.status_code == 200, result.text
    return parse_qs(urlsplit(result.json()["review_url"]).fragment)["plan"][0]


def fake_vault(monkeypatch, responses):
    calls = []
    real_client = httpx.AsyncClient
    def handle(request):
        calls.append(request)
        status, body = responses[len(calls) - 1]
        return httpx.Response(status, json=body) if body is not None else httpx.Response(status)
    monkeypatch.setattr(bridge.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw))
    return calls


def execute(client, signed, **changes):
    return client.post("/api/execute", headers=HEADERS, json={"ticket": signed, "vault_token": "hvs.private-demo-token", "confirmed": True, **changes})


def test_planning_never_contacts_vault(client, monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail("Planning must not contact Vault")
    monkeypatch.setattr(bridge.httpx, "AsyncClient", forbidden)
    signed = ticket(client)
    result = client.post("/api/preview", headers=HEADERS, json={"ticket": signed})
    assert result.status_code == 200
    assert result.json()["vault_address"] == "https://vault.example.com:8200"
    assert result.json()["namespace"] == "engineering"


def test_tool_auth_required(client):
    assert client.post("/api/plans", json=plan_input()).status_code == 401


@pytest.mark.parametrize("mount", ["sys", "onboard-../sys", "onboard-x/sys", "onboard-x%2fsys", "onboard-X", "other-mount", "onboard-x?x", "onboard-x#x"])
def test_reject_bad_mounts(client, mount):
    assert client.post("/api/plans", headers={"x-api-key": KEY}, json=plan_input(mount=mount)).status_code == 422


@pytest.mark.parametrize("path", ["../sys", "a//b", "/root", "a/", "a/%2f", "a/../b", "a?x=y"])
def test_reject_bad_secret_paths(client, path):
    assert client.post("/api/plans", headers={"x-api-key": KEY}, json=plan_input(action="create_secret", secret_path=path)).status_code == 422


def test_tampered_plan_rejected(client):
    signed = ticket(client)
    data, signature = signed.split(".")
    body = json.loads(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)))
    body["plan"]["mount"] = "onboard-hijacked"
    tampered = bridge.encode(json.dumps(body).encode()) + "." + signature
    assert execute(client, tampered).status_code == 400


def test_expired_plan_rejected(client, monkeypatch):
    signed = ticket(client)
    now = bridge.time.time()
    monkeypatch.setattr(bridge.time, "time", lambda: now + 601)
    assert execute(client, signed).status_code == 400


def test_cross_origin_and_no_confirmation_rejected(client):
    signed = ticket(client)
    assert client.post("/api/preview", headers={"Origin": "https://evil.example"}, json={"ticket": signed}).status_code == 403
    assert client.post("/api/execute", json={"ticket": signed, "vault_token": "demo", "confirmed": True}).status_code == 403
    assert execute(client, signed, confirmed=False).status_code == 422


def test_engine_creation(client, monkeypatch):
    calls = fake_vault(monkeypatch, [(400, {"errors": ["No secret engine mount at onboard-payments/"]}), (204, None)])
    result = execute(client, ticket(client))
    assert result.status_code == 200
    assert result.json()["status"] == "created"
    assert [r.method for r in calls] == ["GET", "POST"]
    assert calls[1].url.path == "/v1/sys/mounts/onboard-payments"
    assert calls[1].headers["X-Vault-Namespace"] == "engineering"
    assert calls[1].headers["X-Vault-Token"] == "hvs.private-demo-token"
    assert json.loads(calls[1].content)["options"] == {"version": "2"}


def test_existing_engine_is_noop(client, monkeypatch):
    calls = fake_vault(monkeypatch, [(200, {"data": {"type": "kv", "options": {"version": "2"}}})])
    assert execute(client, ticket(client)).json()["status"] == "already_exists"
    assert len(calls) == 1


def test_other_bad_mount_lookup_does_not_allow_creation(client, monkeypatch):
    calls = fake_vault(monkeypatch, [(400, {"errors": ["different Vault error"]})])
    assert execute(client, ticket(client)).status_code == 409
    assert len(calls) == 1


def test_incompatible_engine_rejected(client, monkeypatch):
    calls = fake_vault(monkeypatch, [(200, {"data": {"type": "kv", "options": {"version": "1"}}})])
    assert execute(client, ticket(client)).status_code == 409
    assert len(calls) == 1


def test_create_secret_cas_and_no_echo(client, monkeypatch):
    calls = fake_vault(monkeypatch, [(200, {"data": {"type": "kv", "options": {"version": "2"}}}), (200, {"data": {"version": 1}})])
    signed = ticket(client, action="create_secret", secret_path="dev/database")
    response = execute(client, signed, secret_data={"password": "secret-value-never-echo"})
    assert response.status_code == 200
    assert "secret-value-never-echo" not in response.text
    assert "hvs.private-demo-token" not in response.text
    assert calls[1].url.path == "/v1/onboard-payments/data/dev/database"
    assert json.loads(calls[1].content) == {"options": {"cas": 0}, "data": {"password": "secret-value-never-echo"}}


def test_secret_does_not_enable_engine(client, monkeypatch):
    calls = fake_vault(monkeypatch, [(404, {})])
    signed = ticket(client, action="create_secret", secret_path="dev/database")
    assert execute(client, signed, secret_data={"password": "demo"}).status_code == 409
    assert len(calls) == 1


def test_existing_secret_rejected_by_cas(client, monkeypatch):
    fake_vault(monkeypatch, [(200, {"data": {"type": "kv", "options": {"version": "2"}}}), (400, {"errors": ["check-and-set failed", "never-echo-this-upstream-data"]})])
    signed = ticket(client, action="create_secret", secret_path="dev/database")
    response = execute(client, signed, secret_data={"password": "demo"})
    assert response.status_code == 409
    assert "never-echo" not in response.text


def test_denied_token_never_writes(client, monkeypatch):
    calls = fake_vault(monkeypatch, [(403, {"errors": ["permission denied"]})])
    assert execute(client, ticket(client)).status_code == 403
    assert len(calls) == 1


def test_validation_never_echoes_input(client):
    response = execute(client, ticket(client), secret_data={"password": {"sensitive": "never-echo"}})
    assert response.status_code == 422
    assert "never-echo" not in response.text
    assert "hvs.private-demo-token" not in response.text


def test_large_request_rejected(client):
    assert execute(client, ticket(client), secret_data={"password": "x" * 70000}).status_code == 413


def test_security_headers_and_assets(client):
    response = client.get("/onboard")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/assets/styles.css").status_code == 200
    assert client.get("/assets/index.py").status_code == 404


def test_chat_identity_signed_short_lived_and_stable_without_cookies(client, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    monkeypatch.setenv("WXO_CHAT_PRIVATE_KEY", pem)
    first = client.post("/api/chat-token", headers=HEADERS, json={})
    assert first.status_code == 200
    claims = jwt.decode(first.json()["token"], key.public_key(), algorithms=["RS256"])
    assert claims["exp"] - claims["iat"] == 300
    client.cookies.clear()
    second = client.post("/api/chat-token", headers=HEADERS, json={"chat_session": first.json()["chat_session"]})
    assert jwt.decode(second.json()["token"], key.public_key(), algorithms=["RS256"])["sub"] == claims["sub"]
    assert "role" not in claims
    assert "vault" not in json.dumps(claims)


def test_missing_configuration_fails_closed(client, monkeypatch):
    monkeypatch.delenv("WXO_BRIDGE_API_KEY")
    assert client.post("/api/plans", headers={"x-api-key": KEY}, json=plan_input()).status_code == 503
