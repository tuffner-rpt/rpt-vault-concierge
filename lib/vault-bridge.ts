import "server-only";

export function bridgeOrigin(): string {
  const url = new URL(process.env.WXO_BRIDGE_URL || "");
  if (url.protocol !== "https:" || url.username || url.password || url.pathname !== "/" || url.search || url.hash) throw new Error("Invalid IBM bridge origin");
  return url.origin;
}

// Server-to-server access only. Never send this credential to a browser or URL.
export function bridgeServiceHeaders(): Record<string, string> {
  const secret = process.env.VAULT_BRIDGE_PROTECTION_BYPASS;
  if (!secret && process.env.VERCEL === "1") throw new Error("Vault bridge service access is not configured");
  return secret ? { "x-vercel-protection-bypass": secret } : {};
}

export const chatHeaders = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
