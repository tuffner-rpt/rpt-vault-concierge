"""Optional real Vault smoke test using an isolated, disposable local dev server."""
import os
import secrets
import shutil
import socket
import subprocess
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from api.index import app


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
                for engine in ["transit", "database", "pki"]:
                    result = execute(prepare(engine=engine, mount=f"onboard-{engine}"), root_token)
                    assert result.status_code == 200, result.text
                    assert result.json()["status"] == "created"
                    assert "separately" in result.json()["scope"]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
