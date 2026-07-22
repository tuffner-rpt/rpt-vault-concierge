import { NextResponse } from "next/server";

const systemPrompt = `You are a concise Vault platform agent. Recommend one of: API key, database credential, cloud access, or TLS certificate. State the recommended type, environment safeguards, rotation period, and why. Never request or reveal a secret value. Keep the response under 90 words.`;

export async function POST(request: Request) {
  const { prompt } = await request.json();
  if (!String(prompt || "").trim()) return NextResponse.json({ error: "Prompt required" }, { status: 400 });
  const apiKey = process.env.OPENAI_API_KEY;
  const model = process.env.OPENAI_MODEL || "gpt-5.6-terra";

  if (!apiKey) {
    const lower = String(prompt).toLowerCase();
    const type = lower.includes("database") || lower.includes("postgres") ? "Database credential" : lower.includes("certificate") || lower.includes("tls") ? "TLS certificate" : lower.includes("cloud") || lower.includes("gcp") ? "Cloud access" : "API key";
    return NextResponse.json({ message: `Recommendation: ${type}\n\nUse the shortest practical lease, bind access to the workload identity, and require automatic rotation. Start in development, then promote the same policy to production after validation. OpenAI is in demo mode until OPENAI_API_KEY is configured.` });
  }

  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model,
      instructions: systemPrompt,
      input: String(prompt),
      reasoning: { effort: "none" },
      max_output_tokens: 180,
      store: false,
    }),
  });
  if (!response.ok) return NextResponse.json({ error: "OpenAI request failed" }, { status: 502 });
  const data = await response.json();
  const message = data?.output
    ?.flatMap((item: { type?: string; content?: Array<{ type?: string; text?: string }> }) => item.type === "message" ? item.content || [] : [])
    .filter((part: { type?: string }) => part.type === "output_text")
    .map((part: { text?: string }) => part.text || "")
    .join("")
    .trim();
  return NextResponse.json({ message: message || "No recommendation returned." });
}
