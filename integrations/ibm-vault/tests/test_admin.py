import asyncio
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from api import index as bridge
from api import admin

ORIGIN = 'https://bridge.example.com'
KEY = 'k' * 64
HEADERS = {'Origin': ORIGIN}


@pytest.fixture
def setup(monkeypatch):
    for key, value in {'APP_ORIGIN': ORIGIN, 'VAULT_ADDR': 'https://vault.example.com:8200', 'VAULT_NAMESPACE': 'admin', 'WEBSITE_ORIGIN':'https://site.example.com',
                       'PLAN_SIGNING_KEY':'s' * 64, 'WXO_BRIDGE_API_KEY':KEY, 'ALLOWED_MOUNT_PREFIX':'onboard-',
                       'ADMIN_REVIEW_REQUIRED':'true', 'ADMIN_REVIEW_VAULT_POLICIES':'hcp-root,root'}.items():
        monkeypatch.setenv(key, value)
    values, indexes, calls, mounts = {}, {}, [], set()
    from admin_store import MemoryReviewStore
    memory = MemoryReviewStore()
    values = memory.values
    storage = memory
    monkeypatch.setattr(bridge, 'review_store', storage)
    real_client = httpx.AsyncClient
    def vault(request):
        calls.append(request)
        token = request.headers.get('X-Vault-Token')
        path = request.url.path
        if path == '/v1/auth/token/lookup-self':
            if token == 'invalid-token': return httpx.Response(403, json={'errors':['permission denied']})
            policy = 'hcp-root' if token == 'admin-login-token' else 'default'
            return httpx.Response(200, json={'data':{'policies':[policy], 'accessor':'test-accessor', 'ttl':3600, 'id':token}})
        if token != 'scoped-execution-token': return httpx.Response(403, json={'errors':['permission denied']})
        if path.startswith('/v1/sys/mounts/'):
            mount = path.split('/')[-1]
            if request.method == 'GET':
                return httpx.Response(200, json={'data':{'type':'kv','options':{'version':'2'}}}) if mount in mounts else httpx.Response(400,json={'errors':[f'No secret engine mount at {mount}/']})
            if request.method == 'POST': mounts.add(mount); return httpx.Response(204)
        if '/data/' in path and request.method == 'POST': return httpx.Response(200,json={'data':{'version':1}})
        raise AssertionError(str(request.url))
    monkeypatch.setattr(bridge.httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(vault),**kw))
    with TestClient(bridge.app, base_url=ORIGIN) as client:
        yield client, values, calls, mounts


def login(client, token='admin-login-token'):
    return client.post('/api/admin/login', headers=HEADERS, json={'vault_token':token})


def prepare(client, **changes):
    response = client.post('/api/plans',headers={'X-API-Key':KEY},json={'action':'enable_engine','engine':'kv-v2','mount':'onboard-admin-test','description':'Reviewed request',**changes})
    assert response.status_code == 200, response.text
    review = parse_qs(urlsplit(response.json()['review_url']).fragment)['review'][0]
    resolved = client.post('/api/resolve',headers=HEADERS,json={'review_id':review})
    assert resolved.status_code == 200
    ticket = resolved.json()['ticket']
    request_id = admin.ticket_id(ticket)
    return request_id, ticket


def execute(client, ticket, **changes):
    return client.post('/api/execute',headers=HEADERS,json={'ticket':ticket,'vault_token':'scoped-execution-token','confirmed':True,**changes})


def test_queue_and_execution_require_admin(setup):
    client, values, calls, mounts = setup
    request_id, ticket = prepare(client)
    assert client.get('/api/admin/requests').status_code == 401
    assert client.post('/api/admin/review',headers=HEADERS,json={'request_id':request_id}).status_code == 401
    assert execute(client,ticket).status_code == 401
    assert not calls and not mounts
    assert login(client,'scoped-execution-token').status_code == 403
    assert login(client,'invalid-token').status_code == 403
    assert 'scoped-execution-token' not in json.dumps(values)


