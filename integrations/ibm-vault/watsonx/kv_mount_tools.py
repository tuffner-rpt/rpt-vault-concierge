"""The dedicated KV-mount agent has exactly one narrowly scoped tool."""
import json
from urllib.parse import urlsplit

import requests
from ibm_watsonx_orchestrate.agent_builder.tools import tool
from ibm_watsonx_orchestrate.agent_builder.connections import ConnectionType
from ibm_watsonx_orchestrate.run import connections


@tool(expected_credentials=[{"app_id": "rpt_vault_bridge", "type": ConnectionType.KEY_VALUE}])
def prepare_kv_mount_request(business_unit_id: str, mount: str, kv_version: str) -> str:
    """Prepare ONLY a new KV v1 or KV v2 mount for administrator review; never executes Vault operations.

    Args:
        business_unit_id: User-supplied Business Unit ID, 1-64 letters, digits, dots, underscores or hyphens. Not proof of identity or authorization.
        mount: Exact requested lowercase mount name, one segment starting with onboard-. Never silently rename it.
        kv_version: Exactly 1 for KV v1 or 2 for KV v2. Ask the user to choose; never assume.
    """
    creds = connections.key_value("rpt_vault_bridge")
    origin = creds["bridge_url"].rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        return json.dumps({"error": "Invalid bridge configuration"})
    if kv_version not in {"1", "2"}:
        return json.dumps({"error": "Choose KV v1 or KV v2"})
    try:
        response = requests.post(origin + "/api/kv-mount-plans", headers={"x-api-key": creds["api_key"]},
                                 json={"business_unit_id": business_unit_id, "mount": mount, "kv_version": kv_version},
                                 timeout=20, allow_redirects=False)
        if response.status_code >= 300:
            return json.dumps({"error": "Request not prepared. Check the Business Unit ID, an exact mount beginning onboard-, and KV version 1 or 2.", "status": response.status_code})
        return json.dumps(response.json())
    except (requests.RequestException, ValueError):
        return json.dumps({"error": "KV mount request service unavailable. No Vault change was made."})
