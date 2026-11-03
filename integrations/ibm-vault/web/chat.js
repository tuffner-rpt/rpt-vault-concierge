"use strict";
(async () => {
  const status = document.getElementById("chat-status");
  let chatSession = null;
  async function freshToken() {
    const response = await fetch("/api/chat-token", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ chat_session: chatSession }), credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error("Chat identity service is not configured. Contact the site administrator.");
    const result = await response.json();
    chatSession = result.chat_session;
    return result.token;
  }
  try {
    const response = await fetch("/api/chat-config", { cache: "no-store" });
    if (!response.ok) throw new Error("The IBM agent connection has not been configured yet.");
    const config = await response.json();
    config.token = await freshToken();
    config.chatOptions.onLoad = (instance) => {
      status.hidden = true;
      instance.on("authTokenNeeded", async (event, current) => {
        try { event.authToken = await freshToken(); current.updateAuthToken(event.authToken); }
        catch (error) { status.textContent = error.message; status.hidden = false; }
      });
    };
    window.wxOConfiguration = config;
    const script = document.createElement("script");
    script.src = `${config.hostURL}/wxochat/wxoLoader.js?embed=true`;
    script.addEventListener("load", () => window.wxoLoader.init());
    script.addEventListener("error", () => { status.textContent = "Could not load the IBM chat widget. Check the IBM host URL and network access."; });
    document.head.append(script);
  } catch (error) { status.textContent = error.message; }
})();
