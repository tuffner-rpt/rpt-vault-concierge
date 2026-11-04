import "server-only";

export function bridgeOrigin(): string {
  const url = new URL(process.env.WXO_BRIDGE_URL || "");
  if (url.protocol !== "https:" || url.username || url.password || url.pathname !== "/" || url.search || url.hash) throw new Error("Invalid IBM bridge origin");
  return url.origin;
}

export async function bridgeChat(path: "/api/chat-config" | "/api/chat-token", body?: { chat_session: string | null }) {
  const origin = bridgeOrigin();
  const response = await fetch(`${origin}${path}`, {
    method: body ? "POST" : "GET",
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(15_000),
    ...(body ? { headers: { "Content-Type": "application/json", Origin: origin }, body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) throw new Error("IBM bridge unavailable");
  return response.json();
}

export const chatHeaders = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
