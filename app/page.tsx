"use client";

import { FormEvent, useMemo, useState } from "react";
import { DocumentationWindow } from "./components/DocumentationWindow";

type Template = {
  id: string;
  icon: string;
  title: string;
  description: string;
  accent: string;
  lease: string;
  kind: string;
};

const templates: Template[] = [
  { id: "api-key", icon: "⌁", title: "API key", description: "Generate a scoped key for a service-to-service integration.", accent: "mint", lease: "90 days", kind: "kv-v2" },
  { id: "database", icon: "◉", title: "Database credential", description: "Create a rotating credential for PostgreSQL or MySQL.", accent: "blue", lease: "24 hours", kind: "dynamic" },
  { id: "cloud", icon: "◇", title: "Cloud access", description: "Provision short-lived credentials for a cloud workload.", accent: "violet", lease: "8 hours", kind: "dynamic" },
  { id: "certificate", icon: "✦", title: "TLS certificate", description: "Issue a certificate from the internal PKI authority.", accent: "amber", lease: "30 days", kind: "pki" },
];

export default function Home() {
  const [selected, setSelected] = useState<Template | null>(null);
  const [name, setName] = useState("");
  const [environment, setEnvironment] = useState("development");
  const [team, setTeam] = useState("platform");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<{ path: string; lease: string } | null>(null);
  const [error, setError] = useState("");
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentInput, setAgentInput] = useState("");
  const [agentReply, setAgentReply] = useState("Tell me what your app needs. I can recommend the safest secret type and configuration.");
  const [agentBusy, setAgentBusy] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);

  const previewPath = useMemo(() => {
    const safe = name.trim().toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-|-$/g, "") || "secret-name";
    return `kv/${team}/${environment}/${safe}`;
  }, [name, team, environment]);

  function openProvision(template: Template) {
    setSelected(template);
    setName("");
    setDescription("");
    setError("");
    setSuccess(null);
  }

  async function provision(event: FormEvent) {
    event.preventDefault();
    if (!selected || !name.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/provision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ templateId: selected.id, name, environment, team, description }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Provisioning failed");
      setSuccess({ path: result.path, lease: result.lease });
      const requestRecord = { name: result.path.replace(/^kv\//, ""), type: selected.title, owner: "You", time: "Just now", status: "Active" };
      const saved = JSON.parse(localStorage.getItem("vault-access-requests") || "[]");
      localStorage.setItem("vault-access-requests", JSON.stringify([requestRecord, ...saved].slice(0, 20)));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  async function askAgent(event: FormEvent) {
    event.preventDefault();
    if (!agentInput.trim()) return;
    setAgentBusy(true);
    try {
      const response = await fetch("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: agentInput }),
      });
      const result = await response.json();
      setAgentReply(result.message || "I couldn't prepare a recommendation.");
    } catch {
      setAgentReply("I couldn't reach the agent. You can still provision from a template.");
    } finally {
      setAgentBusy(false);
      setAgentInput("");
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="RPT Vault Developer Concierge home">
          <span className="brand-mark"><img src="/rpt-gcp.jpeg" alt="" /></span>
          <span>RPT Vault <strong>Developer Concierge</strong></span>
        </a>
        <nav aria-label="Primary navigation">
          <a className="nav-active" href="#catalog">Catalog</a>
          <a href="/access-requests">My secrets</a>
          <a href="#docs" onClick={(event) => { event.preventDefault(); setDocsOpen(true); }}>Docs</a>
        </nav>
        <div className="top-actions">
          <button className="avatar" aria-label="Open user menu">KT</button>
        </div>
      </header>

      <div className="workspace" id="top">
        <aside className="sidebar">
          <div className="side-label">Workspace</div>
          <a className="side-item active" href="#catalog"><span>⌂</span> Secret catalog</a>
          <a className="side-item" href="/access-requests"><span>◫</span> My secrets <b>3</b></a>
          <a className="side-item" href="/access-requests"><span>◎</span> Access requests</a>
          <div className="side-label section-gap">Resources</div>
          <a className="side-item" href="#docs" onClick={(event) => { event.preventDefault(); setDocsOpen(true); }}><span>?</span> Documentation</a>
          <div className="health-statuses" aria-label="Service health">
            <div className="side-status">
              <span className="status-dot" />
              <div><strong>Vault healthy</strong><small>us-central1 · 99.99%</small></div>
            </div>
            <div className="side-status">
              <span className="status-dot openai-dot" />
              <div><strong>OpenAI healthy</strong><small>gpt-5.6-terra · ready</small></div>
            </div>
          </div>
        </aside>

        <section className="content">
          <section className="hero" id="catalog">
            <h1>Workload Recommendation</h1>
            <p>Choose a HashiCorp Vault Secret Pattern Down Below:</p>
          </section>

          <section className="template-grid" aria-label="Secret templates">
            {templates.map((template) => (
              <button className="template-card" key={template.id} onClick={() => openProvision(template)}>
                <span className={`tile-icon ${template.accent}`}>{template.icon}</span>
                <span className="tile-arrow">↗</span>
                <strong>{template.title}</strong>
                <span className="tile-description">{template.description}</span>
                <span className="tile-meta"><i /> {template.kind} <em>{template.lease}</em></span>
              </button>
            ))}
          </section>

          <button className="agent-banner" onClick={() => setAgentOpen(true)}>
            <span className="agent-gem">✦</span>
            <span><strong>Not sure which secret to use?</strong><small>Ask RPT Vault Developer Concierge For Recommended Vault Onboarding Patterns</small></span>
            <span className="ask-button">Ask OpenAI <b>→</b></span>
          </button>

          <footer id="docs"><span>RPT Vault Developer Concierge - Demo</span></footer>
        </section>
      </div>

      {selected && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && setSelected(null)}>
          <section className="provision-panel" role="dialog" aria-modal="true" aria-labelledby="provision-title">
            <button className="close-button" onClick={() => setSelected(null)} aria-label="Close provisioning panel">×</button>
            {!success ? (
              <>
                <div className={`panel-icon ${selected.accent}`}>{selected.icon}</div>
                <div className="panel-kicker">NEW SECRET</div>
                <h2 id="provision-title">Provision {selected.title.toLowerCase()}</h2>
                <p className="panel-copy">Vault will create this secret with least-privilege defaults and add it to the audit trail.</p>
                <form onSubmit={provision}>
                  <label>Secret name<input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. stripe-payments" required /></label>
                  <div className="form-row">
                    <label>Environment<select value={environment} onChange={(e) => setEnvironment(e.target.value)}><option value="development">Development</option><option value="staging">Staging</option><option value="production">Production</option></select></label>
                    <label>Team<select value={team} onChange={(e) => setTeam(e.target.value)}><option value="platform">Platform</option><option value="payments">Payments</option><option value="identity">Identity</option><option value="analytics">Analytics</option></select></label>
                  </div>
                  <label>Description <span>(optional)</span><textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What will this secret be used for?" /></label>
                  <div className="path-preview"><small>VAULT PATH</small><code>{previewPath}</code></div>
                  <div className="policy-note"><span>✓</span><div><strong>Policy checks passed</strong><small>Rotation, encryption, and ownership metadata will be applied.</small></div></div>
                  {error && <p className="form-error">{error}</p>}
                  <button className="provision-button" type="submit" disabled={submitting}>{submitting ? "Provisioning…" : "Provision secret"}<span>→</span></button>
                </form>
              </>
            ) : (
              <div className="success-state">
                <div className="success-check">✓</div>
                <div className="panel-kicker">PROVISIONED</div>
                <h2>Secret ready</h2>
                <p>Your secret was created without exposing its value in the portal.</p>
                <div className="success-path"><small>VAULT PATH</small><code>{success.path}</code><span>Lease: {success.lease}</span></div>
                <pre>{`vault kv get ${success.path.replace(/^kv\//, "kv/")}`}</pre>
                <button className="provision-button" onClick={() => setSelected(null)}>Done <span>✓</span></button>
              </div>
            )}
          </section>
        </div>
      )}

      {agentOpen && (
        <aside className="agent-panel" aria-label="RPT Vault Developer Concierge">
          <div className="agent-head"><span className="agent-gem brand-agent"><img src="/rpt-gcp.jpeg" alt="" /></span><div><strong>RPT Vault Developer Concierge</strong><small>Powered by OpenAI</small></div><button onClick={() => setAgentOpen(false)} aria-label="Close RPT Vault Developer Concierge">×</button></div>
          <div className="agent-thread">
            <div className="agent-bubble">{agentReply}</div>
            <div className="agent-suggestions"><button onClick={() => setAgentInput("My production service needs a Stripe API key")}>Production API key</button><button onClick={() => setAgentInput("My CI job needs temporary database access")}>CI database access</button></div>
          </div>
          <form className="agent-form" onSubmit={askAgent}><input value={agentInput} onChange={(e) => setAgentInput(e.target.value)} placeholder="Describe what your app needs…" aria-label="Message RPT Vault Developer Concierge"/><button disabled={agentBusy || !agentInput.trim()}>{agentBusy ? "…" : "↑"}</button></form>
        </aside>
      )}
      <DocumentationWindow open={docsOpen} onClose={() => setDocsOpen(false)} />
    </main>
  );
}
