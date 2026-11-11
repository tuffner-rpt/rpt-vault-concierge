import { NextResponse } from "next/server";
import { bridgeOrigin, chatHeaders } from "@/lib/watsonx-chat";

export async function POST(request: Request) {
  const protocol = process.env.VERCEL === "1" ? "https:" : new URL(request.url).protocol;
  if (request.headers.get("origin") !== `${protocol}//${request.headers.get("host")}`) return NextResponse.json({ error: "Same-origin request required" }, { status: 403, headers: chatHeaders });
  if (request.headers.get("content-type")?.split(";")[0] !== "application/json") return NextResponse.json({ error: "JSON required" }, { status: 415, headers: chatHeaders });
  try {
    const raw = await request.text();
    if (raw.length > 8192) return NextResponse.json({ error: "Request too large" }, { status: 413, headers: chatHeaders });
    const body = JSON.parse(raw);
    if (!body || Array.isArray(body) || Object.keys(body).some(key => !["vault_token", "prefix"].includes(key)) ||
        typeof body.vault_token !== "string" || body.vault_token.length < 1 || body.vault_token.length > 4096 || !/^[A-Za-z0-9._-]+$/.test(body.vault_token) ||
        (body.prefix !== undefined && (typeof body.prefix !== "string" || body.prefix.length > 300 || (body.prefix !== "" && (!/^[A-Za-z0-9_.@~/-]+$/.test(body.prefix) || body.prefix.split("/").some((part: string) => !part || part === "." || part === "..")))))) {
      return NextResponse.json({ error: "Check the scoped Vault token and folder path." }, { status: 422, headers: chatHeaders });
    }
    const key = process.env.KV_SECRET_LIST_KEY;
    if (!key || key.length < 32) throw new Error("Listing unavailable");
    const response = await fetch(`${bridgeOrigin()}/api/kv-secret-list`, {
      method: "POST", headers: { "Content-Type": "application/json", "x-kv-list-key": key },
      body: JSON.stringify({ vault_token: body.vault_token, prefix: body.prefix ?? "" }),
      redirect: "error", cache: "no-store", signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) return NextResponse.json({ error: response.status === 403 ? "Your Vault token needs list permission for this folder under onboard-concierge/metadata/." : "Could not list keys. Check the token, folder and Vault connection." }, { status: response.status === 403 ? 403 : 503, headers: chatHeaders });
    const result = await response.json();
    if (result.namespace !== "admin" || result.mount !== "onboard-concierge" || result.prefix !== (body.prefix ?? "") || !Array.isArray(result.keys) || result.keys.some((value: unknown) => typeof value !== "string")) throw new Error("Invalid listing target");
    return NextResponse.json({ namespace: "admin", mount: "onboard-concierge", prefix: result.prefix, keys: result.keys }, { headers: chatHeaders });
  } catch {
    return NextResponse.json({ error: "The key listing is unavailable. Please try again." }, { status: 503, headers: chatHeaders });
  }
}
