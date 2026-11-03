"use strict";
const $ = (id) => document.getElementById(id);
let ticket = new URLSearchParams(location.hash.slice(1)).get("plan");
history.replaceState(null, "", location.pathname);
let plan;
let busy = false;

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
  const payload = { ticket, vault_token: $("vault-token").value, confirmed: $("confirmed").checked, secret_data: secretData };
  try {
    const result = await call("/api/execute", payload);
    $("status").textContent = result.status === "already_exists" ? "The compatible engine already exists. No changes were made." : "Created in Vault.";
    $("receipt").textContent = JSON.stringify(result, null, 2); $("receipt").hidden = false; $("execute").hidden = true; ticket = null;
  } catch (error) {
    $("status").textContent = error.message + " Credentials have been cleared. Verify the result in Vault before retrying.";
  } finally {
    payload.vault_token = "";
    for (const key of Object.keys(secretData)) delete secretData[key];
    $("vault-token").value = "";
    for (const input of $("fields").querySelectorAll('input[type="password"]')) input.value = "";
    $("confirmed").checked = false; busy = false; $("submit").disabled = false;
  }
});

(async () => {
  if (!ticket) { $("status").textContent = "Open the review link provided by your Vault Concierge agent to begin."; return; }
  try {
    const result = await call("/api/preview", { ticket }); plan = result.plan;
    const fields = { Operation: plan.action === "enable_engine" ? "Enable secrets engine" : "Create KV v2 secret", "Vault address": result.vault_address, Namespace: result.namespace || "Root namespace", Engine: plan.engine, Mount: plan.mount + "/", "Secret path": plan.secret_path, Description: plan.description };
    for (const [label, value] of Object.entries(fields)) {
      if (!value) continue;
      const dt = document.createElement("dt"); dt.textContent = label;
      const dd = document.createElement("dd"); dd.textContent = value;
      $("summary").append(dt, dd);
    }
    $("summary").hidden = false; $("scope").textContent = result.scope; $("scope").hidden = false;
    $("status").textContent = "Pending your approval. This link expires 10 minutes after creation.";
    $("execute").hidden = false;
    if (plan.action === "create_secret") { $("secret-fields").hidden = false; addField(); }
  } catch (error) { $("status").textContent = error.message; }
})();
