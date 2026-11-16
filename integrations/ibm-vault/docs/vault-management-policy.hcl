# Example for a trusted team's full engine management within onboard-team-*.
# This policy intentionally permits reading secrets and destructive engine APIs
# within that namespace. Give other users a narrower policy for their actual role.
# Types are unrestricted; paths remain constrained. No policy/plugin/auth admin.

path "sys/plugins/catalog" {
  capabilities = ["read"]
}

path "sys/mounts/onboard-team-*" {
  capabilities = ["read", "create", "update", "delete"]
}

path "onboard-team-*" {
  capabilities = ["read", "create", "update", "delete", "list", "patch"]
}

# When scoped further to a single engine, include read access for its mount help
# (GET /onboard-team-name?help=1) and mount metadata/type compatibility check.
