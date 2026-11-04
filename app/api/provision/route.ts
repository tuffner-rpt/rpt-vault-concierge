import { NextResponse } from "next/server";

// All current-site provisioning requests must pass through the administrator queue.
export async function POST() {
  return NextResponse.json({ error: "Administrator review is required. Prepare your request in IBM Granite chat.", reviewUrl: "/vault-onboarding" }, { status: 409 });
}
