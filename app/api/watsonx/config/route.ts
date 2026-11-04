import { NextResponse } from "next/server";
import { bridgeChat, bridgeOrigin, chatHeaders } from "@/lib/watsonx-chat";

export async function GET() {
  try {
    const config = await bridgeChat("/api/chat-config");
    return NextResponse.json({ ...config, reviewOrigin: bridgeOrigin() }, { headers: chatHeaders });
  } catch {
    return NextResponse.json({ error: "The IBM chat connection is unavailable. Please try again." }, { status: 503, headers: chatHeaders });
  }
}
