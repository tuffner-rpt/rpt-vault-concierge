"""Import these three standalone Python tools using the Orchestrate ADK."""
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
        engine: One of kv-v2, transit, database, pki. Non-KV engines are mount-only.
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
