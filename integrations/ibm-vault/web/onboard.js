"use strict";
const $ = (id) => document.getElementById(id);
const fragment = new URLSearchParams(location.hash.slice(1));
let ticket = fragment.get("plan");
let reviewId = fragment.get("review");
history.replaceState(null, "", location.pathname);
let plan;
let busy = false;

$("inspect-engine").addEventListener("click", async () => {
  $("inspect-engine").disabled = true;
  try {
    const info = await call("/api/inspect", { ticket, vault_token: $("vault-token").value });
    $("engine-info").textContent = JSON.stringify(info, null, 2); $("engine-info").hidden = false;
  } catch (error) { $("status").textContent = error.message; }
  finally { $("inspect-engine").disabled = false; }
});
function clearSensitive() {
  $("sensitive-output").textContent = ""; $("sensitive-result").hidden = true;
  $("vault-token").value = ""; $("operation-json").value = "{}";
  for (const input of $("fields").querySelectorAll('input[type="password"]')) input.value = "";
}
$("clear-result").addEventListener("click", clearSensitive);
window.addEventListener("pagehide", clearSensitive);

async function call(path, payload) {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), cache: "no-store", credentials: "same-origin" });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request could not be completed.");
  return data;
}

function addField() {
  if ($("fields").children.length >= 64) return;
  const row = document.createElement("div");
  row.className = "field-row";
  const keyLabel = document.createElement("label");
  keyLabel.textContent = "Field name";
  const key = document.createElement("input");
  key.required = true; key.maxLength = 100; key.pattern = "[A-Za-z0-9_-]+"; key.placeholder = "e.g. api_key"; key.autocomplete = "off";
  keyLabel.append(key);
  const valueLabel = document.createElement("label");
  valueLabel.textContent = "Secret value";
  const value = document.createElement("input");
  value.type = "password"; value.required = true; value.autocomplete = "off"; value.maxLength = 16000;
  valueLabel.append(value);
  const remove = document.createElement("button");
  remove.type = "button"; remove.className = "secondary"; remove.textContent = "Remove";
  remove.addEventListener("click", () => row.remove());
  row.append(keyLabel, valueLabel, remove); $("fields").append(row);
}

$("add-field").addEventListener("click", addField);
$("execute").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  const secretData = Object.create(null);
  for (const row of $("fields").children) {
    const [key, value] = row.querySelectorAll("input");
    if (Object.hasOwn(secretData, key.value)) { $("status").textContent = "Use unique field names."; return; }
    secretData[key.value] = value.value;
  }
  if (plan.action === "create_secret" && !Object.keys(secretData).length) { $("status").textContent = "Add at least one secret field."; return; }
  busy = true; $("submit").disabled = true; $("status").textContent = "Submitting to Vault…";
  const payload = { ticket, vault_token: $("vault-token").value, confirmed: $("confirmed").checked, secret_data: secretData, operation_json: $("operation-json").value, confirmation_text: $("confirmation-text").value };
  try {
    const result = await call("/api/execute", payload);
    $("status").textContent = result.status === "already_exists" ? "The compatible engine already exists. No changes were made." : result.status === "completed" ? "Vault completed the approved operation. Its outcome is recorded in the review queue." : "Created in Vault.";
    const { sensitive_result: sensitive, ...receipt } = result;
    if (result.fulfilled_url) { $("status").textContent = "Secret created in Vault and logged to Requests fulfilled."; $("fulfilled-link").hidden = false; }
    $("receipt").textContent = JSON.stringify(receipt, null, 2); $("receipt").hidden = false; $("execute").hidden = true; ticket = null;
    if (sensitive && Object.keys(sensitive).length) { $("sensitive-output").textContent = JSON.stringify(sensitive, null, 2); $("sensitive-result").hidden = false; }
  } catch (error) {
    $("status").textContent = error.message + " Credentials have been cleared. Verify the result in Vault before retrying.";
  } finally {
    payload.vault_token = "";
    payload.operation_json = ""; $("operation-json").value = "{}"; $("confirmation-text").value = "";
    for (const key of Object.keys(secretData)) delete secretData[key];
    $("vault-token").value = "";
    for (const input of $("fields").querySelectorAll('input[type="password"]')) input.value = "";
    $("confirmed").checked = false; busy = false; $("submit").disabled = false;
  }
});

