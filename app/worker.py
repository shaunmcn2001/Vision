
import os
import time
from rq import Worker, Queue, Connection
from redis import Redis

def main():
    url = os.environ.get("REDIS_URL")
    if not url:
        raise RuntimeError("REDIS_URL not set for worker.")
    conn = Redis.from_url(url, decode_responses=False)
    with Connection(conn):
        worker = Worker([Queue("visionzones")])
        print("Worker started. Waiting for jobs...")
        worker.work(with_scheduler=True)

if __name__ == "__main__":
    main()