def test_admin_login_cookie_and_no_credential_persistence(setup):
    client, values, calls, mounts = setup
    result = login(client)
    assert result.status_code == 200
    assert 'HttpOnly' in result.headers['set-cookie'] and 'Secure' in result.headers['set-cookie'] and 'SameSite=strict' in result.headers['set-cookie']
    assert 'admin-login-token' not in result.text
    assert 'test-accessor' not in result.text
    assert client.get('/api/admin/session').json()['policies'] == ['hcp-root']
    assert 'admin-login-token' not in json.dumps(values)
    assert client.post('/api/admin/logout',headers=HEADERS,json={}).status_code == 200
    assert client.get('/api/admin/requests').status_code == 401


def test_approval_tracks_completed_and_blocks_other_review_tickets(setup):
    client, values, calls, mounts = setup
    request_id, ticket = prepare(client)
    assert login(client).status_code == 200
    queue = client.get('/api/admin/requests').json()['requests']
    assert len(queue) == 1 and queue[0]['status'] == 'pending'
    assert 'signature' not in queue[0] and 'target' not in queue[0]
    refreshed = client.post('/api/admin/review',headers=HEADERS,json={'request_id':request_id})
    assert refreshed.status_code == 200
    review = parse_qs(urlsplit(refreshed.json()['review_url']).fragment)['review'][0]
    other_ticket = client.post('/api/resolve',headers=HEADERS,json={'review_id':review}).json()['ticket']
    assert execute(client,ticket).status_code == 200
    assert execute(client,other_ticket).status_code == 409
    record = client.get('/api/admin/requests').json()['requests'][0]
    assert record['status'] == 'completed'
    assert record['receipt']['mount'] == 'onboard-admin-test'
    assert record['receipt']['status'] == 'created'
    assert len([c for c in calls if c.method == 'POST']) == 1
    assert 'scoped-execution-token' not in json.dumps(values)


def test_rejection_and_failure_block_resubmission(setup):
    client, values, calls, mounts = setup
    request_id, ticket = prepare(client)
    login(client)
    assert client.post('/api/admin/reject',headers=HEADERS,json={'request_id':request_id}).status_code == 200
    assert execute(client,ticket).status_code == 409
    request2, ticket2 = prepare(client,mount='onboard-second')
    assert execute(client,ticket2,vault_token='invalid-token').status_code == 403
    records = {r['id']:r for r in client.get('/api/admin/requests').json()['requests']}
    assert records[request2]['status'] == 'needs_attention'
    assert execute(client,ticket2).status_code == 409
    assert not mounts


def test_secret_values_and_outputs_never_enter_queue(setup):
    client, values, calls, mounts = setup
    mounts.add('onboard-admin-test')
    request_id, ticket = prepare(client,action='create_secret',secret_path='dev/app')
    login(client)
    response = execute(client,ticket,secret_data={'password':'do-not-persist-secret'})
    assert response.status_code == 200
    record = client.get('/api/admin/requests').json()['requests'][0]
    assert record['status'] == 'completed' and record['receipt']['version'] == 1
    assert 'do-not-persist-secret' not in json.dumps(values)
    assert 'admin-login-token' not in json.dumps(values)


def test_namespace_change_invalidates_admin_session(setup, monkeypatch):
    client, values, calls, mounts = setup
    login(client)
    monkeypatch.setenv('VAULT_NAMESPACE','other-team')
    assert client.get('/api/admin/requests').status_code == 401


def test_record_tampering_is_rejected(setup):
    client, values, calls, mounts = setup
    request_id, ticket = prepare(client)
    login(client)
    key = admin.record_key(request_id)
    record = json.loads(values[key]); record['plan']['mount']='onboard-tampered';values[key]=json.dumps(record)
    assert execute(client,ticket).status_code == 404
    assert not mounts


def test_missing_session_and_cross_origin_admin_mutations(setup):
    client, values, calls, mounts = setup
    assert client.post('/api/admin/login',json={'vault_token':'admin-login-token'}).status_code == 403
    login(client)
    assert client.post('/api/admin/logout',json={}).status_code == 403
    assert client.post('/api/admin/reject',json={'request_id':'x'*36}).status_code == 403


