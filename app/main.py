
import os, json
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ee_client import ensure_ee
from .jobs import JobState, jobs_registry as jobs
from .zones import run_zone_export
from .storage import zip_gcs_prefix
from .queue import get_queue, enqueue
from .kml_utils import maybe_kmz_to_geojson
from .paddocks import create_paddock, list_paddocks, get_paddock, delete_paddock
from .ee_tiles import ndvi_median_image, zones_image, tile_url_for

app = FastAPI(title="VisionZones", version="0.9.0")

# Static: / -> /map
app.mount("/", StaticFiles(directory="static", html=True), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=2)

@app.get("/healthz")
def healthz():
    return {"ok": True}

# ---------- Paddocks CRUD ----------
class PaddockCreate(BaseModel):
    name: str
    geometry: dict  # GeoJSON Feature/Polygon/MultiPolygon

@app.post("/paddocks")
def paddocks_create(body: PaddockCreate):
    doc = create_paddock(body.name, body.geometry)
    return {"ok": True, "paddock": doc}

@app.get("/paddocks")
def paddocks_list():
    return {"items": list_paddocks()}

@app.get("/paddocks/{pid}")
def paddocks_get(pid: str):
    p = get_paddock(pid)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    return p

@app.delete("/paddocks/{pid}")
def paddocks_delete(pid: str):
    if not get_paddock(pid):
        raise HTTPException(status_code=404, detail="Not found")
    delete_paddock(pid)
    return {"ok": True}

# ---------- Jobs as before ----------
class StartResponse(BaseModel):
    job_id: str
    status: str

@app.post("/start", response_model=StartResponse)
async def start(
    file: UploadFile = File(...),
    start_year: Optional[int] = Form(None),
    end_year: Optional[int] = Form(None),
    k: int = Form(5)
):
    filename = (file.filename or "").lower()
    raw_bytes = await file.read()
    try:
        geojson = maybe_kmz_to_geojson(filename, raw_bytes)
    except Exception as e:
        try:
            geojson = json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid input ({e}). Provide GeoJSON or KMZ/KML.")

    for key in ["EE_PROJECT", "GCS_BUCKET"]:
        if not os.getenv(key):
            raise HTTPException(status_code=500, detail=f"Missing env var: {key}")

    job_id = f"job_{datetime.utcnow().strftime('%Y-%m-%d_%H%M%S')}"
    jobs.create(job_id)

    if get_queue():
        enqueue(_start_sync_job, job_id=job_id, geojson=geojson, k=k,
                start_year=start_year, end_year=end_year)
        jobs.update(job_id, JobState.RUNNING, "Queued on worker")
    else:
        def _task():
            _start_sync_job(job_id, geojson, k, start_year, end_year)
        executor.submit(_task)

    return StartResponse(job_id=job_id, status=JobState.QUEUED.value)

def _start_sync_job(job_id: str, geojson, k, start_year, end_year):
    jobs.update(job_id, JobState.RUNNING, "Initializing Earth Engine")
    try:
        ensure_ee()
        run_zone_export(job_id=job_id, geojson=geojson, k=k,
                        start_year=start_year, end_year=end_year)
        jobs.update(job_id, JobState.SUCCEEDED, "Export complete")
    except Exception as e:
        jobs.update(job_id, JobState.FAILED, f"Error: {e}")

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

# ---------- Earth Engine tiles for map ----------
@app.get("/tiles")
def tiles(type: str, paddock_id: str, start_year: int, end_year: int):
    ensure_ee()
    p = get_paddock(paddock_id)
    if not p:
        raise HTTPException(status_code=404, detail="Paddock not found")

    if type == "ndvi_median":
        img = ndvi_median_image(p["geometry"], start_year, end_year)
        vis = {"min": 0.1, "max": 0.9, "palette": ["#440154", "#3b528b", "#21908d", "#5dc963", "#fde725"]}
    elif type == "zones":
        img = zones_image(p["geometry"], start_year, end_year, k=5)
        # assign a simple palette for classes 0..k-1
        vis = {"min": 0, "max": 4, "palette": ["#440154", "#21908d", "#5dc963", "#fde725", "#3b528b"]}
    else:
        raise HTTPException(status_code=400, detail="Unknown type")

    url = tile_url_for(img, vis)
    return {"tile_url": url}
