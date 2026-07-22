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

Set `NEXT_PUBLIC_SITE_URL` to your custom production URL if you use one. Otherwise, the app automatically uses Vercel's production deployment URL for social metadata.

For production, store `OPENAI_API_KEY` and `VAULT_TOKEN` as encrypted Vercel environment variables. Ensure `VAULT_ADDR` is reachable from Vercel's serverless network, restrict the token to the required KV paths, and prefer a short-lived Vault auth method over a static token.
