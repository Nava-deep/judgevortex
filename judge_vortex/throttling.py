import time
import redis
from rest_framework.throttling import BaseThrottle

# Connect to Redis container
redis_client = redis.Redis(host='redis', port=6379, db=0)

class DistributedRateThrottle(BaseThrottle):
    def allow_request(self, request, view):
        # Identify user
        ident = request.user.id if request.user.is_authenticated else request.META.get('REMOTE_ADDR')
        key = f"throttle:submission:{ident}"
        
        limit = 100   # 5 requests
        period = 60 # per 60 seconds

        # Atomic Lua Script
        lua_script = """
        local current = redis.call("incr", KEYS[1])
        if tonumber(current) == 1 then
            redis.call("expire", KEYS[1], ARGV[1])
        end
        if tonumber(current) > tonumber(ARGV[2]) then
            return 0
        end
        return 1
        """
        
        is_allowed = redis_client.eval(lua_script, 1, key, period, limit)
        return bool(is_allowed)

    def wait(self):
        return 60