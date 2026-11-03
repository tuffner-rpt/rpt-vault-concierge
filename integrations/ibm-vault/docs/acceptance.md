# Verification and acceptance

Story: a visitor describes an onboarding request to IBM Granite in watsonx
Orchestrate, opens a signed review link, authorizes with their own Vault token,
and receives a receipt after Vault accepts the change.

## Local evidence

Run `.venv/bin/python -m pytest -q`. The automated suite checks:

- Plan preparation does not contact Vault.
- Mount prefixes, reserved/unsafe paths, engine compatibility and action schemas.
- Signed plan integrity, audience binding and ten-minute expiration.
- Same-origin submission, explicit confirmation and bounded request bodies.
- A caller token is sent only to the configured Vault host with the configured namespace.
- Engine creation, existing-engine no-op and incompatible-engine rejection.
- KV v2 creation uses `options.cas=0`; no secret read, update or delete API exists.
- Vault ACL denial and upstream errors do not cause writes or leak upstream data.
- Validation errors and receipts omit tokens and secret values.
- Chat identities are RS256-signed, five minutes long, anonymous and have no Vault authority.

`tests/test_bridge.py` simulates Vault responses with HTTPX MockTransport.
`tests/test_local_vault.py` additionally starts an isolated real Vault dev server
on an ephemeral loopback port and shuts it down afterward. It was verified with
Vault v2.1.2 and checks KV v2, transit, database and PKI mount creation, compatible
mount no-op, scoped-user secret creation, atomic overwrite refusal, and ACL denial.
Only disposable test values are used, with root and caller tokens generated in
memory. Vault startup output is suppressed, and token-file storage is disabled.
The test skips if the `vault` executable is unavailable.

`python scripts/validate-agent.py` validates the agent, three Python tool schemas
and draft/live connection configurations using the installed IBM ADK (verified
with 2.19.1). It does not contact IBM or verify tenant model availability.

The local browser check verified plan rendering, URL-fragment removal, and adding
and removing secret fields. [Form preview](onboarding-preview.jpg).
These checks do not establish the user's target Vault connectivity or successful
IBM inference.

## Live acceptance after provisioning

1. Confirm the intended IBM Granite model is available in the target tenant using
   `orchestrate models list`. Set `llm` in `watsonx/agent.yaml` to its exact ID.
2. Connect the bridge and import the tools and agent. Configure both draft and
   live connection credentials; deploy the agent to Live.
3. Register the embed signing public key in Orchestrate and confirm a visitor can
   load `/chat`, get a response from Granite, call the catalog tool, and refresh
   chat authentication after five minutes without losing their anonymous identity.
4. Ask: “Enable a KV v2 engine at onboard-payments for development.” Confirm
   the returned link opens `/onboard` in a **new tab**, outside the chat iframe.
5. Verify the displayed Vault address and namespace before entering a scoped
   test token. Unchecked confirmation must prevent submission. Check and submit;
   verify the new mount independently in the Vault UI or CLI.
6. Ask: “Create a secret in onboard-payments at dev/database.” Enter test values
   only in the review form. Verify creation independently using a separate
   authorized Vault account. The form receipt must not contain the values.
7. Retry creation at the same secret path. It must fail without changing the
   existing version. Replaying a mount plan must be a no-op for a compatible mount.
8. Repeat with a token that lacks the needed ACLs; expect refusal. Try an expired
   plan, a modified plan, and a path outside the allowed prefix; expect refusal.
9. Confirm the original website embeds the chat, displays the no-secrets notice,
   works on mobile and supports keyboard navigation and readable errors.

Database, transit and PKI acceptance covers **mount enablement only**. Configuring
database connections/roles, transit keys or certificate authorities requires a
separate implementation and acceptance plan.