(async () => {
  if (!ticket && !reviewId) { $("status").textContent = "Open the review link provided by your Vault Concierge agent to begin."; return; }
  try {
    if (reviewId) { ticket = (await call("/api/resolve", { review_id: reviewId })).ticket; reviewId = null; }
    const result = await call("/api/preview", { ticket }); plan = result.plan;
    const selfService = plan.approval_mode === "self_service";
    if (selfService) {
      document.title = "Create KV Secret · RPT Vault";
      $("page-eyebrow").textContent = "KV SECRET CREATION";
      $("page-title").textContent = "Create your KV secret.";
      $("page-intro").textContent = "Enter the secret values and your scoped Vault token to create this key under /admin/onboard-concierge. No separate administrator approval is required.";
      const steps = $("page-steps").children;
      steps[1].textContent = "02 · Enter values & create";
      steps[2].textContent = "03 · Requests fulfilled";
      $("submit").textContent = "Create secret";
    }
    const names = { enable_engine: "Enable secrets engine", create_secret: "Create KV v2 secret", engine_operation: "Run engine-specific operation", tune_engine: "Tune engine lease defaults", disable_engine: "Disable engine and remove its data" };
    const fields = { Operation: names[plan.action], "Vault address": result.vault_address, Namespace: result.namespace || "Root namespace", "Business Unit ID (self-reported)": plan.business_unit_id, "UserID (self-reported)": plan.user_id, Engine: plan.engine, Mount: plan.mount + "/", "Secret path": plan.secret_path, Endpoint: plan.endpoint, "HTTP method": plan.action === "engine_operation" ? plan.method : "", Description: plan.description };
    for (const [label, value] of Object.entries(fields)) {
      if (!value) continue;
      const dt = document.createElement("dt"); dt.textContent = label;
      const dd = document.createElement("dd"); dd.textContent = value;
      $("summary").append(dt, dd);
    }
    $("summary").hidden = false; $("scope").textContent = result.scope; $("scope").hidden = false;
    $("status").textContent = selfService ? "Ready to create with your Vault permissions. This link expires 10 minutes after creation." : "Pending your approval. This link expires 10 minutes after creation.";
    if (result.access_requirements) {
      $("access-note").textContent = result.access_requirements.note;
      $("access-policy").textContent = result.access_requirements.policy_hcl;
      $("access-help").hidden = false;
    }
    if (plan.action === "create_secret") $("inspect-engine").hidden = true;
    let approvedAdmin = true;
    $("back-queue").hidden = !result.admin_review_required;
    if (result.admin_review_required) {
      const session = await fetch("/api/admin/session", {credentials:"same-origin", cache:"no-store"});
      approvedAdmin = session.ok;
      $("admin-required").hidden = approvedAdmin;
      if (!approvedAdmin) $("status").textContent = "Queued for administrator review. No Vault change has been made.";
    }
    $("execute").hidden = !approvedAdmin;
    if (plan.action === "create_secret") { $("secret-fields").hidden = false; addField(); }
    if (["engine_operation", "tune_engine"].includes(plan.action)) $("operation-fields").hidden = false;
    if (result.confirmation_phrase) {
      $("destructive-confirmation").hidden = false; $("confirmation-phrase").textContent = result.confirmation_phrase; $("confirmation-text").required = true;
    }
    if (plan.action === "disable_engine") $("submit").textContent = "Confirm & disable engine";
    else if (plan.action !== "enable_engine" && plan.action !== "create_secret") $("submit").textContent = "Confirm & execute operation";
  } catch (error) { $("status").textContent = error.message; }
})();
