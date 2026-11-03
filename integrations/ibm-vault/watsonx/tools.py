"""Import these five standalone Python tools using the Orchestrate ADK."""
import json
from urllib.parse import urlsplit

import requests
from ibm_watsonx_orchestrate.agent_builder.tools import tool
from ibm_watsonx_orchestrate.agent_builder.connections import ConnectionType
from ibm_watsonx_orchestrate.run import connections

APP_ID = "rpt_vault_bridge"
CREDS = [{"app_id": APP_ID, "type": ConnectionType.KEY_VALUE}]


def _call(method: str, path: str, payload=None) -> str:
    creds = connections.key_value(APP_ID)
    origin = creds["bridge_url"].rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        return json.dumps({"error": "The bridge connection requires an HTTPS origin"})
    try:
        response = requests.request(method, origin + path, headers={"x-api-key": creds["api_key"]}, json=payload, timeout=20, allow_redirects=False)
        if response.status_code >= 300:
            return json.dumps({"error": "The bridge could not prepare the request. Verify the allowed mount prefix, path, connection and server configuration.", "status": response.status_code})
        return json.dumps(response.json())
    except (requests.RequestException, ValueError):
        return json.dumps({"error": "The onboarding bridge is unavailable. No Vault change was made."})


@tool(expected_credentials=CREDS)
def vault_onboarding_catalog() -> str:
    """Get allowed engine types, mount prefix and onboarding limitations. Does not connect to Vault."""
    return _call("GET", "/api/catalog")


@tool(expected_credentials=CREDS)
def prepare_vault_engine(engine: str, mount: str, description: str) -> str:
    """Prepare an engine mount review link without changing Vault.

    Args:
        engine: Mountable Vault secrets engine or registered secrets plugin name. Use kv-v1 or kv-v2 for KV version selection.
        mount: Single mount segment using the prefix returned by the catalog.
        description: Non-secret purpose of the mount, at most 240 characters.

    Returns:
        A pending plan and secure review URL; this does not indicate engine creation.
    """
    return _call("POST", "/api/plans", {"action": "enable_engine", "engine": engine, "mount": mount, "description": description})


@tool(expected_credentials=CREDS)
def prepare_vault_secret(mount: str, secret_path: str) -> str:
    """Prepare a create-only KV v2 secret review link. Never accepts secret values.

    Args:
        mount: Existing KV v2 mount using the prefix returned by the catalog.
        secret_path: Relative secret path such as payments/dev/database.

    Returns:
        A pending plan and secure form URL for entering values outside chat.
    """
    return _call("POST", "/api/plans", {"action": "create_secret", "engine": "kv-v2", "mount": mount, "secret_path": secret_path})


@tool(expected_credentials=CREDS)
def prepare_vault_operation(engine: str, mount: str, method: str, endpoint: str, purpose: str) -> str:
    """Prepare a reviewed operation for any mounted secrets engine; never accepts credential values.

    Args:
        engine: Secrets engine or registered plugin type, e.g. aws, database, transit, pki, kv-v1.
        mount: Existing mount using the catalog's allowed prefix.
        method: GET, LIST, POST, PUT, PATCH, or DELETE from the engine's documented API.
        endpoint: Relative engine endpoint, e.g. config/root, roles/payments, keys/payments, creds/developer. Never include a URL, mount prefix, query, or credentials.
        purpose: Non-secret explanation of the requested operation and its consequences.

    Returns:
        A secure review URL. The form validates the endpoint and input against Vault's live OpenAPI schema. Credentials, request JSON and outputs stay outside chat.
    """
    return _call("POST", "/api/plans", {"action": "engine_operation", "engine": engine, "mount": mount, "method": method, "endpoint": endpoint, "description": purpose})


@tool(expected_credentials=CREDS)
def prepare_vault_mount_change(engine: str, mount: str, action: str, purpose: str) -> str:
    """Prepare reviewed lease tuning or destructive disabling of any compatible engine mount.

    Args:
        engine: Existing secrets engine or registered plugin type.
        mount: Existing mount using the catalog's allowed prefix.
        action: tune_engine for lease defaults and description, or disable_engine to revoke leases and remove all mount data.
        purpose: User's non-secret reason; explicitly explain any data loss or credential revocation.

    Returns:
        A review URL. Execution requires the caller's Vault token, durable one-use approval, and typed confirmation for disabling.
    """
    return _call("POST", "/api/plans", {"action": action, "engine": engine, "mount": mount, "description": purpose})
