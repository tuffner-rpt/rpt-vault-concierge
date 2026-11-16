"""Validate local schemas with IBM's installed ADK without contacting a tenant."""
import sys
from pathlib import Path

import yaml
from ibm_watsonx_orchestrate.agent_builder.agents.agent import Agent
from ibm_watsonx_orchestrate.cli.commands.connections.connections_controller import (
    ConnectionConfiguration,
    _validate_connections_spec_content,
)

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
agent = Agent.from_spec(str(root / "watsonx/agent.yaml"))
print(f"Valid agent schema: {agent.name} ({agent.llm})")

import watsonx.tools as tools

for name in agent.tools:
    tool = getattr(tools, name)
    assert type(tool).__name__ == "PythonTool", name
    print(f"Valid tool schema: {name}")

with open(root / "watsonx/connection.yaml") as source:
    spec = yaml.safe_load(source)
_validate_connections_spec_content(spec)
for environment, configuration in spec["environments"].items():
    ConnectionConfiguration.model_validate({**configuration, "environment": environment, "app_id": spec["app_id"]})
    print(f"Valid connection schema: {environment}")
print("Local schemas only; tenant import and model availability are not verified.")
