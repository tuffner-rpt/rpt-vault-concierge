"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

const questions = [
  "What is the KV Mount Name you are requesting?",
  "Enter your Business Unit ID",
  "Enter your UserID",
];
const rules = [
  { pattern: /^Onboard-[a-z0-9][a-z0-9_-]*$/, max: 100, hint: 'Must use "Onboard-xxx" format. Example: Onboard-payments.' },
  { pattern: /^[A-Za-z0-9][A-Za-z0-9_.-]*$/, max: 64, hint: "Use letters, digits, dots, underscores or hyphens (up to 64 characters)." },
  { pattern: /^[A-Za-z0-9][A-Za-z0-9_.@-]*$/, max: 128, hint: "Enter your UserID or email address (up to 128 characters)." },
];

export function KVMountChat() {
  const [answers, setAnswers] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState<"ready" | "submitting" | "submitted" | "uncertain">("ready");
  const [reviewUrl, setReviewUrl] = useState("");
  const submitting = useRef(false);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const step = answers.length;

  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); input.current?.focus(); }, [step, status]);

  function answer(event: FormEvent) {
    event.preventDefault();
    const value = draft.trim();
    const rule = rules[step];
    if (!rule || value.length > rule.max || !rule.pattern.test(value)) {
      setError(rule?.hint || "Review your answers below.");
      return;
    }
    setAnswers(previous => [...previous, value]);
    setDraft("");
    setError("");
  }

  async function submit() {
    if (submitting.current || step !== 3 || status !== "ready") return;
    submitting.current = true;
    setStatus("submitting");
    setError("");
    try {
      const response = await fetch("/api/kv-mount", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mount: answers[0], business_unit_id: answers[1], user_id: answers[2] }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Submission could not be confirmed.");
      setReviewUrl(result.review_url);
      setStatus("submitted");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Submission could not be confirmed. Check with your administrator before submitting again.");
      setStatus("uncertain");
    }
  }

  return (
    <section className="kv-guided-chat" aria-label="Ask RPT KV mount onboarding">
      <div className="kv-chat-brand">Ask RPT <span>KV mount onboarding</span></div>
      <div className="kv-chat-messages" role="log" aria-live="polite" aria-relevant="additions">
        {questions.slice(0, Math.min(step + 1, 3)).map((question, index) => (
          <div className="kv-chat-exchange" key={question}>
            <div className="kv-chat-bubble assistant"><strong>Ask RPT</strong><p>{question}</p>{index === 0 ? <small>Must use &quot;Onboard-xxx&quot; format.</small> : null}</div>
            {answers[index] ? <div className="kv-chat-bubble user"><strong>You</strong><p>{answers[index]}</p></div> : null}
          </div>
        ))}
        {step === 3 ? (
          <div className="kv-chat-review">
            <h2>Review your KV mount request</h2>
            <dl><dt>KV Mount Name</dt><dd>{answers[0]}</dd><dt>Business Unit ID</dt><dd>{answers[1]}</dd><dt>UserID</dt><dd>{answers[2]}</dd><dt>KV Mount Type</dt><dd>KV v2</dd></dl>
            {status === "submitted" ? <><p role="status">Your request is pending administrator review. No Vault change has been made.</p><a href={reviewUrl} target="_blank" rel="noopener noreferrer">Open secure review ↗</a></> : <>
              <p>The Business Unit ID and UserID are self-reported. An administrator must approve and execute the request with their Vault permissions.</p>
              <div className="kv-chat-review-actions"><button type="button" onClick={submit} disabled={status !== "ready"}>{status === "submitting" ? "Submitting…" : "Submit for Administrator Review"}</button><button type="button" className="secondary" disabled={status !== "ready"} onClick={() => { setAnswers([]); setError(""); }}>Edit answers</button></div>
            </>}
          </div>
        ) : null}
        <div ref={end} />
      </div>
      <div className="kv-chat-composer">
        {error ? <p role="alert" className="kv-chat-error">{error}</p> : null}
        {step < 3 ? <form onSubmit={answer}>
          <label htmlFor="kv-answer">{questions[step]}</label>
          <div className="kv-chat-input-row"><input ref={input} id="kv-answer" value={draft} onChange={event => { setDraft(event.target.value); setError(""); }} placeholder={step === 0 ? "Onboard-xxx" : step === 1 ? "Business Unit ID" : "UserID"} maxLength={rules[step].max} autoComplete="off" spellCheck={false} aria-describedby={step === 0 ? "kv-mount-format" : undefined} /><button type="submit" disabled={!draft.trim()}>Send →</button></div>
          {step === 0 ? <small id="kv-mount-format">Must use &quot;Onboard-xxx&quot; format.</small> : null}
        </form> : null}
      </div>
    </section>
  );
}
