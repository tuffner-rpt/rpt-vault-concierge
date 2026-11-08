import { NextResponse } from "next/server";
import { bridgeOrigin, chatHeaders } from "@/lib/watsonx-chat";

export async function POST(request: Request) {
  const protocol = process.env.VERCEL === "1" ? "https:" : new URL(request.url).protocol;
  if (request.headers.get("origin") !== `${protocol}//${request.headers.get("host")}`) return NextResponse.json({ error: "Same-origin request required" }, { status: 403, headers: chatHeaders });
  if (request.headers.get("content-type")?.split(";")[0] !== "application/json") return NextResponse.json({ error: "JSON required" }, { status: 415, headers: chatHeaders });
  try {
    const raw = await request.text();
    if (raw.length > 2048) return NextResponse.json({ error: "Request too large" }, { status: 413, headers: chatHeaders });
    const body = JSON.parse(raw);
    if (!body || Array.isArray(body) || Object.keys(body).length !== 3 ||
      typeof body.mount !== "string" || body.mount.length > 100 || !/^Onboard-[a-z0-9][a-z0-9_-]*$/.test(body.mount) ||
      typeof body.business_unit_id !== "string" || body.business_unit_id.length > 64 || !/^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(body.business_unit_id) ||
      typeof body.user_id !== "string" || body.user_id.length > 128 || !/^[A-Za-z0-9][A-Za-z0-9_.@-]*$/.test(body.user_id)) {
      return NextResponse.json({ error: "Check the mount name, Business Unit ID and UserID." }, { status: 422, headers: chatHeaders });
    }
    const key = process.env.KV_MOUNT_INTAKE_KEY;
    if (!key || key.length < 32) throw new Error("KV intake unavailable");
    const response = await fetch(`${bridgeOrigin()}/api/kv-mount-intake`, {
      method: "POST", headers: { "Content-Type": "application/json", "x-kv-mount-key": key },
      body: JSON.stringify(body), redirect: "error", cache: "no-store", signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) throw new Error("KV intake unavailable");
    const result = await response.json();
    const review = new URL(result.review_url);
    if (review.origin !== bridgeOrigin() || review.pathname !== "/onboard" || !/^#review=[A-Za-z0-9_-]{22}$/.test(review.hash)) throw new Error("Invalid review URL");
    return NextResponse.json({ review_url: review.href, status: result.status }, { headers: chatHeaders });
  } catch {
    return NextResponse.json({ error: "The request could not be confirmed. Check with your administrator before submitting again." }, { status: 503, headers: chatHeaders });
  }
}
