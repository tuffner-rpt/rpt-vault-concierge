# Vault Management Developer Portal

A Vercel-ready developer portal for provisioning HashiCorp Vault secrets from governed templates, with an OpenAI-powered recommendation agent.

## Run locally

```bash
cp .env.example .env.local
npm install
npm run dev
```

Without credentials, the portal runs safely in demo mode: provisioning returns metadata but does not persist generated secret values. Add `VAULT_ADDR` and `VAULT_TOKEN` to write secrets to a Vault KV v2 mount named `kv`. Add `OPENAI_API_KEY` to enable live agent recommendations through the OpenAI Responses API.

## Deploy to Vercel

1. Push this project to a Git provider and import it in the Vercel dashboard, or run `npx vercel` from this directory.
2. Keep the detected framework preset set to **Next.js**. No custom build or output settings are required.
3. Add the environment variables from `.env.example` in **Project Settings → Environment Variables**.
4. Deploy. Vercel will run `npm run build` and host the pages and API routes.

The app automatically uses Vercel's production deployment URL for social metadata.

For production, store `OPENAI_API_KEY` and `VAULT_TOKEN` as encrypted Vercel environment variables. Ensure `VAULT_ADDR` is reachable from Vercel's serverless network, restrict the token to the required KV paths, and prefer a short-lived Vault auth method over a static token.

## IBM Granite Vault onboarding

The catalog includes a separate **Onboard engines and secrets with IBM Granite**
entry at `/vault-onboarding`. It embeds the IBM watsonx Orchestrate chat from a
separately deployed onboarding bridge. The existing template and recommendation
flows remain available.

The complete IBM agent definition, Python tools, connection specification, secure
form, bridge and tests are in [integrations/ibm-vault](integrations/ibm-vault/README.md).
Deploy that directory as its own Vercel project or host it in the approved Vault
network. Do not deploy its Python routing configuration over this Next.js app.

Set this website's server-side `WXO_BRIDGE_URL` to the bridge's stable HTTPS origin
(no path). Set the bridge's `WEBSITE_ORIGIN` to this website's production origin.
The embed URL contains no credentials. When the setting is missing or invalid, the
page explicitly reports that IBM setup is pending and makes no IBM or Vault calls.

Agent scope: all available mountable engine types, including licensed Enterprise
and registered custom plugins; live-schema-based configuration, roles and secret
operations; lease tuning and disabling. KV v2 data writes remain CAS-protected.
Generic operations require the bridge's durable Redis REST approval store.
Review links open in a new tab for explicit approval and typed confirmation.
Tokens and values stay outside the chat. The new flow uses each caller's Vault
token; it does not use this website's existing shared `VAULT_TOKEN` setting.

IBM credentials, model availability and target Vault connectivity must be verified
before calling the new integration live. Follow the acceptance sequence in the
integration directory.
