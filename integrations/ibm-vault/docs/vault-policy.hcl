# Example only. Customize these exact mount and secret paths for each team/user.
# Vault namespace is selected by the server, not by the LLM or browser.
# Do not grant a root token or attach this policy to a shared chatbot identity.

# Read the engine type and version for compatibility checks.
path "sys/mounts/onboard-payments" {
  capabilities = ["read", "create", "update"]
  # Only needed for engine onboarding. Remove create/update for secret-only users.
  # Vault requires update for enabling engines; the bridge exposes no tune/delete.
}

# Create-only protection is additionally enforced with KV v2 options.cas = 0.
# KV v2 commonly requires update alongside create; CAS prevents replacement.
path "onboard-payments/data/dev/*" {
  capabilities = ["create", "update"]
}

# No read on secret data, delete, list, policy write or arbitrary mount access.
