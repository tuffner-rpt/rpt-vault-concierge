"use client";

import { useState } from "react";
import { DocumentationWindow } from "./components/DocumentationWindow";
import { AdminReviewLink } from "./components/AdminReviewLink";
import { FloatingWatsonChat } from "./components/FloatingWatsonChat";

type Template = {
  id: string;
  icon: string;
  title: string;
  description: string;
  accent: string;
  kind: string;
};

const templates: Template[] = [
  { id: "kv-mount", icon: "⌁", title: "Create KV Mount", description: "Set up a KV v1 or KV v2 secrets engine at your chosen mount path.", accent: "mint", kind: "kv-v1 / kv-v2" },
  { id: "kv-secret", icon: "◇", title: "Create KV Secret", description: "Add a new secret to an existing KV v2 mount.", accent: "blue", kind: "kv-v2" },
  { id: "kubernetes-secret", icon: "⎈", title: "Create Kubernetes Secret", description: "Request Vault-managed credentials for a Kubernetes workload.", accent: "violet", kind: "kubernetes" },
  { id: "database-secret", icon: "◉", title: "Create Database Secret", description: "Request database credentials from a configured Vault database engine.", accent: "blue", kind: "database" },
  { id: "pki-certificate", icon: "✦", title: "Create PKI Certificate", description: "Request a certificate from a configured Vault PKI role.", accent: "amber", kind: "pki" },
];

export default function Home() {
  const [docsOpen, setDocsOpen] = useState(false);

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
          <AdminReviewLink />
          <div className="health-statuses" aria-label="Service health">
            <div className="side-status">
              <span className="status-dot" />
              <div><strong>Vault healthy</strong><small>us-central1 · 99.99%</small></div>
            </div>
          </div>
        </aside>

        <section className="content">
          <section className="hero" id="catalog">
            <h1>RPT Vault Onboarding Patterns</h1>
            <p>Choose a Vault Onboarding Pattern Tile Down Below:</p>
          </section>

          <section className="template-grid" aria-label="Secret templates">
            {templates.map((template) => (
              <button className="template-card" key={template.id} onClick={() => window.location.assign(template.id === "kv-mount" ? "/kv-mount" : template.id === "kv-secret" ? "/kv-secret" : "/vault-onboarding")}>
                <span className={`tile-icon ${template.accent}`}>{template.icon}</span>
                <span className="tile-arrow">↗</span>
                <strong>{template.title}</strong>
                <span className="tile-description">{template.description}</span>
                <span className="tile-meta"><i /> {template.kind} </span>
              </button>
            ))}
          </section>

          <footer id="docs"><span>RPT Vault Developer Concierge - Demo</span></footer>
        </section>
      </div>

      <DocumentationWindow open={docsOpen} onClose={() => setDocsOpen(false)} />
      <FloatingWatsonChat />
    </main>
  );
}
