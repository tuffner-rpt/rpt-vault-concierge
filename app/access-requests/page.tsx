"use client";

import { useEffect, useState } from "react";
import { DocumentationWindow } from "../components/DocumentationWindow";

type AccessRequest = {
  name: string;
  type: string;
  owner: string;
  time: string;
  status: string;
};

const defaultRequests: AccessRequest[] = [
  { name: "payments-api/prod/stripe", type: "API key", owner: "You", time: "12 min ago", status: "Active" },
  { name: "analytics/staging/postgres", type: "Database", owner: "Maya Chen", time: "1 hr ago", status: "Active" },
  { name: "identity/dev/tls", type: "Certificate", owner: "Luis Ortiz", time: "Yesterday", status: "Renewing" },
];

export default function AccessRequestsPage() {
  const [requests, setRequests] = useState(defaultRequests);
  const [docsOpen, setDocsOpen] = useState(false);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem("vault-access-requests") || "[]") as AccessRequest[];
      if (saved.length) setRequests([...saved, ...defaultRequests]);
    } catch {
      localStorage.removeItem("vault-access-requests");
    }
  }, []);

  return (
    <main className="app-shell request-page">
      <header className="topbar">
        <a className="brand" href="/" aria-label="RPT Vault Developer Concierge home">
          <span className="brand-mark"><img src="/rpt-gcp.jpeg" alt="" /></span>
          <span>RPT Vault <strong>Developer Concierge</strong></span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="/">Catalog</a>
          <a className="nav-active" href="/access-requests">My secrets</a>
          <a href="/#docs" onClick={(event) => { event.preventDefault(); setDocsOpen(true); }}>Docs</a>
        </nav>
        <div className="top-actions"><button className="avatar" aria-label="Open user menu">KT</button></div>
      </header>

      <div className="workspace">
        <aside className="sidebar">
          <div className="side-label">Workspace</div>
          <a className="side-item" href="/"><span>⌂</span> Secret catalog</a>
          <a className="side-item" href="/access-requests"><span>◫</span> My secrets <b>{requests.length}</b></a>
          <a className="side-item active" href="/access-requests"><span>◎</span> Access requests</a>
          <div className="side-label section-gap">Resources</div>
          <a className="side-item" href="/#docs" onClick={(event) => { event.preventDefault(); setDocsOpen(true); }}><span>?</span> Documentation</a>
          <div className="health-statuses" aria-label="Service health">
            <div className="side-status"><span className="status-dot" /><div><strong>Vault healthy</strong><small>us-central1 · 99.99%</small></div></div>
            <div className="side-status"><span className="status-dot openai-dot" /><div><strong>OpenAI healthy</strong><small>gpt-5.6-terra · ready</small></div></div>
          </div>
        </aside>

        <section className="content">
          <div className="request-heading">
            <div className="hero"><h1>Access Requests</h1><p>Review secret provisioning activity across your teams.</p></div>
            <a className="back-to-catalog" href="/">← Back to catalog</a>
          </div>

          <section className="activity-section">
            <div className="section-heading">
              <div><h2>Recent activity</h2><p>All secrets provisioned through RPT Vault Developer Concierge</p></div>
              <span className="request-count">{requests.length} requests</span>
            </div>
            <div className="activity-table" role="table" aria-label="Access requests">
              <div className="table-row table-head" role="row">
                <span>Secret path</span><span>Type</span><span>Owner</span><span>Created</span><span>Status</span>
              </div>
              {requests.map((item, index) => (
                <div className="table-row" role="row" key={`${item.name}-${item.time}-${index}`}>
                  <span className="secret-name"><i>◇</i>{item.name}</span>
                  <span>{item.type}</span><span>{item.owner}</span><span>{item.time}</span>
                  <span><b className={`pill ${item.status.toLowerCase()}`}>{item.status}</b></span>
                </div>
              ))}
            </div>
          </section>

          <footer><span>RPT Vault Developer Concierge - Demo</span></footer>
        </section>
      </div>
      <DocumentationWindow open={docsOpen} onClose={() => setDocsOpen(false)} />
    </main>
  );
}
