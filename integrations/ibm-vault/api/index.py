"""Vercel ASGI entry point; also run with uvicorn api.index:app."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
import jwt
from api import admin as admin_review
from jsonschema import Draft4Validator, ValidationError, SchemaError
from referencing.exceptions import Unresolvable
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="RPT Vault Onboarding Bridge", docs_url=None, redoc_url=None, openapi_url=None)
ENGINES = {
    "kv-v1": {"type": "kv", "options": {"version": "1"}, "ready": "KV v1 operations require the secure engine operation form."},
    "kv-v2": {"type": "kv", "options": {"version": "2"}, "ready": "Supports create-only versioned secret plans; Vault mount and caller access are unverified."},
    "transit": {"type": "transit", "options": {}, "ready": "Manage keys and cryptographic operations using the live engine API schema."},
    "database": {"type": "database", "options": {}, "ready": "Manage database connections, roles and credential operations using the live engine API schema."},
    "pki": {"type": "pki", "options": {}, "ready": "Manage issuers, certificate roles and issuance using the live engine API schema."},
}
for _engine in ("ad", "alicloud", "aws", "azure", "consul", "gcp", "gcpkms", "keymgmt", "kmip", "kubernetes", "ldap", "mongodbatlas", "nomad", "openldap", "rabbitmq", "ssh", "terraform", "totp", "transform"):
    ENGINES[_engine] = {"type": _engine, "options": {}, "ready": "Configure and manage through this engine's live API schema in the secure form."}


def engine_spec(engine: str) -> dict:
    return ENGINES.get(engine, {"type": engine, "options": {}, "ready": "Registered custom plugin: operations require its live Vault API schema."})


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
    action: Literal["enable_engine", "create_secret", "engine_operation", "tune_engine", "disable_engine"]
    engine: str = Field(min_length=1, max_length=100)
    mount: str = Field(min_length=2, max_length=100)
    secret_path: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=240)
    business_unit_id: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9_.-]*$")
    endpoint: str = Field(default="", max_length=400)
    method: Literal["GET", "LIST", "POST", "PUT", "PATCH", "DELETE"] = "POST"

    @field_validator("engine")
    @classmethod
    def valid_engine(cls, value):
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", value) or value in {"sys", "system", "identity", "cubbyhole", "auth"}:
            raise ValueError("Use a mountable secrets engine or registered secrets plugin name")
        return "kv-v2" if value == "kv" else value

    @field_validator("mount")
    @classmethod
    def valid_mount(cls, value):
        prefix = os.getenv("ALLOWED_MOUNT_PREFIX", "onboard-")
        if not prefix or not re.fullmatch(r"[a-z][a-z0-9_-]*", value) or not value.startswith(prefix):
            raise ValueError(f"Mount must be a single lowercase segment starting with {prefix}")
        if value in {"sys", "auth", "identity", "cubbyhole"}:
            raise ValueError("Reserved mount")
        return value

    @field_validator("secret_path", "endpoint")
    @classmethod
    def valid_path(cls, value):
        if value and (not re.fullmatch(r"[A-Za-z0-9_.@~/-]+", value) or any(p in {"", ".", ".."} for p in value.split("/"))):
            raise ValueError("Secret path must contain safe nonempty path segments")
        return value

    def check_action(self):
        if self.action == "create_secret" and (self.engine != "kv-v2" or not self.secret_path):
            raise HTTPException(422, "Secrets require KV v2 and a secret path")
        if self.action != "create_secret" and self.secret_path:
            raise HTTPException(422, "Only secret creation plans can include a secret path")
        if self.action == "engine_operation" and not self.endpoint:
            raise HTTPException(422, "An engine operation requires an explicit relative endpoint")
        if self.action != "engine_operation" and (self.endpoint or self.method != "POST"):
            raise HTTPException(422, "Endpoint and method apply only to engine operations")
        # Keep KV v2 creation's atomic no-overwrite guarantee; don't bypass it through the generic API.
        if self.action == "engine_operation" and self.engine == "kv-v2" and self.method in {"POST", "PUT", "PATCH"} and self.endpoint.startswith("data/"):
            raise HTTPException(422, "Use create_secret for KV v2 data writes; existing values cannot be overwritten")


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


async def issue_plan(plan: Plan, *, request_id: str | None = None, queue: bool = True) -> dict:
    plan.check_action()
    body = {"plan": plan.model_dump(), "exp": int(time.time()) + 600, "id": request_id or str(uuid.uuid4()), "aud": trusted_origin("APP_ORIGIN")}
    data = encode(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    signature = encode(hmac.new(signing_key(), data.encode(), hashlib.sha256).digest())
    ticket = f"{data}.{signature}"
    review_id = secrets.token_urlsafe(16)
    if queue:
        await admin_review.register(body)
    await store_review(review_id, ticket)
    return {"plan": body["plan"], "expires_at": body["exp"], "review_url": f"{body['aud']}/onboard#review={review_id}", "status": "awaiting_admin_review" if admin_review.enabled() else "awaiting_browser_review", "admin_queue_url": trusted_origin("APP_ORIGIN") + "/admin", "note": "Nothing has been changed in Vault. An approved administrator must review and authorize execution in the secure form."}


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
    operation_json: SecretStr = Field(default=SecretStr("{}"), max_length=60000)
    confirmation_text: str = Field(default="", max_length=600)


class InspectInput(TicketInput):
    vault_token: SecretStr = Field(min_length=1, max_length=4096)


def confirmation_phrase(plan: Plan) -> str:
    if plan.action == "disable_engine":
        return f"DISABLE {plan.mount}"
    if plan.action == "engine_operation" and plan.method == "DELETE":
        return f"DELETE {plan.mount}/{plan.endpoint}"
    if plan.action == "engine_operation" and plan.method in {"POST", "PUT", "PATCH"}:
        return f"EXECUTE {plan.method} {plan.mount}/{plan.endpoint}"
    return ""


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
    return {"catalog_source": "static_bridge_capabilities", "vault_queried": False, "availability_verified": False, "notice": "These are supported engine examples, not installed or available engines retrieved from Vault. Mounts, licenses, provider configuration and caller access have not been checked. Use Inspect in the secure review form with your scoped Vault token to query Vault.", "engines": {name: {"type": spec["type"], "options": spec["options"], "capability": spec["ready"], "vault_availability": "unverified"} for name, spec in ENGINES.items()}, "custom_plugins": "Any registered mountable secrets plugin; availability is checked against Vault at execution.", "system_managed": ["cubbyhole", "identity", "system"], "mount_prefix": os.getenv("ALLOWED_MOUNT_PREFIX", "onboard-"), "operations": ["enable_engine", "create_secret", "engine_operation", "tune_engine", "disable_engine"], "secret_support": "KV v2 data writes remain create-only. Other engine operations use live OpenAPI validation and caller ACLs. Destructive operations require typed confirmation."}


@app.post("/api/plans")
async def prepare(plan: Plan, request: Request):
    tool_authorized(request)
    return await issue_plan(plan)


class KVMountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_unit_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    mount: str = Field(min_length=2, max_length=100)
    kv_version: Literal["1", "2"]

    @field_validator("mount")
    @classmethod
    def valid_mount(cls, value):
        return Plan.valid_mount(value)


@app.post("/api/kv-mount-plans")
async def prepare_kv_mount(body: KVMountInput, request: Request):
    tool_authorized(request)
    # This dedicated tool cannot select another action, engine, or secret payload.
    plan = Plan(action="enable_engine", engine=f"kv-v{body.kv_version}",
                mount=body.mount, business_unit_id=body.business_unit_id,
                description="KV mount onboarding")
    return await issue_plan(plan)


async def review_store(command: list):
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
            response = await client.post(trusted_origin("UPSTASH_REDIS_REST_URL"), headers={"Authorization": "Bearer " + required("UPSTASH_REDIS_REST_TOKEN")}, json=command)
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            raise ValueError()
        return data.get("result")
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Secure review link storage is unavailable. No Vault change was made.") from None


async def store_review(review_id: str, ticket: str):
    result = await review_store(["SET", "rpt-vault:review:" + review_id, ticket, "EX", "600", "NX"])
    if result != "OK":
        raise HTTPException(503, "Secure review link could not be prepared. No Vault change was made.")


async def resolve_review(review_id: str) -> str:
    ticket = await review_store(["GET", "rpt-vault:review:" + review_id])
    if not isinstance(ticket, str):
        raise HTTPException(400, "Invalid or expired review link. Ask the agent for a new one.")
    return ticket


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str = Field(pattern=r"^[A-Za-z0-9_-]{22}$")


@app.post("/api/resolve")
async def resolve(body: ReviewInput, request: Request):
    same_origin(request)
    ticket = await resolve_review(body.review_id)
    read_plan(ticket)
    return {"ticket": ticket}


def access_requirements(plan: Plan) -> dict:
    """Describe exact request ACLs; never installs a policy or issues a token."""
    permissions = {f"sys/mounts/{plan.mount}": ["read"]}
    if plan.action == "enable_engine":
        permissions[f"sys/mounts/{plan.mount}"] = ["read", "create", "update", "sudo"]
        permissions["sys/plugins/catalog"] = ["read"]
    elif plan.action == "create_secret":
        permissions[f"{plan.mount}/data/{plan.secret_path}"] = ["create"]
    elif plan.action == "engine_operation":
        permissions[plan.mount] = ["read"]
        permissions[f"{plan.mount}/{plan.endpoint}"] = [{"GET": "read", "LIST": "list", "POST": "update", "PUT": "update", "PATCH": "patch", "DELETE": "delete"}[plan.method]]
        if plan.method in {"POST", "PUT"}:
            permissions[f"{plan.mount}/{plan.endpoint}"].insert(0, "create")
    elif plan.action == "tune_engine":
        permissions[plan.mount] = ["read"]
        permissions[f"sys/mounts/{plan.mount}/tune"] = ["read", "update", "sudo"]
    elif plan.action == "disable_engine":
        permissions[plan.mount] = ["read"]
        permissions[f"sys/mounts/{plan.mount}"] = ["read", "delete", "sudo"]
    policy = "\n\n".join(f"path {json.dumps(path)} {{\n  capabilities = {json.dumps(caps)}\n}}" for path, caps in permissions.items())
    return {"policy_hcl": policy, "namespace": os.getenv("VAULT_NAMESPACE", ""),
            "note": "A Vault administrator must review and attach these request-specific permissions to a short-lived token in this namespace. Inspect does not issue tokens or grant access. Engine plugins can require additional permissions; provider configuration and licenses are separate."}


@app.post("/api/preview")
def preview(body: TicketInput, request: Request):
    same_origin(request)
    plan = read_plan(body.ticket)
    return {"plan": plan.model_dump(), "vault_address": trusted_origin("VAULT_ADDR"), "namespace": os.getenv("VAULT_NAMESPACE", ""), "scope": engine_spec(plan.engine)["ready"], "confirmation_phrase": confirmation_phrase(plan), "access_requirements": access_requirements(plan), "admin_review_required": admin_review.enabled()}


async def vault_request(client, method, path, token, payload=None, allow_missing=False):
    headers = {"X-Vault-Token": token, "X-Vault-Request": "true"}
    namespace = os.getenv("VAULT_NAMESPACE", "")
    if namespace:
        headers["X-Vault-Namespace"] = namespace
    if method == "PATCH":
        headers["Content-Type"] = "application/merge-patch+json"
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
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        # Some published engine endpoints return PEM, text or binary data.
        return {"data": {"raw_body_base64": base64.b64encode(response.content).decode(), "content_type": response.headers.get("content-type", "application/octet-stream")}}


def validate_token(token: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", token):
        raise HTTPException(422, "Invalid Vault token format")


async def checked_mount(client, plan, token):
    current = await vault_request(client, "GET", f"sys/mounts/{plan.mount}", token, allow_missing=True)
    if current is not None:
        current = current.get("data", current)
        spec = engine_spec(plan.engine)
        if current.get("type") != spec["type"] or (plan.engine in {"kv-v1", "kv-v2"} and str((current.get("options") or {}).get("version", "1")) != spec["options"]["version"]):
            raise HTTPException(409, "An incompatible engine already exists at this mount")
    return current


async def engine_document(client, plan, token):
    if await checked_mount(client, plan, token) is None:
        raise HTTPException(409, "Enable this engine before managing it")
    result = await vault_request(client, "GET", f"{plan.mount}?help=1", token)
    document = result.get("openapi", {})
    try:
        document = json.loads(document) if isinstance(document, str) else document
        if not isinstance(document, dict) or not isinstance(document.get("paths"), dict):
            raise ValueError()
        # Never fetch remote JSON-schema references supplied by a plugin.
        def check_refs(value):
            if isinstance(value, dict):
                if "$ref" in value and (not isinstance(value["$ref"], str) or not value["$ref"].startswith("#/")):
                    raise ValueError()
                for child in value.values():
                    check_refs(child)
            elif isinstance(value, list):
                for child in value:
                    check_refs(child)
        check_refs(document)
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(409, "The engine must publish a valid OpenAPI schema with local references") from None
    return document


def operation_definition(document, plan):
    matches = []
    for path, item in document["paths"].items():
        # Vault mount help returns paths relative to the mount.
        pattern = "/" + plan.endpoint
        template = path.rstrip("/")
        pieces = re.split(r"(\{[^}]+\})", template)
        regex = "".join(".+" if piece in {"{path}", "{prefix}"} else "[^/]+" if piece.startswith("{") else re.escape(piece) for piece in pieces)
        if re.fullmatch(regex, pattern):
            method = "get" if plan.method == "LIST" else plan.method.lower()
            operation = item.get(method)
            if operation:
                if plan.method == "LIST" and not any(p.get("name") == "list" and p.get("in") == "query" for p in operation.get("parameters", []) + item.get("parameters", [])):
                    continue
                # Literal paths take precedence over parameterized paths.
                matches.append((template.count("{"), operation))
    if not matches:
        raise HTTPException(422, "This endpoint and method are not published by the mounted engine")
    return min(matches, key=lambda match: match[0])[1]


def request_schema(document, operation):
    body = operation.get("requestBody", {})
    if "$ref" in body:
        try:
            value = document
            for part in body["$ref"][2:].split("/"):
                value = value[part.replace("~1", "/").replace("~0", "~")]
            body = value
        except (KeyError, TypeError):
            raise HTTPException(409, "The engine request schema cannot be resolved") from None
    content = body.get("content", {})
    return (content.get("application/json") or content.get("application/merge-patch+json") or {}).get("schema", {"type": "object", "additionalProperties": False})


def validate_payload(document, schema, payload):
    try:
        Draft4Validator({"allOf": [schema], "components": document.get("components", {})}).validate(payload)
    except (ValidationError, SchemaError, ValueError, KeyError, RecursionError, Unresolvable):
        raise HTTPException(422, "Request JSON does not match the engine's published input schema. Check required fields and their types.") from None


async def claim_operation(client, ticket):
    # A durable atomic claim is required across Vercel instances before non-idempotent operations.
    origin = trusted_origin("UPSTASH_REDIS_REST_URL")
    key = "rpt-vault:used:" + hashlib.sha256(ticket.encode()).hexdigest()
    try:
        response = await client.post(origin, headers={"Authorization": "Bearer " + required("UPSTASH_REDIS_REST_TOKEN")}, json=["SET", key, "used", "EX", "900", "NX"])
        if response.status_code != 200:
            raise ValueError()
        result = response.json()
        if result.get("error"):
            raise ValueError()
        if result.get("result") != "OK":
            raise HTTPException(409, "This operation plan has already been submitted. Verify the Vault result before requesting a new plan.")
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Durable operation approval storage is unavailable; no engine operation was sent") from None


@app.post("/api/inspect")
async def inspect_engine(body: InspectInput, request: Request):
    same_origin(request)
    plan = read_plan(body.ticket)
    token = body.vault_token.get_secret_value()
    validate_token(token)
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
        if plan.action == "enable_engine":
            result = await vault_request(client, "GET", "sys/plugins/catalog", token)
            return {"available_engines": sorted(set(result.get("data", {}).get("secret", [])) | {"database", "kv-v1", "kv-v2"}), "note": "Enterprise engines and custom plugins require their licenses and registered binaries. Catalog access does not grant mount permissions."}
        document = await engine_document(client, plan, token)
        if plan.action == "engine_operation":
            operation = operation_definition(document, plan)
            return {"endpoint": plan.endpoint, "method": plan.method, "summary": operation.get("summary", ""), "request_schema": request_schema(document, operation), "components": document.get("components", {}), "note": "Enter credentials and operation input only in the JSON field below. Outputs may contain secrets and stay in this secure form."}
        return {"endpoints": {path: {method.upper(): operation.get("summary", "") for method, operation in item.items() if method in {"get", "post", "put", "patch", "delete"}} for path, item in document["paths"].items()}}


@app.post("/api/execute")
async def execute(body: ExecuteInput, request: Request):
    same_origin(request)
    plan = read_plan(body.ticket)
    token = body.vault_token.get_secret_value()
    validate_token(token)
    if plan.action != "create_secret" and body.secret_data:
        raise HTTPException(422, "Only KV v2 creation plans can include secret fields")
    phrase = confirmation_phrase(plan)
    if phrase and body.confirmation_text != phrase:
        raise HTTPException(422, "Type the exact destructive-operation confirmation shown in the form")
    try:
        payload = json.loads(body.operation_json.get_secret_value())
        if not isinstance(payload, dict):
            raise ValueError()
    except (ValueError, RecursionError):
        raise HTTPException(422, "Operation input must be a JSON object") from None
    if plan.action in {"enable_engine", "create_secret", "disable_engine"} and payload:
        raise HTTPException(422, "This plan does not accept operation JSON")
    if plan.action == "create_secret" and (not 1 <= len(body.secret_data) <= 64 or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", k) for k in body.secret_data)):
        raise HTTPException(422, "Provide 1 to 64 named secret fields")
    actor = admin_review.require_admin(request) if admin_review.enabled() else None
    request_id = await admin_review.begin(body.ticket, actor) if actor else None
    try:
        result = await execute_validated(plan, token, payload, body)
    except HTTPException as error:
        if request_id:
            try:
                await admin_review.finish(request_id, actor, error=error.status_code)
            except HTTPException:
                pass  # Remain executing and block resubmission if status storage is unavailable.
        raise
    except Exception:
        if request_id:
            try:
                await admin_review.finish(request_id, actor, error=500)
            except HTTPException:
                pass
        raise HTTPException(503, "Outcome requires verification in Vault. Do not resubmit this request.") from None
    if request_id:
        try:
            await admin_review.finish(request_id, actor, result=result)
        except HTTPException:
            raise HTTPException(503, "Vault may have completed the operation, but its queue status could not be saved. Verify Vault before any retry.") from None
    return result


async def execute_validated(plan, token, payload, body):
    # No ambient Vault credentials; each request acts with the caller's ACLs.
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
        current = await checked_mount(client, plan, token)
        spec = engine_spec(plan.engine)
        if plan.action == "enable_engine":
            status = "already_exists"
            if current is None:
                # Vault's mount API performs the final plugin/license availability check.
                await vault_request(client, "POST", f"sys/mounts/{plan.mount}", token, {"type": spec["type"], "options": spec["options"], "description": plan.description})
                status = "created"
            return {"status": status, "mount": plan.mount, "engine": plan.engine, "scope": spec["ready"]}
        if current is None:
            raise HTTPException(409, "Enable this engine first, then manage its secrets or configuration")
        if plan.action in {"engine_operation", "tune_engine", "disable_engine"}:
            if plan.action == "engine_operation":
                document = await engine_document(client, plan, token)
                operation = operation_definition(document, plan)
                validate_payload(document, request_schema(document, operation), payload)
                if plan.method in {"GET", "LIST", "DELETE"} and payload:
                    raise HTTPException(422, "GET, LIST and DELETE operations do not accept JSON input")
                path, method = f"{plan.mount}/{plan.endpoint}", plan.method
            elif plan.action == "tune_engine":
                schema = {"type": "object", "minProperties": 1, "additionalProperties": False, "properties": {"default_lease_ttl": {"type": "string", "pattern": "^[0-9]+[smh]$"}, "max_lease_ttl": {"type": "string", "pattern": "^[0-9]+[smh]$"}, "description": {"type": "string", "maxLength": 240}}}
                validate_payload({}, schema, payload)
                path, method = f"sys/mounts/{plan.mount}/tune", "POST"
            else:
                path, method = f"sys/mounts/{plan.mount}", "DELETE"
            await claim_operation(client, body.ticket)
            result = await vault_request(client, method, path, token, payload if method in {"POST", "PUT", "PATCH"} else None)
            return {"status": "completed", "engine": plan.engine, "mount": plan.mount, "endpoint": path, "method": method, "sensitive_result": {k: result[k] for k in ("data", "lease_id", "lease_duration", "renewable", "warnings") if k in result}}
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


@app.get("/api/kv-mount-chat-config")
def kv_mount_chat_config():
    config = chat_config()
    # Fail closed when the restricted agent is not deployed; never use the general agent.
    config["chatOptions"] = {"agentId": required("WXO_KV_MOUNT_AGENT_ID"),
                             "agentEnvironmentId": required("WXO_KV_MOUNT_AGENT_ENVIRONMENT_ID")}
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
    if name not in {"onboard.js", "chat.js", "styles.css", "admin.js", "admin.css"}:
        raise HTTPException(404)
    return FileResponse(ROOT / "web" / name)


admin_review.install(app)