def test_storage_failure_after_vault_write_blocks_retry(setup, monkeypatch):
    client, values, calls, mounts = setup
    request_id, ticket = prepare(client)
    login(client)
    original = bridge.review_store
    async def fail_completion(command):
        if command[0] == 'EVAL' and command[1] == admin.TRANSITION and command[5] == 'completed':
            raise bridge.HTTPException(503, 'Store unavailable')
        return await original(command)
    monkeypatch.setattr(bridge, 'review_store', fail_completion)
    response = execute(client, ticket)
    assert response.status_code == 503
    assert 'onboard-admin-test' in mounts
    assert 'Verify Vault' in response.json()['detail']
    assert execute(client, ticket).status_code == 409
    assert json.loads(values[admin.record_key(request_id)])['status'] == 'executing'


def test_expired_chat_link_can_be_refreshed_by_admin(setup, monkeypatch):
    client, values, calls, mounts = setup
    request_id, ticket = prepare(client)
    login(client)
    now = bridge.time.time()
    monkeypatch.setattr(bridge.time, 'time', lambda: now + 601)
    assert client.post('/api/preview', headers=HEADERS, json={'ticket':ticket}).status_code == 400
    refreshed = client.post('/api/admin/review', headers=HEADERS, json={'request_id':request_id})
    assert refreshed.status_code == 200
    review_id = parse_qs(urlsplit(refreshed.json()['review_url']).fragment)['review'][0]
    resolved = client.post('/api/resolve', headers=HEADERS, json={'review_id':review_id})
    assert resolved.status_code == 200
    assert bridge.read_plan(resolved.json()['ticket']).mount == 'onboard-admin-test'


def test_sensitive_engine_output_is_not_saved_to_queue(setup, monkeypatch):
    client, values, calls, mounts = setup
    request_id, ticket = prepare(client, action='engine_operation', engine='transit', endpoint='keys/test')
    login(client)
    async def fake_operation(*args):
        return {'status':'completed','mount':'onboard-admin-test','sensitive_result':{'data':{'private_key':'never-store-this-output'}}}
    monkeypatch.setattr(bridge, 'execute_validated', fake_operation)
    result = execute(client, ticket, confirmation_text='EXECUTE POST onboard-admin-test/keys/test')
    assert result.status_code == 200
    assert 'never-store-this-output' in result.text
    assert 'never-store-this-output' not in json.dumps(values)


def test_kv_mount_business_unit_is_signed_and_queued(setup):
    client, values, calls, mounts = setup
    response = client.post('/api/kv-mount-plans', headers={'X-API-Key': KEY}, json={
        'business_unit_id': 'BU-456', 'mount': 'onboard-bu-test', 'kv_version': '2'})
    assert response.status_code == 200 and not calls
    review = parse_qs(urlsplit(response.json()['review_url']).fragment)['review'][0]
    signed = client.post('/api/resolve', headers=HEADERS, json={'review_id': review}).json()['ticket']
    assert execute(client, signed).status_code == 401
    assert login(client).status_code == 200
    queue = client.get('/api/admin/requests').json()['requests']
    assert queue[0]['plan']['business_unit_id'] == 'BU-456'
    assert execute(client, signed).status_code == 200
    assert mounts == {'onboard-bu-test'}
    assert 'admin-login-token' not in json.dumps(values)
    assert 'scoped-execution-token' not in json.dumps(values)


def test_existing_queue_without_business_unit_can_still_be_approved(setup):
    client, values, calls, mounts = setup
    request_id, signed = prepare(client)
    key = admin.record_key(request_id)
    record = json.loads(values[key])
    record['plan'].pop('business_unit_id', None)
    record['signature'] = admin.intent_signature(record)
    values[key] = json.dumps(record)
    assert login(client).status_code == 200
    assert execute(client, signed).status_code == 200


