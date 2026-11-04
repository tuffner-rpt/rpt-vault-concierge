import Link from "next/link";
import { AdminReviewLink } from "../components/AdminReviewLink";

export const dynamic = "force-dynamic";

function chatUrl(): string | null {
  const value = process.env.WXO_BRIDGE_URL;
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || url.pathname !== "/") return null;
    return `${url.origin}/chat`;
  } catch {
    return null;
  }
}

export default function VaultOnboarding() {
  const url = chatUrl();
  return (
    <main className="app-shell">
      <header className="topbar onboarding-topbar">
        <Link className="brand" href="/" aria-label="RPT Vault Developer Concierge home">
          <span className="brand-mark"><img src="/rpt-gcp.jpeg" alt="" /></span>
          <span>RPT Vault <strong>Developer Concierge</strong></span>
        </Link>
        <Link className="onboarding-back" href="/">← Back to catalog</Link>
      </header>
      <div className="workspace onboarding-layout">
        <aside className="sidebar"><div className="side-label">WORKSPACE</div><Link className="side-item" href="/">⌂ &nbsp; Secret catalog</Link><Link className="side-item active" href="/vault-onboarding">✦ &nbsp; IBM Granite chat</Link><AdminReviewLink /></aside>
      <section className="onboarding-workspace" aria-labelledby="onboarding-title">
        <div className="panel-kicker">IBM WATSONX ORCHESTRATE · GRANITE</div>
        <h1 id="onboarding-title">Onboard with a conversation.</h1>
        <p className="onboarding-intro">Manage available Vault secrets engines, configuration, roles, and secret operations through IBM Granite. Review each operation and approve it using your own Vault permissions.</p>
        <div className="onboarding-scope" aria-label="Supported onboarding operations">
          <span><strong>All available engine types</strong>Built-in, licensed Enterprise + custom plugins</span>
          <span><strong>Engine-specific operations</strong>Configuration, roles, credentials + lifecycle</span>
          <span><strong>Your approval</strong>Required before Vault changes</span>
        </div>
        <p className="onboarding-privacy">Keep Vault tokens and secret values out of chat. Enter them only in the separate secure review form, opened in a new tab.</p>
        {url ? (
          <iframe className="onboarding-chat" src={url} title="IBM Granite Vault onboarding assistant" referrerPolicy="no-referrer" />
        ) : (
          <section className="onboarding-unavailable" role="status">
            <span className="agent-gem">✦</span>
            <h2>IBM Vault onboarding is being configured</h2>
            <p>Your platform team needs to connect the IBM agent before chat is available. No Vault changes have been made.</p>
            <p>You can return to the catalog while setup is completed.</p>
            <Link className="back-to-catalog" href="/">Return to catalog →</Link>
          </section>
        )}
      </section>
      </div>
    </main>
  );
}
