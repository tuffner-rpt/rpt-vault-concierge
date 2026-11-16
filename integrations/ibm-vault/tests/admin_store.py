"""In-memory Redis protocol emulator for isolated review workflow tests only."""
import json
from api import admin

class MemoryReviewStore:
    def __init__(self):
        self.values, self.indexes = {}, {}

    async def __call__(self, command):
        values, indexes = self.values, self.indexes
        op, *args = command
        if op == 'GET': return values.get(args[0])
        if op == 'SET':
            if 'NX' in args and args[0] in values: return None
            values[args[0]] = args[1]; return 'OK'
        if op == 'MGET': return [values.get(k) for k in args]
        if op == 'ZREMRANGEBYSCORE': return 0
        if op == 'ZREVRANGE': return list(reversed(indexes.get(args[0], [])))[int(args[1]):int(args[2])+1]
        if op == 'EVAL':
            script, count = args[:2]; count = int(count); keys = args[2:2+count]; a = args[2+count:]
            if script == admin.CREATE:
                if keys[0] in values: return 0
                values[keys[0]] = a[0]; indexes.setdefault(keys[1], []).append(a[2]); return 1
            if script == admin.TRANSITION:
                if keys[0] not in values: return 0
                record = json.loads(values[keys[0]])
                if record['status'] != a[0]: return 0
                record.update(status=a[1], updated_at=int(a[2]), reviewer=a[3])
                if a[4]: record['receipt'] = json.loads(a[4])
                values[keys[0]] = json.dumps(record); return 1
        raise AssertionError(command)
