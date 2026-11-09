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
    monkeypatch.setattr(bridge.admin_review, "enabled", lambda: False)
    reviews = {}
    async def save(review_id, signed):
        reviews[review_id] = signed
    async def resolve(review_id):
        if review_id not in reviews:
            raise bridge.HTTPException(400, "Invalid or expired review link")
        return reviews[review_id]
    monkeypatch.setattr(bridge, "store_review", save)
    monkeypatch.setattr(bridge, "resolve_review", resolve)
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
    review_id = parse_qs(urlsplit(result.json()["review_url"]).fragment)["review"][0]
    resolved = client.post("/api/resolve", headers=HEADERS, json={"review_id": review_id})
    assert resolved.status_code == 200
    return resolved.json()["ticket"]


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


@pytest.mark.parametrize("engine", ["aws", "azure", "gcp", "gcpkms", "alicloud", "consul", "kv-v1", "ssh", "rabbitmq", "ldap", "openldap", "mongodbatlas", "nomad", "kubernetes", "terraform", "totp", "transform", "kmip", "keymgmt", "custom-secrets-plugin"])
def test_all_mountable_engine_names_can_be_planned(client, engine):
    signed = ticket(client, engine=engine)
    assert bridge.read_plan(signed).engine == engine


@pytest.mark.parametrize("engine", ["auth", "system", "identity", "cubbyhole", "foo/bar", "https://evil.example", "aws%2fconfig"])
def test_system_and_unsafe_engine_names_rejected(client, engine):
    assert client.post("/api/plans", headers={"x-api-key": KEY}, json=plan_input(engine=engine)).status_code == 422


SCHEMA = {"paths": {"/roles/{name}": {"post": {"summary": "Configure a role", "requestBody": {"content": {"application/json": {"schema": {"type": "object", "required": ["ttl"], "properties": {"ttl": {"type": "integer"}}, "additionalProperties": False}}}}}}, "/creds/{name}": {"get": {"summary": "Generate credentials"}}}, "components": {}}


def operation_ticket(client, **changes):
    return ticket(client, **{"action": "engine_operation", "engine": "aws", "endpoint": "roles/demo", "method": "POST", **changes})


def operation_responses(*tail, document=None):
    mount = (200, {"data": {"type": "aws"}})
    return [mount, mount, (200, {"openapi": document or SCHEMA}), *tail]


def redis_config(monkeypatch):
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://redis.example.com")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-redis-secret")


def test_live_schema_inspection_returns_no_provider_credentials(client, monkeypatch):
    fake_vault(monkeypatch, [(200, {"data": {"type": "aws"}}), (200, {"openapi": SCHEMA})])
    response = client.post("/api/inspect", headers=HEADERS, json={"ticket": operation_ticket(client), "vault_token": "hvs.test"})
    assert response.status_code == 200
    assert response.json()["request_schema"]["required"] == ["ttl"]
    assert "hvs.test" not in response.text


def test_generic_operation_typed_confirmation_required(client):
    assert execute(client, operation_ticket(client), operation_json='{"ttl":60}').status_code == 422


def test_schema_validated_operation_uses_durable_claim_before_write(client, monkeypatch):
    redis_config(monkeypatch)
    calls = fake_vault(monkeypatch, operation_responses((200, {"result": "OK"}), (204, None)))
    response = execute(client, operation_ticket(client), operation_json='{"ttl":60}', confirmation_text="EXECUTE POST onboard-payments/roles/demo")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert calls[-2].url.host == "redis.example.com"
    assert json.loads(calls[-2].content)[-1] == "NX"
    assert "X-Vault-Token" not in calls[-2].headers
    assert calls[-1].url.path == "/v1/onboard-payments/roles/demo"
    assert "Authorization" not in calls[-1].headers


def test_schema_mismatch_never_claims_or_writes(client, monkeypatch):
    calls = fake_vault(monkeypatch, operation_responses())
    response = execute(client, operation_ticket(client), operation_json='{"ttl":"credential-never-echo"}', confirmation_text="EXECUTE POST onboard-payments/roles/demo")
    assert response.status_code == 422
    assert "credential-never-echo" not in response.text
    assert len(calls) == 3


