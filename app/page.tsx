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
            <h1>Workload Recommendation</h1>
            <p>Choose a Vault pattern, then prepare your request in IBM chat for administrator review.</p>
          </section>

          <section className="template-grid" aria-label="Secret templates">
            {templates.map((template) => (
              <button className="template-card" key={template.id} onClick={() => window.location.assign("/vault-onboarding")}>
                <span className={`tile-icon ${template.accent}`}>{template.icon}</span>
                <span className="tile-arrow">↗</span>
                <strong>{template.title}</strong>
                <span className="tile-description">{template.description}</span>
                <span className="tile-meta"><i /> {template.kind} <em>{template.lease}</em></span>
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
