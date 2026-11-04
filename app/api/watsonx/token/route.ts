import { NextResponse } from "next/server";
import { bridgeChat, chatHeaders } from "@/lib/watsonx-chat";

export async function POST(request: Request) {
  // This endpoint issues anonymous chat identity only. It forwards no browser
  // cookies, Vault tokens, admin sessions or shared service credentials.
  const protocol = process.env.VERCEL === "1" ? "https:" : new URL(request.url).protocol;
  const expectedOrigin = `${protocol}//${request.headers.get("host")}`;
  if (request.headers.get("origin") !== expectedOrigin) return NextResponse.json({ error: "Same-origin request required" }, { status: 403, headers: chatHeaders });
  if (request.headers.get("content-type")?.split(";")[0] !== "application/json") return NextResponse.json({ error: "JSON required" }, { status: 415, headers: chatHeaders });
  try {
    const raw = await request.text();
    if (raw.length > 1024) return NextResponse.json({ error: "Request too large" }, { status: 413, headers: chatHeaders });
    const body = JSON.parse(raw);
    if (!body || typeof body !== "object" || Array.isArray(body) || Object.keys(body).some(key => key !== "chat_session") || (body.chat_session != null && (typeof body.chat_session !== "string" || body.chat_session.length > 200))) return NextResponse.json({ error: "Invalid chat session" }, { status: 422, headers: chatHeaders });
    const data = await bridgeChat("/api/chat-token", { chat_session: body.chat_session ?? null });
    return NextResponse.json({ token: data.token, chat_session: data.chat_session }, { headers: chatHeaders });
  } catch {
    return NextResponse.json({ error: "The IBM chat identity service is unavailable. Please try again." }, { status: 503, headers: chatHeaders });
  }
}
