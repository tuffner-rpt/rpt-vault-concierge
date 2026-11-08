"""Vault-policy-gated administrative review queue. Never persists Vault credentials."""
import hashlib
import hmac
import json
import os
import time
import uuid

import httpx
import jwt
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr

RETENTION = 7 * 86400
COOKIE = "rpt_vault_admin"
CREATE = '''-- rpt_request_create
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[4])
redis.call('ZADD', KEYS[2], ARGV[2], ARGV[3])
redis.call('EXPIRE', KEYS[2], ARGV[4])
return 1'''
TRANSITION = '''-- rpt_request_transition
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local record = cjson.decode(raw)
if record.status ~= ARGV[1] then return 0 end
record.status = ARGV[2]
record.updated_at = tonumber(ARGV[3])
record.reviewer = ARGV[4]
if ARGV[5] ~= '' then record.receipt = cjson.decode(ARGV[5]) end
redis.call('SET', KEYS[1], cjson.encode(record), 'KEEPTTL')
return 1'''


def bridge():
    from api import index
    return index


def enabled():
    return True  # Administrator approval is mandatory in the deployed application.


def policies():
    return {p.strip() for p in os.getenv("ADMIN_REVIEW_VAULT_POLICIES", "hcp-root,root").split(',') if p.strip()}


def target():
    b = bridge()
    return b.trusted_origin("VAULT_ADDR") + "|" + os.getenv("VAULT_NAMESPACE", "")


def prefix():
    return "rpt-vault:requests:" + hashlib.sha256(target().encode()).hexdigest()[:20]


def record_key(request_id):
    try:
        uuid.UUID(request_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "Invalid request identifier") from None
    return prefix() + ":" + request_id


def session_key():
    return hmac.new(bridge().signing_key(), b"admin-review-session", hashlib.sha256).digest()


def intent_signature(record):
    data = {k: record[k] for k in ("id", "plan", "created_at", "target")}
    return hmac.new(bridge().signing_key(), json.dumps(data, sort_keys=True, separators=(',', ':')).encode(), hashlib.sha256).hexdigest()


async def register(body):
    if not enabled():
        return
    b = bridge()
    now = int(time.time())
    record = {"id": body["id"], "plan": body["plan"], "created_at": now, "updated_at": now,
              "target": target(), "status": "pending", "source": "IBM Granite chat", "requester": "Not identity-verified"}
    record["signature"] = intent_signature(record)
    result = await b.review_store(["EVAL", CREATE, "2", record_key(record['id']), prefix(), json.dumps(record), str(now), record['id'], str(RETENTION)])
    if result != 1:
        raise HTTPException(503, "The review request could not be queued. No Vault change was made.")


async def get_record(request_id, raw=None):
    if raw is None:
        raw = await bridge().review_store(["GET", record_key(request_id)])
    try:
        record = json.loads(raw)
        if record['id'] != request_id or record['target'] != target() or not hmac.compare_digest(record['signature'], intent_signature(record)):
            raise ValueError()
        bridge().Plan.model_validate(record['plan']).check_action()
        return record
    except (TypeError, ValueError, KeyError):
        raise HTTPException(404, "Review request not found or no longer valid") from None


def require_admin(request: Request):
    b = bridge()
    try:
        claims = jwt.decode(request.cookies.get(COOKIE, ''), session_key(), algorithms=['HS256'], audience=b.trusted_origin('APP_ORIGIN') + '/admin', options={'require': ['sub', 'exp', 'iat', 'target', 'policies']})
        if claims['target'] != target() or not policies().intersection(claims['policies']):
            raise ValueError()
        return claims
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(401, "Administrator sign-in required. Open Review & approve and sign in with an approved Vault admin token.") from None


def ticket_id(ticket):
    b = bridge()
    b.read_plan(ticket)
    import base64
    raw = ticket.split('.')[0]
    return json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))['id']


async def transition(request_id, before, after, actor, receipt=None):
    result = await bridge().review_store(['EVAL', TRANSITION, '1', record_key(request_id), before, after, str(int(time.time())), actor,
                                          json.dumps(receipt) if receipt is not None else ''])
    if result != 1:
        raise HTTPException(409, "This request is no longer pending or has already been submitted. Refresh the review queue and verify Vault before retrying.")


async def begin(ticket, actor):
    request_id = ticket_id(ticket)
    record = await get_record(request_id)
    if bridge().Plan.model_validate(record['plan']).model_dump() != bridge().read_plan(ticket).model_dump():
        raise HTTPException(409, "The plan does not match the queued request")
    await transition(request_id, 'pending', 'executing', actor['sub'])
    return request_id