def test_guided_secret_intake_is_self_service_and_cas_zero(setup, monkeypatch):
    client, values, calls, mounts = setup
    monkeypatch.setenv('KV_SECRET_INTAKE_KEY', 'v' * 64)
    mounts.add('onboard-concierge')
    response = client.post('/api/kv-secret-intake', headers={'x-kv-secret-key': 'v' * 64}, json={
        'mount': 'onboard-concierge', 'secret_path': 'app/database',
        'business_unit_id': 'BU-789', 'user_id': 'test-developer'})
    assert response.status_code == 200 and not calls
    review = parse_qs(urlsplit(response.json()['review_url']).fragment)['review'][0]
    signed = client.post('/api/resolve', headers=HEADERS, json={'review_id': review}).json()['ticket']
    assert client.get('/api/admin/session').status_code == 401
    assert client.post('/api/preview', headers=HEADERS, json={'ticket': signed}).json()['admin_review_required'] is False
    assert client.get('/api/fulfilled').json()['requests'] == []
    response = execute(client, signed, secret_data={'password': 'test-value'})
    assert response.status_code == 200
    assert response.json()['fulfilled_url'] == ORIGIN + '/fulfilled'
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie
    completed = client.get('/api/fulfilled').json()['requests']
    assert len(completed) == 1 and completed[0]['plan']['user_id'] == 'test-developer'
    assert completed[0]['receipt']['status'] == 'created'
    assert client.get('/api/admin/session').status_code == 401
    assert execute(client, signed, secret_data={'password': 'test-value'}).status_code == 409
    write = next(request for request in calls if request.url.path.endswith('/data/app/database'))
    assert json.loads(write.content) == {'options': {'cas': 0}, 'data': {'password': 'test-value'}}
    assert 'test-value' not in json.dumps(values)


def self_service_ticket(client, monkeypatch):
    monkeypatch.setenv('KV_SECRET_INTAKE_KEY', 'v' * 64)
    response = client.post('/api/kv-secret-intake', headers={'x-kv-secret-key': 'v' * 64}, json={
        'secret_path': 'app/self-service', 'business_unit_id': 'BU-456', 'user_id': 'test-user'})
    assert response.status_code == 200
    assert response.json()['status'] == 'awaiting_secret_entry'
    review = parse_qs(urlsplit(response.json()['review_url']).fragment)['review'][0]
    signed = client.post('/api/resolve', headers=HEADERS, json={'review_id': review}).json()['ticket']
    return signed


def test_failed_self_service_write_is_not_fulfilled(setup, monkeypatch):
    client, values, calls, mounts = setup
    signed = self_service_ticket(client, monkeypatch)
    response = execute(client, signed, vault_token='invalid-token', secret_data={'password': 'failure-test-value'})
    assert response.status_code == 403
    assert client.get('/api/fulfilled').json()['requests'] == []
    record = json.loads(values[admin.record_key(admin.ticket_id(signed))])
    assert record['status'] == 'needs_attention'
    assert execute(client, signed, secret_data={'password': 'retry'}).status_code == 409
    assert 'failure-test-value' not in json.dumps(values)
    assert 'invalid-token' not in json.dumps(values)


def test_fulfilled_history_is_browser_scoped_and_cookie_signed(setup, monkeypatch):
    client, values, calls, mounts = setup
    mounts.add('onboard-concierge')
    signed = self_service_ticket(client, monkeypatch)
    response = execute(client, signed, secret_data={'password': 'private-test-value'})
    assert response.status_code == 200
    own = client.get('/api/fulfilled').json()
    assert len(own['requests']) == 1
    assert 'private-test-value' not in json.dumps(own)
    assert 'scoped-execution-token' not in json.dumps(own)
    client.cookies.clear()
    assert client.get('/api/fulfilled').json()['requests'] == []
    client.cookies.set(admin.FULFILLED_COOKIE, 'forged-cookie')
    assert client.get('/api/fulfilled').json()['requests'] == []
    assert client.get('/api/admin/requests').status_code == 401


def test_agent_cannot_disable_approval_by_requesting_self_service(setup):
    client, values, calls, mounts = setup
    response = client.post('/api/plans', headers={'X-API-Key': KEY}, json={
        'action': 'create_secret', 'engine': 'kv-v2', 'mount': 'onboard-concierge',
        'secret_path': 'app/bypass', 'approval_mode': 'self_service'})
    assert response.status_code == 422 and not calls
    assert not values
