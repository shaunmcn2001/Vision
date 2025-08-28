
from enum import Enum
from typing import Dict, Any
from datetime import datetime

class JobState(Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"

class JobRegistry:
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def create(self, job_id: str):
        self._jobs[job_id] = {
            "job_id": job_id,
            "state": JobState.QUEUED.value,
            "message": "Queued",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z"
        }

    def update(self, job_id: str, state: JobState, message: str):
        job = self._jobs.get(job_id)
        if not job:
            return
        job["state"] = state.value
        job["message"] = message
        job["updated_at"] = datetime.utcnow().isoformat() + "Z"

    def get(self, job_id: str):
        return self._jobs.get(job_id)
