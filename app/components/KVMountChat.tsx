"use client";

import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";

const mountQuestions = [
  "What is the KV Mount Name you are requesting?",
  "Enter your Business Unit ID",
  "Enter your UserID",
];
type InputRule = { pattern: RegExp; max: number; hint: string; validate?: (value: string) => boolean };
const mountRules: InputRule[] = [
  { pattern: /^Onboard-[a-z0-9][a-z0-9_-]*$/, max: 100, hint: 'Must use "Onboard-xxx" format. Example: Onboard-payments.' },
  { pattern: /^[A-Za-z0-9][A-Za-z0-9_.-]*$/, max: 64, hint: "Use letters, digits, dots, underscores or hyphens (up to 64 characters)." },
  { pattern: /^[A-Za-z0-9][A-Za-z0-9_.@-]*$/, max: 128, hint: "Enter your UserID or email address (up to 128 characters)." },
];

const secretQuestions = [
  "What is the name or path of the KV secret you are requesting?",
  "Enter your Business Unit ID",
  "Enter your UserID",
];
const secretRules: InputRule[] = [
  { pattern: /^[A-Za-z0-9_.@~/-]+$/, max: 300, validate: value => value.split("/").every(part => part !== "" && part !== "." && part !== ".."), hint: "Enter a relative secret name/path, such as app/database. Do not enter secret values." },
  mountRules[1],
  mountRules[2],
];
const labels: Record<string, string> = { mount: "KV Mount Name", secret_path: "Secret Name / Path", business_unit_id: "Business Unit ID", user_id: "UserID" };

export function KVMountChat({ mode = "mount" }: { mode?: "mount" | "secret" }) {
  const secret = mode === "secret";
  const questions = secret ? secretQuestions : mountQuestions;
  const rules = secret ? secretRules : mountRules;
  const fields = secret ? ["secret_path", "business_unit_id", "user_id"] : ["mount", "business_unit_id", "user_id"];
  const noun = secret ? "secret" : "mount";
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
    if (!rule || value.length > rule.max || !rule.pattern.test(value) || (rule.validate && !rule.validate(value))) {
      setError(rule?.hint || "Review your answers below.");
      return;
    }
    setAnswers(previous => [...previous, value]);
    setDraft("");
    setError("");
  }

  async function submit() {
    if (submitting.current || step !== questions.length || status !== "ready") return;
    submitting.current = true;
    setStatus("submitting");
    setError("");
    try {
      const response = await fetch(secret ? "/api/kv-secret" : "/api/kv-mount", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.fromEntries(fields.map((field, index) => [field, answers[index]]))),
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
    <section className="kv-guided-chat" aria-label={`Ask RPT KV ${noun} onboarding`}>
      <div className="kv-chat-brand">Ask RPT <span>KV {noun} onboarding{secret ? " · Path: /admin/onboard-concierge" : ""}</span></div>
      <div className="kv-chat-messages" role="log" aria-live="polite" aria-relevant="additions">
        {questions.slice(0, Math.min(step + 1, questions.length)).map((question, index) => (
          <div className="kv-chat-exchange" key={question}>
            <div className="kv-chat-bubble assistant"><strong>Ask RPT</strong><p>{question}</p>{index === 0 ? <small>{secret ? "All keys are created under /admin/onboard-concierge/. " : ""}{rules[0].hint}</small> : null}</div>
            {answers[index] ? <div className="kv-chat-bubble user"><strong>You</strong><p>{answers[index]}</p></div> : null}
          </div>
        ))}
        {step === questions.length ? (
          <div className="kv-chat-review">
            <h2>Review your KV {noun} request</h2>
            <dl>{secret ? <><dt>Vault Namespace</dt><dd>admin</dd><dt>KV Mount Name</dt><dd>onboard-concierge</dd><dt>Full Mount Path</dt><dd>/admin/onboard-concierge</dd></> : null}{fields.map((field, index) => <Fragment key={field}><dt>{labels[field]}</dt><dd>{answers[index]}</dd></Fragment>)}<dt>KV Mount Type</dt><dd>KV v2</dd></dl>
            {status === "submitted" ? <><p role="status">Your request is pending administrator review. No Vault change has been made.</p><a href={reviewUrl} target="_blank" rel="noopener noreferrer">Open secure review ↗</a></> : <>
              {secret ? <p>Secret values are entered only in the secure review form. This request cannot overwrite an existing secret.</p> : null}
              <p>The Business Unit ID and UserID are self-reported. An administrator must approve and execute the request with their Vault permissions.</p>
              <div className="kv-chat-review-actions"><button type="button" onClick={submit} disabled={status !== "ready"}>{status === "submitting" ? "Submitting…" : "Submit for Administrator Review"}</button><button type="button" className="secondary" disabled={status !== "ready"} onClick={() => { setAnswers([]); setError(""); }}>Edit answers</button></div>
            </>}
          </div>
        ) : null}
        <div ref={end} />
      </div>
      <div className="kv-chat-composer">
        {error ? <p role="alert" className="kv-chat-error">{error}</p> : null}
        {step < questions.length ? <form onSubmit={answer}>
          <label htmlFor="kv-answer">{questions[step]}</label>
          <div className="kv-chat-input-row"><input ref={input} id="kv-answer" value={draft} onChange={event => { setDraft(event.target.value); setError(""); }} placeholder={fields[step] === "mount" ? "Onboard-xxx" : fields[step] === "secret_path" ? "app/database" : labels[fields[step]]} maxLength={rules[step].max} autoComplete="off" spellCheck={false} aria-describedby={step === 0 ? "kv-mount-format" : undefined} /><button type="submit" disabled={!draft.trim()}>Send →</button></div>
          {step === 0 ? <small id="kv-mount-format">{rules[0].hint}</small> : null}
          {secret ? <small>Do not enter secret values in this chat.</small> : null}
        </form> : null}
      </div>
    </section>
  );
}
