"""Optional real Vault smoke test using an isolated, disposable local dev server."""
import os
import secrets
import shutil
import socket
import subprocess
import time
import base64
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from api.index import app
from api import index as bridge
from fastapi import HTTPException


@pytest.mark.skipif(not shutil.which("vault"), reason="Vault binary is not installed")
def test_real_local_vault_onboarding(monkeypatch):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    address = f"http://127.0.0.1:{port}"
    root_token = secrets.token_hex(32)
    bridge_key = secrets.token_hex(32)
    origin = "https://bridge.example.com"
    env = {**os.environ, "VAULT_DEV_ROOT_TOKEN_ID": root_token, "VAULT_DEV_LISTEN_ADDRESS": f"127.0.0.1:{port}", "VAULT_ADDR": address}
    proc = subprocess.Popen([shutil.which("vault"), "server", "-dev", "-dev-no-store-token"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url=address, headers={"X-Vault-Token": root_token}, trust_env=False, timeout=2) as vault:
            for attempt in range(50):
                try:
                    if vault.get("/v1/sys/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if proc.poll() is not None:
                    pytest.fail("Isolated Vault dev server failed to start")
                time.sleep(0.1)
            else:
                pytest.fail("Isolated Vault dev server did not become healthy")
            for name, value in {"VAULT_ADDR": address, "VAULT_NAMESPACE": "", "APP_ORIGIN": origin, "WXO_BRIDGE_API_KEY": bridge_key, "PLAN_SIGNING_KEY": secrets.token_hex(32), "ALLOWED_MOUNT_PREFIX": "onboard-"}.items():
                monkeypatch.setenv(name, value)
            with TestClient(app) as client:
                def prepare(**changes):
                    response = client.post("/api/plans", headers={"x-api-key": bridge_key}, json={"action": "enable_engine", "engine": "kv-v2", "mount": "onboard-integration", **changes})
                    assert response.status_code == 200, response.text
                    return parse_qs(urlsplit(response.json()["review_url"]).fragment)["plan"][0]
                def execute(ticket, token, **changes):
                    return client.post("/api/execute", headers={"Origin": origin}, json={"ticket": ticket, "vault_token": token, "confirmed": True, **changes})
                engine_plan = prepare()
                result = execute(engine_plan, root_token)
                assert result.status_code == 200, result.text
                assert result.json()["status"] == "created"
                assert execute(engine_plan, root_token).json()["status"] == "already_exists"
                # A real scoped caller can write only beneath one application path.
                policy = 'path "sys/mounts/onboard-integration" { capabilities = ["read"] }\npath "onboard-integration/data/dev/*" { capabilities = ["create", "update"] }'
                assert vault.put("/v1/sys/policies/acl/rpt-test", json={"policy": policy}).status_code == 204
                issued = vault.post("/v1/auth/token/create", json={"policies": ["rpt-test"], "no_default_policy": True, "ttl": "5m"})
                assert issued.status_code == 200
                caller_token = issued.json()["auth"]["client_token"]
                secret_plan = prepare(action="create_secret", secret_path="dev/database")
                result = execute(secret_plan, caller_token, secret_data={"password": "disposable-integration-test-value"})
                assert result.status_code == 200, result.text
                assert result.json()["version"] == 1
                assert "disposable-integration-test-value" not in result.text
                result = execute(secret_plan, caller_token, secret_data={"password": "must-not-overwrite"})
                assert result.status_code == 409
                stored = vault.get("/v1/onboard-integration/data/dev/database").json()["data"]
                assert stored["metadata"]["version"] == 1
                assert stored["data"]["password"] == "disposable-integration-test-value"
                forbidden = prepare(action="create_secret", secret_path="prod/database")
                assert execute(forbidden, caller_token, secret_data={"password": "denied"}).status_code == 403
                assert vault.get("/v1/onboard-integration/data/prod/database").status_code == 404
                available = vault.get("/v1/sys/plugins/catalog").json()["data"]
                mountable = {item["name"] for item in available["detailed"] if item["type"] == "secret" and item.get("deprecation_status") == "supported"}
                for engine in sorted(mountable | {"database", "kv-v1"}):
                    result = execute(prepare(engine=engine, mount=f"onboard-{engine}"), root_token)
                    assert result.status_code == 200, result.text
                    assert result.json()["status"] == "created"
                assert {"aws", "azure", "gcp", "transit", "pki", "kv", "ssh", "totp"}.issubset(mountable)

                # Redis REST behavior is covered separately with HTTP mocks. This
                # integration exercises real Vault operations with a test-only claim.
                claimed = set()
                async def test_claim(_client, signed):
                    if signed in claimed:
                        raise HTTPException(409, "Already submitted")
                    claimed.add(signed)
                monkeypatch.setattr(bridge, "claim_operation", test_claim)

                def operation(endpoint, payload, method="POST"):
                    signed = prepare(action="engine_operation", engine="transit", mount="onboard-transit", endpoint=endpoint, method=method)
                    result = execute(signed, root_token, operation_json=json.dumps(payload), confirmation_text=f"EXECUTE {method} onboard-transit/{endpoint}" if method in {"POST", "PUT", "PATCH"} else "")
                    assert result.status_code == 200, result.text
                    return result.json(), signed

                operation("keys/demo", {"type": "aes256-gcm96"})
                listed, _ = operation("keys", {}, method="LIST")
                assert "demo" in listed["sensitive_result"]["data"]["keys"]
                plaintext = base64.b64encode(b"disposable-local-test").decode()
                encrypted, _ = operation("encrypt/demo", {"plaintext": plaintext})
                ciphertext = encrypted["sensitive_result"]["data"]["ciphertext"]
                decrypted, _ = operation("decrypt/demo", {"ciphertext": ciphertext})
                assert decrypted["sensitive_result"]["data"]["plaintext"] == plaintext
                _, rotate_plan = operation("keys/demo/rotate", {})
                assert execute(rotate_plan, root_token, confirmation_text="EXECUTE POST onboard-transit/keys/demo/rotate").status_code == 409
                assert vault.get("/v1/onboard-transit/keys/demo").json()["data"]["latest_version"] == 2

                tune = prepare(action="tune_engine", engine="transit", mount="onboard-transit")
                assert execute(tune, root_token, operation_json='{"default_lease_ttl":"30m","max_lease_ttl":"60m"}').status_code == 200
                assert vault.get("/v1/sys/mounts/onboard-transit/tune").json()["data"]["max_lease_ttl"] == 3600

                kv1 = prepare(action="engine_operation", engine="kv-v1", mount="onboard-kv-v1", endpoint="dev/database")
                assert execute(kv1, root_token, operation_json='{"password":"kv1-test"}', confirmation_text="EXECUTE POST onboard-kv-v1/dev/database").status_code == 200
                disable = prepare(action="disable_engine", engine="kv-v1", mount="onboard-kv-v1")
                assert execute(disable, root_token, confirmation_text="DISABLE onboard-kv-v1").status_code == 200
                assert vault.get("/v1/onboard-kv-v1/dev/database").status_code == 404

                root_plan = prepare(action="engine_operation", engine="pki", mount="onboard-pki", endpoint="root/generate/internal")
                result = execute(root_plan, root_token, operation_json='{"common_name":"disposable.test","ttl":"1h"}', confirmation_text="EXECUTE POST onboard-pki/root/generate/internal")
                assert result.status_code == 200, result.text
                cert_plan = prepare(action="engine_operation", engine="pki", mount="onboard-pki", endpoint="ca/pem", method="GET")
                result = execute(cert_plan, root_token)
                assert result.status_code == 200, result.text
                raw = result.json()["sensitive_result"]["data"]["raw_body_base64"]
                assert b"BEGIN CERTIFICATE" in base64.b64decode(raw)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
