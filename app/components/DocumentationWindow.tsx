"use client";

type DocumentationWindowProps = { open: boolean; onClose: () => void };

const resources = [
  { id: "vault-overview", icon: "V", title: "Vault fundamentals", description: "Understand Vault architecture, authentication, authorization, and audit workflows.", source: "HashiCorp", url: "https://developer.hashicorp.com/vault/docs/about-vault/what-is-vault" },
  { id: "vault-kv", icon: "K", title: "KV secrets engine", description: "Store versioned application secrets and manage KV v2 paths safely.", source: "HashiCorp", url: "https://developer.hashicorp.com/vault/docs/secrets/kv" },
  { id: "vault-database", icon: "D", title: "Dynamic database credentials", description: "Generate leased database users and automatically revoke expired access.", source: "HashiCorp", url: "https://developer.hashicorp.com/vault/docs/secrets/databases" },
  { id: "vault-pki", icon: "P", title: "PKI certificates", description: "Issue short-lived X.509 certificates from Vault's PKI secrets engine.", source: "HashiCorp", url: "https://developer.hashicorp.com/vault/docs/secrets/pki" },
  { id: "vault-policies", icon: "A", title: "Policies and least privilege", description: "Control path-based capabilities with deny-by-default Vault policies.", source: "HashiCorp", url: "https://developer.hashicorp.com/vault/docs/concepts/policies" },
  { id: "openai-responses", icon: "O", title: "OpenAI Responses API", description: "Build the server-side recommendation workflow used by this concierge.", source: "OpenAI", url: "https://developers.openai.com/api/docs/quickstart" },
] as const;

export function DocumentationWindow({ open, onClose }: DocumentationWindowProps) {
  if (!open) return null;

  return (
    <div className="docs-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="docs-window" role="dialog" aria-modal="true" aria-labelledby="docs-window-title">
        <header className="docs-window-head">
          <span className="agent-gem brand-agent"><img src="/rpt-gcp.jpeg" alt="" /></span>
          <div><span className="docs-kicker">OPENAI DOCUMENTATION GUIDE</span><h2 id="docs-window-title">Recommended documentation</h2></div>
          <button className="docs-close" onClick={onClose} aria-label="Close documentation window">×</button>
        </header>

        <div className="docs-grid">
          {resources.map((resource) => (
            <a className="doc-card" href={resource.url} target="_blank" rel="noreferrer" key={resource.id}>
              <div className="doc-card-top">
                <span className="doc-icon">{resource.icon}</span>
                <span className="doc-arrow" aria-hidden="true">↗</span>
              </div>
              <div className="doc-card-copy"><small>{resource.source}</small><h3>{resource.title}</h3><p>{resource.description}</p></div>
              <span className="doc-card-link">Open documentation <span>↗</span></span>
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}
