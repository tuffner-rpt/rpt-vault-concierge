# RPT Vault Concierge — IBM Granite + watsonx Orchestrate

This repository contains an Orchestrate native agent, five IBM ADK Python tools,
a Vercel-compatible FastAPI bridge, and an embeddable IBM chat page. It is designed
to connect to the existing `rpt-vault-concierge-demo` website without replacing it.

**Current status:** implementation and local automated verification are available.
IBM ADK 2.19.1 validates the agent, tools and connection schemas. An isolated local
Vault v2.1.2 test verifies all locally supported mountable plugins, scoped writes,
transit cryptography and rotation, lease tuning, engine disable, replay refusal and ACLs. The user's IBM tenant, actual Granite model availability, target
Vault connectivity, and deployment to the supplied website have not been verified.
The parent Next.js website includes `/vault-onboarding` for embedding this bridge.
The target IBM instance is recorded in `watsonx/instance.json`; authentication and
live deployment remain pending. Configure the website's `WXO_BRIDGE_URL` after
successfully deploying and accepting the bridge and IBM agent.

## Behavior

1. A user describes the engine or secret they need in the IBM chat widget.
2. Granite calls a tool to prepare a signed plan; no Vault operation runs yet.
3. The user opens the review link in a new tab and reviews the fixed Vault host,
   namespace, operation and path.
4. The user supplies their own short-lived scoped Vault token and, for secrets,
   values in the separate form, then explicitly confirms.
5. The server executes against Vault using that caller token and returns a receipt
   containing paths and status. Engine-specific sensitive results are revealed only
   in a separate secure-form area; they never enter chat. The application does not
   persist tokens, payloads or secret values. Input fields clear after submission.

The Orchestrate identity is an anonymous planner identity, **not** Vault authority.
The only shared tool credential can prepare plans; it cannot execute them. The
backend has no administrator Vault token. Plan links contain metadata, expire in
10 minutes, and are held in a URL fragment that is removed on page load. Do not
put confidential data in descriptions or path names; those remain in chat history.

| Capability | Implemented scope |
| --- | --- |
| Engine types | Any available mountable secrets plugin; built-in, Enterprise and registered custom plugins |
| KV v2 data writes | Atomic create-only CAS; generic API cannot bypass this |
| Engine-specific APIs | Configuration, roles, cryptography, issuance, credentials, reads, listing, rotation, revocation and deletion when published in the live mount schema |
| Mount lifecycle | Enable, compatible-mount no-op, lease defaults/description tuning and disable |
| Approval | Exact method/path review; typed mutation/destruction confirmation; caller ACLs |
| Replay prevention | Atomic Redis one-use claim for generic operations, tuning and disabling |

The default allowed mount prefix remains `onboard-`. All engine types does not
imply access to all paths or an administrator identity. Vault-managed System,
Identity and Cubbyhole are special existing mounts, not manually enabled plugins.
Enterprise/custom availability depends on the installation and license.

Read [all-engine management](docs/all-engines.md) for exact scope, limitations and
single-use storage setup. New generic operations require a durable Redis REST
store (`UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`); they fail closed
without it. Engine schemas and actual Vault ACLs remain authoritative. The simple
compatible-engine and CAS-protected creation flows remain safely repeatable.

## Run locally

Use Python 3.12 or later. IBM ADK 2.19.1 supports Python 3.11–3.14.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
```

Set `APP_ORIGIN=http://127.0.0.1:8000`, the intended `VAULT_ADDR`, namespace and
two independent random 32-byte or longer keys in `.env`. Generate each value with
`openssl rand -hex 32`. Keep `.env` out of source control. Local loopback HTTP is
allowed for development; production origins require HTTPS. Vault must have a
trusted TLS certificate; verification is always enabled, redirects are disabled.

```sh
.venv/bin/uvicorn api.index:app --env-file .env --host 127.0.0.1 --port 8000
.venv/bin/python -m pytest -q
```

`/` and `/onboard` display the secure form. A signed review link comes from the
agent's preparation tools. `/chat` displays an explicit setup error until its IBM
configuration is provided. `/api/health` is application liveness only; it does not
contact Vault and must not be treated as an integration health check.

## Configure IBM watsonx Orchestrate

Use a separate ADK environment if preferred; IBM ADK is not a bridge runtime
dependency. Never place an IBM API key, private signing key or Vault token in HTML.

```sh
pip install ibm-watsonx-orchestrate==2.19.1
python scripts/validate-agent.py
orchestrate env add --name rpt-vault --url https://api.us-south.watson-orchestrate.cloud.ibm.com/instances/49049ef8-a58a-4d39-b778-23fb47342d35
orchestrate env activate rpt-vault
orchestrate models list
```

Follow the CLI's secure authentication prompt. The agent uses
`watsonx/ibm/granite-4-h-small`, verified in the target instance's full model catalog
on November 3, 2026 (`orchestrate models list -a`).
Do not silently substitute another model family. No separate inference provider
is used: Orchestrate runs the configured Granite model.