def test_unpublished_endpoint_never_claims_or_writes(client, monkeypatch):
    calls = fake_vault(monkeypatch, operation_responses())
    response = execute(client, operation_ticket(client, endpoint="undocumented/demo"), confirmation_text="EXECUTE POST onboard-payments/undocumented/demo")
    assert response.status_code == 422
    assert len(calls) == 3


def test_remote_schema_references_never_fetched(client, monkeypatch):
    schema = {"paths": {}, "components": {"schemas": {"x": {"$ref": "https://evil.example/steal"}}}}
    calls = fake_vault(monkeypatch, operation_responses(document=schema))
    response = execute(client, operation_ticket(client), confirmation_text="EXECUTE POST onboard-payments/roles/demo")
    assert response.status_code == 409
    assert len(calls) == 3


def test_operation_replay_is_refused_before_write(client, monkeypatch):
    redis_config(monkeypatch)
    calls = fake_vault(monkeypatch, operation_responses((200, {"result": None})))
    response = execute(client, operation_ticket(client), operation_json='{"ttl":60}', confirmation_text="EXECUTE POST onboard-payments/roles/demo")
    assert response.status_code == 409
    assert len(calls) == 4


def test_missing_durable_store_refuses_mutation(client, monkeypatch):
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    calls = fake_vault(monkeypatch, operation_responses())
    response = execute(client, operation_ticket(client), operation_json='{"ttl":60}', confirmation_text="EXECUTE POST onboard-payments/roles/demo")
    assert response.status_code == 503
    assert len(calls) == 3


def test_generated_credentials_return_only_to_secure_browser_endpoint(client, monkeypatch):
    redis_config(monkeypatch)
    fake_vault(monkeypatch, operation_responses((200, {"result": "OK"}), (200, {"data": {"secret_key": "generated-test-secret"}, "lease_id": "aws/creds/demo/test", "lease_duration": 60})))
    signed = operation_ticket(client, method="GET", endpoint="creds/demo")
    response = execute(client, signed)
    assert response.status_code == 200
    assert response.json()["sensitive_result"]["data"]["secret_key"] == "generated-test-secret"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
def test_generic_operations_cannot_bypass_kv_v2_cas(client, method):
    result = client.post("/api/plans", headers={"x-api-key": KEY}, json=plan_input(action="engine_operation", endpoint="data/dev/password", method=method))
    assert result.status_code == 422


def test_disable_requires_typed_confirmation_and_durable_claim(client, monkeypatch):
    signed = ticket(client, action="disable_engine")
    assert execute(client, signed).status_code == 422
    redis_config(monkeypatch)
    calls = fake_vault(monkeypatch, [(200, {"data": {"type": "kv", "options": {"version": "2"}}}), (200, {"result": "OK"}), (204, None)])
    response = execute(client, signed, confirmation_text="DISABLE onboard-payments")
    assert response.status_code == 200
    assert calls[-1].method == "DELETE"
    assert calls[-1].url.path == "/v1/sys/mounts/onboard-payments"


def test_tune_rejects_audit_weakening_options(client, monkeypatch):
    calls = fake_vault(monkeypatch, [(200, {"data": {"type": "kv", "options": {"version": "2"}}})])
    response = execute(client, ticket(client, action="tune_engine"), operation_json='{"audit_non_hmac_request_keys":["password"]}')
    assert response.status_code == 422
    assert len(calls) == 1


def test_nested_kv_read_matches_wildcard_schema():
    plan = bridge.Plan(action="engine_operation", engine="kv-v2", mount="onboard-test", endpoint="data/dev/database", method="GET")
    assert bridge.operation_definition({"paths": {"/data/{path}": {"get": {"summary": "Read secret"}}}}, plan)["summary"] == "Read secret"


def test_kv_alias_cannot_bypass_cas(client):
    result = client.post("/api/plans", headers={"x-api-key": KEY}, json=plan_input(action="engine_operation", engine="kv", endpoint="data/dev/password"))
    assert result.status_code == 422


