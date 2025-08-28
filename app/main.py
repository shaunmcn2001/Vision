
import os
import json
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ee_client import ensure_ee
from .jobs import JobState, jobs_registry as jobs
from .zones import run_zone_export
from .storage import zip_gcs_prefix
from .queue import get_queue, enqueue

app = FastAPI(title="VisionZones", version="0.2.0")

# Serve the simple UI at /ui
app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=2)

@app.get("/")
def root():
    return {
        "ok": True,
        "name": "VisionZones",
        "version": "0.2.0",
        "endpoints": ["/healthz", "/ui", "/start", "/status", "/download-zip", "/docs"],
    }

@app.get("/healthz")
def healthz():
    return {"ok": True}

class StartResponse(BaseModel):
    job_id: str
    status: str

def _start_sync_job(job_id: str, geojson, k, start_year, end_year):
    jobs.update(job_id, JobState.RUNNING, "Initializing Earth Engine")
    try:
        ensure_ee()
        run_zone_export(job_id=job_id, geojson=geojson, k=k,
                        start_year=start_year, end_year=end_year)
        jobs.update(job_id, JobState.SUCCEEDED, "Export complete")
    except Exception as e:
        jobs.update(job_id, JobState.FAILED, f"Error: {e}")

@app.post("/start", response_model=StartResponse)
async def start(
    file: UploadFile = File(...),
    start_year: Optional[int] = Form(None),
    end_year: Optional[int] = Form(None),
    k: int = Form(5)
):
    if file.content_type not in ("application/geo+json", "application/json", "text/plain"):
        raise HTTPException(status_code=400, detail="Upload a GeoJSON file (application/geo+json).")

    content = await file.read()
    try:
        geojson = json.loads(content.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    for key in ["EE_PROJECT", "GCS_BUCKET"]:
        if not os.getenv(key):
            raise HTTPException(status_code=500, detail=f"Missing env var: {key}")

    job_id = f"job_{datetime.utcnow().strftime('%Y-%m-%d_%H%M%S')}"
    jobs.create(job_id)

    # If REDIS_URL is configured, enqueue to worker; else run in a local thread
    if get_queue():
        # enqueue background job
        enqueue(_start_sync_job, job_id=job_id, geojson=geojson, k=k,
                start_year=start_year, end_year=end_year)
        # Mark as RUNNING; worker will update status upon completion
        jobs.update(job_id, JobState.RUNNING, "Queued on worker")
    else:
        # Fallback: run in-thread pool on the web service
        def _task():
            _start_sync_job(job_id, geojson, k, start_year, end_year)
        executor.submit(_task)

    return StartResponse(job_id=job_id, status=JobState.QUEUED.value)

@app.get("/status")
def status(job_id: str):
    st = jobs.get(job_id)
    if not st:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return JSONResponse(st)

@app.get("/download-zip")
def download_zip(job_id: str):
    st = jobs.get(job_id)
    if not st:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    if st["state"] != JobState.SUCCEEDED.value:
        raise HTTPException(status_code=409, detail=f"Job not ready (state={st['state']}).")

    gcs_bucket = os.environ["GCS_BUCKET"]
    prefix = f"{job_id}/"
    stream = zip_gcs_prefix(bucket_name=gcs_bucket, prefix=prefix)
    headers = {"Content-Disposition": f"attachment; filename={job_id}.zip"}
    return StreamingResponse(stream, headers=headers, media_type="application/zip")
