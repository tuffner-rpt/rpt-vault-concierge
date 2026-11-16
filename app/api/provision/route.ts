import { NextResponse } from "next/server";

// All current-site provisioning requests must pass through the administrator queue.
export async function POST() {
  return NextResponse.json({ error: "Use the Create, Update, or List KV Secret tiles in the catalog.", reviewUrl: "/" }, { status: 409 });
}
