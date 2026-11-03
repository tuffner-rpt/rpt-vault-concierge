"""Vercel ASGI entry point; also run with uvicorn api.index:app."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="RPT Vault Onboarding Bridge", docs_url=None, redoc_url=None, openapi_url=None)
ENGINES = {
    "kv-v2": {"type": "kv", "options": {"version": "2"}, "ready": "Ready for versioned secret creation."},
    "transit": {"type": "transit", "options": {}, "ready": "Mount only. Encryption keys must be configured separately."},
    "database": {"type": "database", "options": {}, "ready": "Mount only. Database connections and roles must be configured separately."},
    "pki": {"type": "pki", "options": {}, "ready": "Mount only. CA, URLs, and issuance roles must be configured separately."},
}


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(503, f"Server configuration missing: {name}")
    return value


def trusted_origin(name: str) -> str:
    value = required(name).rstrip("/")
    parts = urlsplit(value)
    local = parts.hostname in {"localhost", "127.0.0.1"}
    if (parts.scheme != "https" and not (parts.scheme == "http" and local)) or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path:
        raise HTTPException(503, f"Invalid origin configuration: {name}")
    return value


def signing_key() -> bytes:
    value = required("PLAN_SIGNING_KEY")
    if len(value) < 32:
        raise HTTPException(503, "PLAN_SIGNING_KEY must have at least 32 characters")
    return value.encode()


def same_origin(request: Request):
    if request.headers.get("origin") != trusted_origin("APP_ORIGIN"):
        raise HTTPException(403, "This operation must be submitted from the onboarding site")


def tool_authorized(request: Request):
    expected = required("WXO_BRIDGE_API_KEY")
    if len(expected) < 32:
        raise HTTPException(503, "WXO_BRIDGE_API_KEY must have at least 32 characters")
    if not hmac.compare_digest(request.headers.get("x-api-key", ""), expected):
        raise HTTPException(401, "Invalid bridge credentials")


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["enable_engine", "create_secret"]
    engine: Literal["kv-v2", "transit", "database", "pki"]
    mount: str = Field(min_length=2, max_length=100)
    secret_path: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=240)

    @field_validator("mount")
    @classmethod
    def valid_mount(cls, value):
        prefix = os.getenv("ALLOWED_MOUNT_PREFIX", "onboard-")
        if not prefix or not re.fullmatch(r"[a-z][a-z0-9_-]*", value) or not value.startswith(prefix):
            raise ValueError(f"Mount must be a single lowercase segment starting with {prefix}")
        if value in {"sys", "auth", "identity", "cubbyhole"}:
            raise ValueError("Reserved mount")
        return value

    @field_validator("secret_path")
    @classmethod
    def valid_path(cls, value):
        if value and (not re.fullmatch(r"[A-Za-z0-9_/-]+", value) or any(p in {"", ".", ".."} for p in value.split("/"))):
            raise ValueError("Secret path must contain safe nonempty path segments")
        return value

    def check_action(self):
        if self.action == "create_secret" and (self.engine != "kv-v2" or not self.secret_path):
            raise HTTPException(422, "Secrets require KV v2 and a secret path")
        if self.action == "enable_engine" and self.secret_path:
            raise HTTPException(422, "Engine plans must not include a secret path")


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def issue_plan(plan: Plan) -> dict:
    plan.check_action()
    body = {"plan": plan.model_dump(), "exp": int(time.time()) + 600, "id": str(uuid.uuid4()), "aud": trusted_origin("APP_ORIGIN")}
    data = encode(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    signature = encode(hmac.new(signing_key(), data.encode(), hashlib.sha256).digest())
    ticket = f"{data}.{signature}"
    return {"plan": body["plan"], "expires_at": body["exp"], "review_url": f"{body['aud']}/onboard#plan={ticket}", "status": "awaiting_browser_review", "note": "Nothing has been changed in Vault. Review and confirm in the secure form."}


def read_plan(ticket: str) -> Plan:
    try:
        data, signature = ticket.split(".")
        expected = encode(hmac.new(signing_key(), data.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        body = json.loads(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)))
        if body["exp"] <= time.time() or body["aud"] != trusted_origin("APP_ORIGIN"):
            raise ValueError()
        plan = Plan.model_validate(body["plan"])
        plan.check_action()
        return plan
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "Invalid or expired plan. Ask the agent for a new review link.") from None


class TicketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=1, max_length=5000)


class ExecuteInput(TicketInput):
    vault_token: SecretStr = Field(min_length=1, max_length=4096)
    confirmed: Literal[True]
    secret_data: dict[str, SecretStr] = Field(default_factory=dict)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    # Pydantic's default response includes input values. Never echo credentials or secrets.
    return JSONResponse(status_code=422, content={"detail": "Invalid request. Check the plan, confirmation, and input fields."})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.method == "POST":
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            return JSONResponse({"detail": "JSON content type required"}, status_code=415)
        # Bound chunked and regular bodies without logging them.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff", "Permissions-Policy": "camera=(), microphone=(), geolocation=()"})
    if request.url.path == "/chat":
        parent = os.getenv("WEBSITE_ORIGIN", "")
        if parent:
            parent = trusted_origin("WEBSITE_ORIGIN")
        response.headers["Content-Security-Policy"] = f"frame-ancestors 'self' {parent}; base-uri 'self'; object-src 'none'"
    else:
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'; object-src 'none'"
        response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "rpt-vault-onboarding", "vault_connected": False}


@app.get("/api/catalog")
def catalog():
    return {"engines": ENGINES, "mount_prefix": os.getenv("ALLOWED_MOUNT_PREFIX", "onboard-"), "secret_support": "KV v2 create-only; no read, update, or delete operations"}


@app.post("/api/plans")
def prepare(plan: Plan, request: Request):
    tool_authorized(request)
    return issue_plan(plan)


@app.post("/api/preview")
def preview(body: TicketInput, request: Request):
    same_origin(request)
    plan = read_plan(body.ticket)
    return {"plan": plan.model_dump(), "vault_address": trusted_origin("VAULT_ADDR"), "namespace": os.getenv("VAULT_NAMESPACE", ""), "scope": ENGINES[plan.engine]["ready"]}


async def vault_request(client, method, path, token, payload=None, allow_missing=False):
    headers = {"X-Vault-Token": token, "X-Vault-Request": "true"}
    namespace = os.getenv("VAULT_NAMESPACE", "")
    if namespace:
        headers["X-Vault-Namespace"] = namespace
    try:
        response = await client.request(method, trusted_origin("VAULT_ADDR") + "/v1/" + path, headers=headers, json=payload)
    except httpx.HTTPError:
        raise HTTPException(502, "Vault could not be reached. Outcome may be uncertain; verify in Vault before retrying.") from None
    if response.status_code == 404 and allow_missing:
        return None
    # Vault's mount lookup returns 400 (not 404) for an absent mount.
    # Match only this exact lookup error; other 400s must never imply absence.
    if response.status_code == 400 and allow_missing and method == "GET" and path.startswith("sys/mounts/"):
        try:
            missing_error = f"No secret engine mount at {path.removeprefix('sys/mounts/')}/"
            if response.json().get("errors") == [missing_error]:
                return None
        except ValueError:
            pass
    if response.status_code in {401, 403}:
        raise HTTPException(403, "Your Vault token does not authorize this operation")
    if response.status_code == 400:
        raise HTTPException(409, "Vault rejected the operation. The path may already exist, or the configuration is incompatible.")
    if response.status_code >= 300:
        raise HTTPException(502, "Vault could not complete the operation. Check Vault health and permissions.")
    return response.json() if response.content else {}


@app.post("/api/execute")
async def execute(body: ExecuteInput, request: Request):
    same_origin(request)
    plan = read_plan(body.ticket)
    token = body.vault_token.get_secret_value()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", token):
        raise HTTPException(422, "Invalid Vault token format")
    if plan.action == "enable_engine" and body.secret_data:
        raise HTTPException(422, "An engine plan cannot include secret values")
    if plan.action == "create_secret" and (not 1 <= len(body.secret_data) <= 64 or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", k) for k in body.secret_data)):
        raise HTTPException(422, "Provide 1 to 64 named secret fields")
    # No ambient Vault credentials; each request acts with the caller's ACLs.
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
        current = await vault_request(client, "GET", f"sys/mounts/{plan.mount}", token, allow_missing=True)
        spec = ENGINES[plan.engine]
        if current is not None:
            current = current.get("data", current)
            if current.get("type") != spec["type"] or (plan.engine == "kv-v2" and str((current.get("options") or {}).get("version")) != "2"):
                raise HTTPException(409, "An incompatible engine already exists at this mount")
        if plan.action == "enable_engine":
            status = "already_exists"
            if current is None:
                await vault_request(client, "POST", f"sys/mounts/{plan.mount}", token, {"type": spec["type"], "options": spec["options"], "description": plan.description})
                status = "created"
            return {"status": status, "mount": plan.mount, "engine": plan.engine, "scope": spec["ready"]}
        if current is None:
            raise HTTPException(409, "Enable the KV v2 engine first, then create the secret")
        data = {key: value.get_secret_value() for key, value in body.secret_data.items()}
        result = await vault_request(client, "POST", f"{plan.mount}/data/{plan.secret_path}", token, {"options": {"cas": 0}, "data": data})
        return {"status": "created", "mount": plan.mount, "path": plan.secret_path, "version": result.get("data", {}).get("version")}


@app.get("/api/chat-config")
def chat_config():
    host = trusted_origin("WXO_HOST_URL")
    config = {"hostURL": host, "orchestrationID": required("WXO_ORCHESTRATION_ID"), "rootElementID": "root", "showLauncher": False,
              "chatOptions": {"agentId": required("WXO_AGENT_ID"), "agentEnvironmentId": required("WXO_AGENT_ENVIRONMENT_ID")}}
    for env, field in [("WXO_CRN", "crn"), ("WXO_DEPLOYMENT_PLATFORM", "deploymentPlatform")]:
        if os.getenv(env):
            config[field] = os.environ[env]
    return config


class ChatTokenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_session: str | None = Field(default=None, max_length=200)


@app.post("/api/chat-token")
def chat_token(body: ChatTokenInput, request: Request):
    same_origin(request)
    # Anonymous planner identity grants no Vault access. Never use context for Vault authorization.
    cookie = body.chat_session or request.cookies.get("rpt_chat", "")
    try:
        subject, signature = cookie.split(".")
        uuid.UUID(subject)
        if not hmac.compare_digest(signature, hmac.new(signing_key(), subject.encode(), hashlib.sha256).hexdigest()):
            raise ValueError()
    except ValueError:
        subject = str(uuid.uuid4())
    signature = hmac.new(signing_key(), subject.encode(), hashlib.sha256).hexdigest()
    now = int(time.time())
    try:
        token = jwt.encode({"sub": subject, "iat": now, "exp": now + 300}, required("WXO_CHAT_PRIVATE_KEY").replace("\\n", "\n"), algorithm="RS256")
    except (ValueError, jwt.PyJWTError):
        raise HTTPException(503, "Chat signing key is not configured correctly") from None
    # In-memory session also works when third-party iframe cookies are blocked.
    response = JSONResponse({"token": token, "chat_session": f"{subject}.{signature}"})
    response.set_cookie("rpt_chat", f"{subject}.{signature}", secure=trusted_origin("APP_ORIGIN").startswith("https:"), httponly=True, samesite="lax", max_age=86400)
    return response


@app.get("/")
@app.get("/onboard")
def onboarding_page():
    return FileResponse(ROOT / "web" / "onboard.html")


@app.get("/chat")
def chat_page():
    return FileResponse(ROOT / "web" / "chat.html")


@app.get("/assets/{name}")
def asset(name: str):
    if name not in {"onboard.js", "chat.js", "styles.css"}:
        raise HTTPException(404)
    return FileResponse(ROOT / "web" / name)
