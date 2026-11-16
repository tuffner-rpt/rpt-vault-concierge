"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

export function KVSecretList() {
  const token = useRef("");
  const tokenInput = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [prefix, setPrefix] = useState("");
  const [keys, setKeys] = useState<string[] | null>(null);
  const [error, setError] = useState("");

  function clear() {
    controller.current?.abort();
    controller.current = null;
    token.current = "";
    if (tokenInput.current) tokenInput.current.value = "";
    setConnected(false); setBusy(false); setKeys(null); setPrefix(""); setError("");
  }

  useEffect(() => {
    const onHide = () => {
      controller.current?.abort(); controller.current = null; token.current = "";
      if (tokenInput.current) tokenInput.current.value = "";
      setConnected(false); setKeys(null); setPrefix(""); setBusy(false); setError("");
    };
    window.addEventListener("pagehide", onHide);
    return () => { window.removeEventListener("pagehide", onHide); controller.current?.abort(); token.current = ""; };
  }, []);

  async function load(path: string) {
    if (controller.current || !token.current) return;
    const active = new AbortController();
    controller.current = active;
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/kv-secrets", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vault_token: token.current, prefix: path }), signal: active.signal, cache: "no-store",
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not list keys.");
      if (active.signal.aborted) return;
      setPrefix(result.prefix); setKeys(result.keys); setConnected(true);
    } catch (failure) {
      if (active.signal.aborted) return;
      token.current = ""; setConnected(false); setKeys(null);
      setError(failure instanceof Error ? failure.message : "Could not list keys.");
    } finally {
      if (controller.current === active) { controller.current = null; setBusy(false); }
    }
  }

  function connect(event: FormEvent) {
    event.preventDefault();
    const value = tokenInput.current?.value.trim() || "";
    if (!value || controller.current) return;
    token.current = value;
    if (tokenInput.current) tokenInput.current.value = "";
    void load("");
  }

  return <section className="kv-list-panel" aria-label="KV secrets in admin onboard-concierge">
    <div className="panel-kicker">HASHICORP VAULT · KV V2</div>
    <h2>/admin/onboard-concierge</h2>
    <p>Browse key names and folders in this mount. Secret values are never retrieved.</p>
    {!connected ? <form onSubmit={connect} className="kv-list-auth" autoComplete="off">
      <label htmlFor="list-vault-token">Your scoped Vault token</label>
      <div className="kv-list-auth-row"><input ref={tokenInput} id="list-vault-token" type="password" required maxLength={4096} autoComplete="off" spellCheck={false} placeholder="Enter a token with list permission" disabled={busy} /><button type="submit" disabled={busy}>{busy ? "Loading…" : "List KV Secrets"}</button></div>
      <small>Your token is cleared when you leave this page.</small>
      <details><summary>Permissions needed</summary><p>Use a token in namespace <strong>admin</strong> with list permission on this mount’s metadata paths.</p><pre>{'path "onboard-concierge/metadata" {\n  capabilities = ["list"]\n}\n\npath "onboard-concierge/metadata/*" {\n  capabilities = ["list"]\n}'}</pre></details>
    </form> : <div className="kv-list-toolbar">
      <button type="button" onClick={() => void load("")} disabled={busy || !prefix}>Mount root</button>
      <button type="button" onClick={() => void load(prefix.split("/").slice(0, -1).join("/"))} disabled={busy || !prefix}>↑ Parent folder</button>
      <button type="button" onClick={() => void load(prefix)} disabled={busy}>Refresh</button>
      <button type="button" className="kv-list-clear" onClick={clear}>Clear session</button>
    </div>}
    {error ? <p className="kv-chat-error" role="alert">{error}</p> : null}
    {connected ? <section className="kv-list-results" aria-label="Listed key names">
      <div className="kv-list-current"><code>/admin/onboard-concierge/{prefix ? prefix + "/" : ""}</code><span role="status">{busy ? "Loading…" : `${keys?.length || 0} entries`}</span></div>
      {keys?.length === 0 ? <p>No keys found in this folder.</p> : <ul>{keys?.map(key => <li key={key}>{key.endsWith("/") ? <button type="button" disabled={busy} onClick={() => void load((prefix ? prefix + "/" : "") + key.slice(0, -1))}><span aria-hidden="true">▣</span> {key}<span className="kv-list-open">Open folder →</span></button> : <div><span aria-hidden="true">◇</span> <strong>{key}</strong><span className="kv-list-open">Key</span></div>}</li>)}</ul>}
    </section> : null}
  </section>;
}
