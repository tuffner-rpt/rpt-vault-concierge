import { NextResponse } from "next/server";
import { bridgeChat, bridgeOrigin, chatHeaders } from "@/lib/watsonx-chat";

export async function GET(request: Request) {
  const workflow = new URL(request.url).searchParams.get("workflow");
  if (workflow !== null && workflow !== "kv-mount") return NextResponse.json({ error: "Unknown onboarding workflow" }, { status: 400, headers: chatHeaders });
  try {
    const config = await bridgeChat(workflow === "kv-mount" ? "/api/kv-mount-chat-config" : "/api/chat-config");
    return NextResponse.json({ ...config, reviewOrigin: bridgeOrigin() }, { headers: chatHeaders });
  } catch {
    return NextResponse.json({ error: "The IBM chat connection is unavailable. Please try again." }, { status: 503, headers: chatHeaders });
  }
}
