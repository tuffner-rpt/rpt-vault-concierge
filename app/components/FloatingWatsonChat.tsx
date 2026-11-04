"use client";

import { useRef, useState } from "react";

export function FloatingWatsonChat() {
  const panel = useRef<HTMLDialogElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);
  const [initialized, setInitialized] = useState(false);
  const [open, setOpen] = useState(false);

  function openChat() {
    setInitialized(true);
    panel.current?.show();
    setOpen(true);
  }

  return (
    <>
      <dialog ref={panel} id="floating-watson-chat" className="floating-chat-panel" aria-labelledby="floating-chat-title" onClose={() => { setOpen(false); launcher.current?.focus(); }}>
        <header className="floating-chat-header">
          <div><span>IBM WATSONX ORCHESTRATE</span><h2 id="floating-chat-title">Vault concierge · IBM Granite</h2></div>
          <button type="button" autoFocus onClick={() => panel.current?.close()} aria-label="Minimize IBM chat">−</button>
        </header>
        {initialized ? <iframe src="/vault-onboarding/chat" title="IBM Granite Vault onboarding assistant" referrerPolicy="no-referrer" /> : null}
        <a className="floating-chat-full" href="/vault-onboarding" target="_blank" rel="noopener noreferrer">Open full-page chat ↗</a>
      </dialog>
      <button ref={launcher} type="button" className="floating-chat-launcher" onClick={() => open ? panel.current?.close() : openChat()} aria-label={open ? "Minimize IBM chat" : "Onboard engines and secrets with IBM Granite"} aria-expanded={open} aria-controls="floating-watson-chat" aria-haspopup="dialog">
        <span className="floating-chat-label"><strong>IBM Granite</strong><small>Onboard engines &amp; secrets</small></span>
        <span className="floating-chat-icon" aria-hidden="true"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-3 2 1.8-5.2A8.5 8.5 0 1 1 21 11.5Z" /><path d="M7 10h9M7 14h6" /></svg></span>
      </button>
    </>
  );
}