async def finish(request_id, actor, result=None, error=None):
    # Persist metadata only. Secret engine outputs and credentials stay out of the queue.
    receipt = ({k: result[k] for k in ('status', 'mount', 'engine', 'path', 'version', 'endpoint', 'method') if k in result}
               if result is not None else {'status': 'outcome_requires_verification', 'http_status': error})
    await transition(request_id, 'executing', 'completed' if result is not None else 'needs_attention', actor['sub'], receipt)


class LoginInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    vault_token: SecretStr = Field(min_length=1, max_length=4096)


class RequestInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(min_length=36, max_length=36)


def install(app):
    @app.get('/admin')
    def page():
        return FileResponse(bridge().ROOT / 'web/admin.html')

    @app.get('/api/admin/config')
    def config():
        b = bridge()
        return {'vault_address': b.trusted_origin('VAULT_ADDR'), 'namespace': os.getenv('VAULT_NAMESPACE', ''),
                'approved_policies': sorted(policies()), 'website_origin': b.trusted_origin('WEBSITE_ORIGIN') if os.getenv('WEBSITE_ORIGIN') else ''}

    @app.post('/api/admin/login')
    async def login(body: LoginInput, request: Request):
        b = bridge()
        b.same_origin(request)
        token = body.vault_token.get_secret_value()
        b.validate_token(token)
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
            result = await b.vault_request(client, 'GET', 'auth/token/lookup-self', token)
        data = result.get('data', {})
        approved = policies().intersection(set(data.get('policies', [])) | set(data.get('identity_policies', [])))
        if not approved or not data.get('accessor'):
            raise HTTPException(403, 'Your Vault token does not carry an approved administrator policy.')
        ttl = data.get('ttl', 0)
        duration = min(900, int(ttl)) if ttl else (900 if 'root' in approved else 0)
        if duration < 1:
            raise HTTPException(403, 'Your Vault administrator token has expired.')
        now = int(time.time())
        claims = {'sub': hashlib.sha256(data['accessor'].encode()).hexdigest(), 'iat': now, 'exp': now + duration,
                  'aud': b.trusted_origin('APP_ORIGIN') + '/admin', 'target': target(), 'policies': sorted(approved)}
        signed = jwt.encode(claims, session_key(), algorithm='HS256')
        response = JSONResponse({'expires_at': now + duration, 'policies': sorted(approved)})
        response.set_cookie(COOKIE, signed, secure=b.trusted_origin('APP_ORIGIN').startswith('https:'), httponly=True, samesite='strict', path='/', max_age=duration)
        return response

    @app.get('/api/admin/session')
    def session(request: Request):
        actor = require_admin(request)
        return {'policies': actor['policies'], 'expires_at': actor['exp']}

    @app.post('/api/admin/logout')
    def logout(request: Request):
        bridge().same_origin(request)
        response = JSONResponse({'status': 'signed_out'})
        response.delete_cookie(COOKIE, path='/', secure=bridge().trusted_origin('APP_ORIGIN').startswith('https:'), httponly=True, samesite='strict')
        return response

    @app.get('/api/admin/requests')
    async def requests(request: Request, offset: int = 0):
        require_admin(request)
        if not 0 <= offset <= 100000:
            raise HTTPException(422, 'Invalid page offset')
        b = bridge()
        await b.review_store(['ZREMRANGEBYSCORE', prefix(), '-inf', str(int(time.time()) - RETENTION)])
        ids = await b.review_store(['ZREVRANGE', prefix(), str(offset), str(offset + 99)])
        records = []
        raw_records = await b.review_store(["MGET", *[record_key(i) for i in ids]]) if ids else []
        for request_id, raw in zip(ids or [], raw_records):
            if raw is None:
                continue
            try:
                record = await get_record(request_id, raw)
                records.append({k: v for k, v in record.items() if k not in {'signature', 'target'}})
            except HTTPException as error:
                if error.status_code != 404:
                    raise
        return {'requests': records, 'offset': offset, 'next_offset': offset + 100 if len(ids or []) == 100 else None, 'retention_days': 7}

    @app.post('/api/admin/review')
    async def review(body: RequestInput, request: Request):
        b = bridge()
        b.same_origin(request)
        require_admin(request)
        record = await get_record(body.request_id)
        if record['status'] != 'pending':
            raise HTTPException(409, 'Only pending requests can be opened for approval. Verify submitted outcomes in Vault.')
        return await b.issue_plan(b.Plan.model_validate(record['plan']), request_id=record['id'], queue=False)

    @app.post('/api/admin/reject')
    async def reject(body: RequestInput, request: Request):
        bridge().same_origin(request)
        actor = require_admin(request)
        await get_record(body.request_id)
        await transition(body.request_id, 'pending', 'rejected', actor['sub'])
        return {'status': 'rejected'}
