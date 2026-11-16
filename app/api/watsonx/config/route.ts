import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({ error: "Chat has been removed. Use the Vault onboarding tiles." }, { status: 410, headers: { "Cache-Control": "no-store" } });
}