def test_durable_store_failure_prevents_engine_write(client, monkeypatch):
    redis_config(monkeypatch)
    calls = fake_vault(monkeypatch, operation_responses((503, {"error": "unavailable"})))
    response = execute(client, operation_ticket(client), operation_json='{"ttl":60}', confirmation_text="EXECUTE POST onboard-payments/roles/demo")
    assert response.status_code == 503
    assert len(calls) == 4


def test_catalog_is_not_live_vault_inventory(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Static capability catalog must not query Vault")
    monkeypatch.setattr(bridge.httpx, "AsyncClient", forbidden)
    response = client.get("/api/catalog")
    assert response.status_code == 200
    data = response.json()
    assert data["catalog_source"] == "static_bridge_capabilities"
    assert data["vault_queried"] is False
    assert data["availability_verified"] is False
    assert data["engines"]
    for engine in data["engines"].values():
        assert engine["vault_availability"] == "unverified"
        assert "capability" in engine
        assert "ready" not in engine


def test_mount_review_shows_exact_scoped_permissions(client):
    signed = ticket(client, mount="onboard-payments")
    result = client.post("/api/preview", headers=HEADERS, json={"ticket": signed})
    policy = result.json()["access_requirements"]["policy_hcl"]
    assert 'path "sys/mounts/onboard-payments"' in policy
    assert 'path "sys/plugins/catalog"' in policy
    assert '"update"' in policy
    assert '"delete"' not in policy
    assert '*' not in policy


def test_secret_review_grants_create_only_at_one_path(client):
    signed = ticket(client, action="create_secret", secret_path="dev/database")
    result = client.post("/api/preview", headers=HEADERS, json={"ticket": signed})
    policy = result.json()["access_requirements"]["policy_hcl"]
    assert 'path "onboard-payments/data/dev/database"' in policy
    assert 'capabilities = ["create"]' in policy
    assert '"update"' not in policy
    assert '"delete"' not in policy
    assert '*' not in policy


def test_review_lookup_requires_same_origin_and_valid_id(client):
    assert client.post("/api/resolve", json={"review_id": "a" * 22}).status_code == 403
    assert client.post("/api/resolve", headers=HEADERS, json={"review_id": "a" * 22}).status_code == 400
    assert client.post("/api/resolve", headers=HEADERS, json={"review_id": "../escape"}).status_code == 422


@pytest.mark.parametrize('version', ['1', '2'])
def test_kv_mount_only_plan_collects_business_unit(client, monkeypatch, version):
    def forbidden(*args, **kwargs):
        pytest.fail('Planning must not contact Vault')
    monkeypatch.setattr(bridge.httpx, 'AsyncClient', forbidden)
    response = client.post('/api/kv-mount-plans', headers={'x-api-key': KEY}, json={
        'business_unit_id': 'BU-123', 'mount': 'onboard-payments', 'kv_version': version})
    assert response.status_code == 200
    plan = response.json()['plan']
    assert plan['business_unit_id'] == 'BU-123'
    assert plan['action'] == 'enable_engine' and plan['engine'] == 'kv-v' + version
    assert plan['secret_path'] == '' and plan['endpoint'] == ''


@pytest.mark.parametrize('changes', [
    {'engine': 'database'}, {'action': 'create_secret'}, {'secret_data': {'password': 'blocked'}},
    {'endpoint': 'config/root'}, {'kv_version': '3'}, {'kv_version': 'database'},
    {'business_unit_id': ''}, {'business_unit_id': '<script>'}, {'mount': 'sys'},
    {'mount': 'onboard-bu/kv'}, {'mount': 'other-mount'},
])
def test_kv_mount_only_rejects_other_activities(client, changes):
    response = client.post('/api/kv-mount-plans', headers={'x-api-key': KEY}, json={
        'business_unit_id': 'BU-123', 'mount': 'onboard-payments', 'kv_version': '2', **changes})
    assert response.status_code == 422


def test_kv_mount_only_requires_tool_auth(client):
    assert client.post('/api/kv-mount-plans', json={
        'business_unit_id': 'BU-123', 'mount': 'onboard-payments', 'kv_version': '2'}).status_code == 401


def test_kv_mount_chat_config_never_falls_back_to_general_agent(client, monkeypatch):
    for key, value in {'WXO_HOST_URL': 'https://ibm.example.com', 'WXO_ORCHESTRATION_ID': 'orch',
                       'WXO_AGENT_ID': 'general', 'WXO_AGENT_ENVIRONMENT_ID': 'general-live'}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('WXO_KV_MOUNT_AGENT_ID', raising=False)
    monkeypatch.delenv('WXO_KV_MOUNT_AGENT_ENVIRONMENT_ID', raising=False)
    assert client.get('/api/kv-mount-chat-config').status_code == 503
    monkeypatch.setenv('WXO_KV_MOUNT_AGENT_ID', 'kv-only')
    monkeypatch.setenv('WXO_KV_MOUNT_AGENT_ENVIRONMENT_ID', 'kv-live')
    assert client.get('/api/kv-mount-chat-config').json()['chatOptions'] == {
        'agentId': 'kv-only', 'agentEnvironmentId': 'kv-live'}
    assert client.get('/api/chat-config').json()['chatOptions']['agentId'] == 'general'


@pytest.fixture
def intake_key(monkeypatch):
    monkeypatch.setenv('KV_MOUNT_INTAKE_KEY', 'i' * 64)
    return {'x-kv-mount-key': 'i' * 64}


def intake_payload(**changes):
    return {'mount': 'Onboard-payments', 'business_unit_id': 'BU-123', 'user_id': 'developer@example.com', **changes}


def test_guided_kv_intake_preserves_case_and_records_identity(client, intake_key):
    response = client.post('/api/kv-mount-intake', headers=intake_key, json=intake_payload())
    assert response.status_code == 200
    plan = response.json()['plan']
    assert plan['mount'] == 'Onboard-payments'
    assert plan['business_unit_id'] == 'BU-123' and plan['user_id'] == 'developer@example.com'
    assert plan['action'] == 'enable_engine' and plan['engine'] == 'kv-v2'
    assert plan['secret_path'] == '' and plan['endpoint'] == ''


@pytest.mark.parametrize('changes', [
    {'mount': 'onboard-payments'}, {'mount': 'Onboard-../sys'}, {'mount': 'Onboard-foo/bar'},
    {'mount': 'Onboard-'}, {'mount': 'Onboard-Payments'}, {'business_unit_id': ''}, {'user_id': ''},
    {'user_id': '<script>'}, {'engine': 'database'}, {'action': 'create_secret'},
    {'kv_version': '1'}, {'secret_data': {'password': 'blocked'}},
])
def test_guided_intake_rejects_other_actions_and_bad_fields(client, intake_key, changes):
    assert client.post('/api/kv-mount-intake', headers=intake_key, json=intake_payload(**changes)).status_code == 422


def test_intake_credential_cannot_mint_generic_plans(client, intake_key):
    assert client.post('/api/plans', headers=intake_key, json=plan_input()).status_code == 401
    assert client.post('/api/kv-mount-plans', headers=intake_key, json={
        'business_unit_id': 'BU-123', 'mount': 'onboard-payments', 'kv_version': '1'}).status_code == 401
    assert client.post('/api/kv-mount-intake', headers={'x-api-key': KEY}, json=intake_payload()).status_code == 401


@pytest.fixture
def secret_intake_key(monkeypatch):
    monkeypatch.setenv('VAULT_NAMESPACE', 'admin')
    monkeypatch.setenv('KV_SECRET_INTAKE_KEY', 'v' * 64)
    return {'x-kv-secret-key': 'v' * 64}


def secret_intake_payload(**changes):
    return {'mount': 'onboard-concierge', 'secret_path': 'app/database',
            'business_unit_id': 'BU-123', 'user_id': 'developer@example.com', **changes}


@pytest.mark.parametrize('mount', ['onboard-concierge'])
def test_secret_intake_is_create_only_metadata(client, secret_intake_key, monkeypatch, mount):
    def forbidden(*args, **kwargs):
        pytest.fail('Secret planning must not contact Vault')
    monkeypatch.setattr(bridge.httpx, 'AsyncClient', forbidden)
    response = client.post('/api/kv-secret-intake', headers=secret_intake_key, json=secret_intake_payload(mount=mount))
    assert response.status_code == 200
    plan = response.json()['plan']
    assert plan['action'] == 'create_secret' and plan['engine'] == 'kv-v2'
    assert plan['mount'] == mount and plan['secret_path'] == 'app/database'
    assert plan['business_unit_id'] == 'BU-123' and plan['user_id'] == 'developer@example.com'
    assert 'secret_data' not in plan and plan['endpoint'] == ''


@pytest.mark.parametrize('changes', [
    {'mount': 'onboard-other'}, {'mount': 'Onboard-concierge'}, {'mount': 'onboard-concierge/other'},
    {'action': 'enable_engine'}, {'engine': 'database'}, {'kv_version': '1'},
    {'secret_data': {'password': 'must-not-be-accepted'}}, {'operation_json': '{}'},
    {'secret_path': ''}, {'secret_path': '../sys'}, {'secret_path': '/app'},
    {'secret_path': 'a//b'}, {'secret_path': 'a/..'}, {'secret_path': 'a/'},
    {'secret_path': 'a?overwrite=true'}, {'secret_path': 'a%2fb'},
    {'business_unit_id': ''}, {'user_id': ''}, {'mount': 'sys'},
])
def test_secret_intake_rejects_other_operations_and_values(client, secret_intake_key, changes):
    response = client.post('/api/kv-secret-intake', headers=secret_intake_key, json=secret_intake_payload(**changes))
    assert response.status_code == 422
    assert 'must-not-be-accepted' not in response.text


def test_secret_credential_does_not_allow_other_workflows(client, secret_intake_key, intake_key):
    assert client.post('/api/plans', headers=secret_intake_key, json=plan_input()).status_code == 401
    assert client.post('/api/kv-mount-intake', headers=secret_intake_key, json=intake_payload()).status_code == 401
    assert client.post('/api/kv-secret-intake', headers=intake_key, json=secret_intake_payload()).status_code == 401


def test_secret_intake_defaults_to_concierge_mount(client, secret_intake_key):
    body = secret_intake_payload()
    body.pop('mount')
    response = client.post('/api/kv-secret-intake', headers=secret_intake_key, json=body)
    assert response.status_code == 200
    assert response.json()['plan']['mount'] == 'onboard-concierge'


@pytest.mark.parametrize('namespace', ['', 'engineering', 'Admin', 'admin/child'])
def test_guided_secret_intake_cannot_target_other_namespaces(client, secret_intake_key, monkeypatch, namespace):
    monkeypatch.setenv('VAULT_NAMESPACE', namespace)
    response = client.post('/api/kv-secret-intake', headers=secret_intake_key, json=secret_intake_payload())
    assert response.status_code == 503


def test_guided_secret_plan_cannot_be_retargeted_after_creation(client, secret_intake_key, monkeypatch):
    response = client.post('/api/kv-secret-intake', headers=secret_intake_key, json=secret_intake_payload())
    assert response.status_code == 200 and response.json()['namespace'] == 'admin'
    review_id = parse_qs(urlsplit(response.json()['review_url']).fragment)['review'][0]
    signed = client.post('/api/resolve', headers=HEADERS, json={'review_id': review_id}).json()['ticket']
    monkeypatch.setenv('VAULT_NAMESPACE', 'admin/child')
    assert client.post('/api/preview', headers=HEADERS, json={'ticket': signed}).status_code == 503


def test_guided_secret_intake_rejects_client_namespace(client, secret_intake_key):
    assert client.post('/api/kv-secret-intake', headers=secret_intake_key,
                       json=secret_intake_payload(namespace='other')).status_code == 422
