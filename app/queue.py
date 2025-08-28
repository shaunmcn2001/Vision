
import os
from typing import Callable, Any, Dict
from rq import Queue
from redis import Redis

def get_queue():
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    r = Redis.from_url(url, decode_responses=False)
    return Queue("visionzones", connection=r)

def enqueue(func: Callable, **kwargs) -> Dict[str, Any]:
    q = get_queue()
    if not q:
        raise RuntimeError("Redis queue not configured. Set REDIS_URL to enable background worker.")
    job = q.enqueue(func, **kwargs, retry=3, result_ttl=86400, job_timeout=7200)
    return {"job_id": job.id}