The target instance currently returns malformed native tool-call arguments for
Granite 4 H Small with `react_core`. Live catalog and review-link smoke tests use
`style: react`, IBM's prompt-based tool calling. IBM marks this style deprecated;
retest `react_core` after an IBM runtime/model update before migrating.


Create the connection first:

```sh
orchestrate connections import -f watsonx/connection.yaml
```

In Orchestrate **Manage → Connections**, set these two key/value credentials in
**both draft and live** for `rpt_vault_bridge`:

| Credential | Value |
| --- | --- |
| `bridge_url` | Stable HTTPS origin of the bridge, no trailing slash or path |
| `api_key` | Same secret value as server-side `WXO_BRIDGE_API_KEY` |

Use the UI to avoid putting secrets into shell history. For Developer Edition,
use the CLI credential mechanism documented by IBM. Tools read the connection
through `connections.key_value()`, never process environment variables.

```sh
bash scripts/import-agent.sh
```

Test the agent in draft, then deploy:

```sh
orchestrate agents deploy --name rpt_vault_concierge
orchestrate channels webchat embed --agent-name rpt_vault_concierge
```

Copy the returned public identifiers into the bridge's `WXO_HOST_URL`,
`WXO_ORCHESTRATION_ID`, `WXO_AGENT_ID`, `WXO_AGENT_ENVIRONMENT_ID`, and, for IBM
Cloud, `WXO_DEPLOYMENT_PLATFORM=ibmcloud` and `WXO_CRN`.

### Secure embedded chat

Generate an RSA signing pair outside the repository:

```sh
openssl genrsa -out /secure/location/rpt-wxo-private.pem 3072
openssl rsa -in /secure/location/rpt-wxo-private.pem -pubout -out /secure/location/rpt-wxo-public.pem
```

Register the public key in the agent's embedded-chat security configuration for
the target environment. Set the private PEM content as `WXO_CHAT_PRIVATE_KEY` in
the bridge server's secret environment configuration. The server issues five-minute
RS256 identity tokens; the widget refreshes them through `authTokenNeeded`.
This implementation includes only `sub`, `iat` and `exp` claims and does not send
SSO or sensitive identity payloads. If the tenant requires encrypted user payloads,
implement that tenant's identity integration before release. Do not disable IBM's
embed security to work around an error.

Anonymous chat is intentional: it can prepare plans but cannot authorize Vault
changes. If the site should restrict who may chat, gate `/chat`, `/api/chat-config`
and `/api/chat-token` with the existing website's verified login/session. Do not
trust a browser-provided role or user ID. Apply platform rate limits to public
chat endpoints according to expected usage before broadly exposing them.

## Deploy and embed on the existing website

Deploy this bridge as its own Vercel project using `vercel.json`, Python 3.12 and
`requirements.txt`; set the environment variables from `.env.example` through
Vercel's environment settings. Use a stable production origin for `APP_ORIGIN` and
the Orchestrate connection, rather than a one-off preview URL. Deploying this
repository over the existing website would replace that website; keep them separate.

Ensure the bridge can reach Vault. A private Vault network may require an
approved network path or hosting the bridge inside that network instead.

Set `WEBSITE_ORIGIN` to the exact website origin and paste the iframe from
[docs/embed.html](docs/embed.html) into its chatbot area. Replace the bridge origin.
If the original website has CSP, allow the bridge origin in `frame-src`. The review
form deliberately rejects framing and must open in a new tab; verify IBM's link
handling for your tenant during acceptance. The chat page allows only itself and
the configured website as frame parents. Its anonymous session continuity also
works without third-party cookies during a page session.

If Vercel Deployment Protection guards the bridge, IBM's Python tool runtime must
have an approved access route to it. Do not embed a deployment bypass secret in
browser code. The browser and server-side IBM tools both need to reach the bridge;
test those paths independently. Preserve the original site's access protections.

Do not attach analytics or chat scripts to the secure secret-entry page. It uses
a restrictive CSP and has no third-party scripts. Review hosting/request-capture
settings so request bodies containing credentials are not recorded.

## Verification and sources

See [acceptance checks](docs/acceptance.md) for local evidence and the live test
sequence. The unit tests use simulated Vault responses; the optional local Vault
test starts and stops a real isolated dev server with disposable in-memory data.
Successful real IBM
import, Granite inference, webchat security, deployment, and Vault writes still
require the target environments and live acceptance.

Implementation references:

- [IBM native agent specifications](https://developer.watson-orchestrate.ibm.com/agents/build_agent)
- [IBM Python tool connections](https://developer.watson-orchestrate.ibm.com/connections/associate_connection_to_tool/python_connections)
- [IBM secure embedded chat setup](https://developer.watson-orchestrate.ibm.com/webchat/get_started)
- [IBM webchat events](https://developer.watson-orchestrate.ibm.com/webchat/events)
- [Vault mounts API](https://developer.hashicorp.com/vault/api-docs/system/mounts)
- [Vault KV v2 API and CAS](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2)
- [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python)
