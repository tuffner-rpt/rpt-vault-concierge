export const dynamic = "force-dynamic";

export function GET(request: Request) {
  const workflow = new URL(request.url).searchParams.get("workflow");
  if (workflow !== null && workflow !== "kv-mount") return new Response("Unknown onboarding workflow", { status: 400 });
  const notice = workflow === "kv-mount"
    ? "KV mount onboarding only. Enter Vault tokens only in the separate secure review form."
    : "Describe your request here. Enter Vault tokens and secret values only in the separate secure review form.";
  return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RPT Vault Concierge</title><link rel="stylesheet" href="/watsonx-chat.css"><script src="/watsonx-chat.js" defer></script></head><body><main class="chat-shell"><p class="chat-notice">${notice}</p><p id="chat-status" role="status">Connecting to watsonx Orchestrate…</p><div id="root"></div></main></body></html>`, {
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Content-Security-Policy": "frame-ancestors 'self'; base-uri 'self'; object-src 'none'", "Permissions-Policy": "camera=(), microphone=(), geolocation=()" },
  });
}
