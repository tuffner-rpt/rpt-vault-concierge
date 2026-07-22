import { randomBytes } from "node:crypto";
import { NextResponse } from "next/server";

const templates: Record<string, { lease: string; length: number }> = {
  "api-key": { lease: "90 days", length: 32 },
  database: { lease: "24 hours", length: 24 },
  cloud: { lease: "8 hours", length: 36 },
  certificate: { lease: "30 days", length: 48 },
};

function safeSegment(value: unknown, fallback = "") {
  return String(value || fallback).toLowerCase().trim().replace(/[^a-z0-9-]+/g, "-").replace(/^-|-$/g, "");
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const template = templates[body.templateId];
    const name = safeSegment(body.name);
    const environment = safeSegment(body.environment, "development");
    const team = safeSegment(body.team, "platform");
    if (!template || !name) return NextResponse.json({ error: "A valid template and secret name are required." }, { status: 400 });

    const path = `kv/${team}/${environment}/${name}`;
    const value = randomBytes(template.length).toString("base64url");
    const vaultAddress = process.env.VAULT_ADDR?.replace(/\/$/, "");
    const vaultToken = process.env.VAULT_TOKEN;
    let mode = "demo";

    if (vaultAddress && vaultToken) {
      const response = await fetch(`${vaultAddress}/v1/kv/data/${team}/${environment}/${name}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Vault-Token": vaultToken, ...(process.env.VAULT_NAMESPACE ? { "X-Vault-Namespace": process.env.VAULT_NAMESPACE } : {}) },
        body: JSON.stringify({ data: { value, type: body.templateId, owner: team, environment, description: String(body.description || ""), managed_by: "vault-developer-portal" } }),
      });
      if (!response.ok) throw new Error(`Vault rejected the request (${response.status}).`);
      mode = "vault";
    }

    return NextResponse.json({ path, lease: template.lease, status: "active", mode });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Provisioning failed." }, { status: 500 });
  }
}
