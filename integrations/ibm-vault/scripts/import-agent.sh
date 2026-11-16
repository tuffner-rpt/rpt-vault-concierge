#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v orchestrate >/dev/null || { echo "Install the IBM ADK and activate your Orchestrate environment first." >&2; exit 1; }
# Requires rpt_vault_bridge connection to be configured in draft and live first.
orchestrate tools import -k python -f watsonx/tools.py -r watsonx/requirements.txt -a rpt_vault_bridge
orchestrate agents import -f watsonx/agent.yaml
orchestrate tools import -k python -f watsonx/kv_mount_tools.py -r watsonx/requirements.txt -a rpt_vault_bridge
orchestrate agents import -f watsonx/kv-mount-agent.yaml
echo "Imported tools and draft agents. Test in draft before deploying to Live."
