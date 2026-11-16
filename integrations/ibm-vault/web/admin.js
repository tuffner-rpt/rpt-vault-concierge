"use strict";
const $ = (id) => document.getElementById(id);
let records = [], offset = 0, nextOffset = null, filter = "pending";
const labels = {enable_engine:"Enable secrets engine",create_secret:"Create KV v2 secret",update_secret:"Update KV v2 secret",engine_operation:"Engine operation",tune_engine:"Tune mount",disable_engine:"Disable engine"};
async function api(path, body) {
  const response = await fetch(path, {method:body === undefined ? "GET" : "POST", credentials:"same-origin", cache:"no-store", ...(body === undefined ? {} : {headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})});
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) { $("login-panel").hidden=false; $("queue-panel").hidden=true; records=[]; $("requests").replaceChildren(); }
    throw new Error(data.detail || "Request could not be completed.");
  }
  return data;
}
function text(tag, value, className) { const el=document.createElement(tag);el.textContent=value;if(className)el.className=className;return el; }
function display() {
  $("requests").replaceChildren();
  $("pending-count").textContent=records.filter(x=>x.status==="pending").length;
  $("completed-count").textContent=records.filter(x=>x.status==="completed").length;
  $("attention-count").textContent=records.filter(x=>["needs_attention","executing"].includes(x.status)).length;
  const visible=records.filter(x=>filter==="all" || (filter==="needs_attention" ? ["needs_attention","executing"].includes(x.status) : x.status===filter));
  $("empty").hidden=visible.length>0;
  for(const record of visible) {
    const p=record.plan, card=text("article","","card request-card"), head=text("div","","request-head");
    head.append(text("h3",labels[p.action] || p.action),text("span",record.status.replaceAll("_"," "),"badge "+record.status));card.append(head,text("p",record.id,"request-id"));
    const dl=text("dl","","request-meta");
    for(const [label,value] of Object.entries({"Business Unit ID (self-reported)":p.business_unit_id,"UserID (self-reported)":p.user_id,Engine:p.engine,Mount:p.mount+"/",Path:p.secret_path || p.endpoint,Method:p.action==="engine_operation" ? p.method : "",Purpose:p.description,Submitted:new Date(record.created_at*1000).toLocaleString(),Requester:record.requester,Source:record.source})) {
      if(value)dl.append(text("dt",label),text("dd",value));
    }
    card.append(dl);
    if(record.receipt)card.append(text("pre",JSON.stringify(record.receipt,null,2)));
    if(["executing","needs_attention"].includes(record.status))card.append(text("p","Verify the actual result in Vault before preparing another request. This request cannot be resubmitted.","notice"));
    if(record.status==="pending") {
      const actions=text("div","","request-actions"), review=text("button","Review & approve →"), reject=text("button","Reject","reject");
      review.onclick=async()=>{review.disabled=true;try {const data=await api("/api/admin/review",{request_id:record.id});location.assign(data.review_url);}catch(e){$("status").textContent=e.message;review.disabled=false;}};
      reject.onclick=async()=>{if(!confirm("Reject this pending request? No Vault operation will run."))return;reject.disabled=true;try{await api("/api/admin/reject",{request_id:record.id});await refresh();}catch(e){$("status").textContent=e.message;reject.disabled=false;}};
      actions.append(review,reject);card.append(actions);
    }
    $("requests").append(card);
  }
  $("previous").disabled=offset===0;$("next").disabled=nextOffset===null;$("page-label").textContent="Page "+(offset/100+1);
}
async function refresh() {
  $("status").textContent="Loading review requests…";
  try {const session=await api("/api/admin/session");$("identity").textContent="Approved policies: "+session.policies.join(", ")+" · Session expires "+new Date(session.expires_at*1000).toLocaleTimeString();
    const data=await api("/api/admin/requests?offset="+offset);records=data.requests;nextOffset=data.next_offset;$("login-panel").hidden=true;$("queue-panel").hidden=false;$("status").textContent="";display();
  }catch(e){$("status").textContent=e.message;}
}
$("login-form").onsubmit=async(event)=>{event.preventDefault();$("login-button").disabled=true;const body={vault_token:$("admin-token").value};try{await api("/api/admin/login",body);offset=0;await refresh();}catch(e){$("status").textContent=e.message;}finally{body.vault_token="";$("admin-token").value="";$("login-button").disabled=false;}};
$("logout").onclick=async()=>{try{await api("/api/admin/logout",{});records=[];$("requests").replaceChildren();$("queue-panel").hidden=true;$("login-panel").hidden=false;$("status").textContent="Signed out.";}catch(e){$("status").textContent=e.message;}};
$("refresh").onclick=refresh;$("previous").onclick=()=>{offset=Math.max(0,offset-100);refresh();};$("next").onclick=()=>{if(nextOffset!==null){offset=nextOffset;refresh();}};
for(const button of document.querySelectorAll("[data-filter]"))button.onclick=()=>{filter=button.dataset.filter;for(const item of document.querySelectorAll("[data-filter]"))item.classList.toggle("selected",item===button);display();};
window.addEventListener("pagehide",()=>{$("admin-token").value="";});
refresh();

(async()=>{try{const config=await api("/api/admin/config");$("vault-target").textContent="Vault: "+config.vault_address+" · Namespace: "+(config.namespace || "root");$("allowed-policies").textContent=config.approved_policies.join(", ");if(config.website_origin){$("brand-link").href=config.website_origin;$("catalog-link").href=config.website_origin;}}catch(e){$("status").textContent=e.message;}})();
