# All-engine management and the configured IBM instance

The IBM ADK environment `rpt-vault-updated` is registered for:

`https://api.dl.watson-orchestrate.ibm.com/instances/20261104-0014-2170-40e0-623668130968`

This is the **API service URL**, not the embedded chat's `hostURL`. The agent and all five tools are deployed,
and MCSP v2 authentication plus signed embedded chat have been verified. Target
Vault execution still requires the caller's scoped token in the review form.

## Authenticate without putting a key in chat or shell history

From this package directory, with the IBM ADK environment activated:

```sh
orchestrate env activate rpt-vault-updated
```

The ADK prompts for the API key using a hidden password prompt. Obtain it from
your Orchestrate instance's Settings → API details. Do not pass the key as a CLI
argument or paste it into a chatbot. Then run `orchestrate models list`, choose an
available IBM Granite chat model, and follow the import/deploy steps in the README.
On another computer, register the environment first:

```sh
orchestrate env add --name rpt-vault-updated --url https://api.dl.watson-orchestrate.ibm.com/instances/20261104-0014-2170-40e0-623668130968
```

## Available engine types

There is no four-engine allowlist. The planner accepts any safe registered secrets
plugin name. Examples include KV v1/v2, AWS, Azure, GCP, GCP KMS, AliCloud, Consul,
Database, Kubernetes, LDAP/OpenLDAP, MongoDB Atlas, Nomad, PKI, RabbitMQ, SSH,
Terraform, TOTP and Transit, plus licensed Enterprise engines such as Transform,
KMIP and Key Management. A name's presence in these examples is not proof that it
is installed, licensed, supported by this Vault release, or permitted for a caller.

The secure form can inspect `GET /sys/plugins/catalog`. Vault's mount API performs
the authoritative availability, deprecation, license and permission checks when
enabling an engine. Database driver plugins are configured within a `database`
mount; they are not separate secret-engine mount types. Custom plugin binaries
must already be registered by administrators.

Vault-owned System, Identity and Cubbyhole are special existing mounts and cannot
be manually enabled through this integration. Auth methods remain separate. The
allowed mount prefix remains `onboard-`; “all types” does not change path ACLs or
give the chatbot an administrator token.

## Operations

| Tool | Purpose |
| --- | --- |
| `vault_onboarding_catalog` | Scope and example engine families; no Vault token |
| `prepare_vault_engine` | Enable any available mountable secrets engine |
| `prepare_vault_secret` | Create KV v2 data with atomic `cas=0` |
| `prepare_vault_operation` | Configuration, roles, key/secret operations, issuance, rotation, reads, listing, revocation and deletion, where published by that mount's schema |
| `prepare_vault_mount_change` | Lease-default/description tuning or disabling an engine |

The agent prepares an exact mount, relative endpoint and HTTP method. It never
collects credential values or request JSON. In the secure form, the user inspects
the live engine schema, supplies their own scoped Vault token and request JSON,
and reviews the exact operation. The bridge checks mount type/version, matches
the endpoint and method against `GET /<mount>?help=1`, resolves only local schema
references, and validates JSON input before executing.

Mutating engine operations require typing `EXECUTE <METHOD> <mount>/<endpoint>`.
DELETE requires `DELETE <mount>/<endpoint>`; disabling requires `DISABLE <mount>`.
Disabling removes engine data and revokes associated leases. These are execution
controls for product users; the builder has not disabled any real target mounts.

KV v2 data writes cannot use the generic tool, including through the `kv` alias;
they must use create-only CAS. Other explicitly approved engine APIs can mutate,
rotate or delete existing objects. This is broader management than the initial
create-only package and must be reflected in each caller's ACLs.

## One-use approval storage

Configure `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` on the bridge
using a durable Upstash Redis database or a compatible Redis REST service. These
server-side values never belong in the browser or IBM tool connection. Provision
the database through your approved hosting account; this repository does not
provision a paid service automatically.

Before generic engine operations (including GET/LIST, which may issue credentials),
tuning or disabling, the bridge atomically claims the signed ticket using
`SET <ticket-hash> used EX 900 NX`. If the store is missing/unavailable, it refuses
the operation. Only a hash and used marker are stored; no tokens, payloads or
secret values are persisted. Failed/uncertain requests remain consumed. Verify
the actual Vault state before preparing another plan; there are no automatic retries.

## Sensitive outputs and limitations

Credentials, plaintext, private keys, lease information and engine output return
only to the secure form. A separate collapsed result area reveals them on demand
and offers a clear button. Outputs never go to the agent or chat transcript.
PEM/text/binary responses are represented as base64 plus their content type.

The generic form is intended for an operator who can review the engine's API
schema. It does not invent cloud credentials, install plugins, obtain licenses,
configure networking, or guarantee every provider operation succeeds. Engines
without a usable OpenAPI document fail closed. GET/LIST/DELETE payloads must be
empty; query-parameter workflows and non-JSON request uploads are not implemented.
Vault's own ACL and engine/provider checks are always authoritative.

References: [Vault plugin catalog](https://developer.hashicorp.com/vault/api-docs/system/plugins-catalog),
[Vault mounts API](https://developer.hashicorp.com/vault/api-docs/system/mounts),
[IBM environment credentials](https://developer.watson-orchestrate.ibm.com/environment/production_import).

The `kv` alias selects KV v2; use `kv-v1` explicitly for version 1. Relative API
paths support safe ASCII names (including dots, at signs and tildes); URL/query
syntax, percent encoding, empty segments and dot traversal segments are rejected.

[Engine management form preview](engine-management-preview.jpg).
[Redis REST protocol reference](https://upstash.com/docs/redis/features/restapi).
