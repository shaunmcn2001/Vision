
import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ee_client import ensure_ee
from .paddocks import create_paddock, list_paddocks, get_paddock
from .ingest import parse_boundary
from .ee_tiles import ndvi_median_image, tile_url_for

app = FastAPI(title="NDVI Viewer", version="1.0.0")

# Static site
app.mount("/", StaticFiles(directory="static", html=True), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
def healthz():
    return {"ok": True}

# Upload boundary and save paddock
@app.post("/upload-boundary")
async def upload_boundary(name: str = Form(...), file: UploadFile = File(...)):
    raw = await file.read()
    try:
        geojson = parse_boundary(file.filename or "upload", raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse boundary: {e}")
    doc = create_paddock(name, geojson)
    return {"ok": True, "paddock": doc}

# List paddocks
@app.get("/paddocks")
def paddocks_list():
    return {"items": list_paddocks()}

# NDVI tile endpoint
@app.get("/tiles_ndvi")
def tiles_ndvi(paddock_id: str, start_year: int, end_year: int):
    ensure_ee()
    p = get_paddock(paddock_id)
    if not p:
        raise HTTPException(status_code=404, detail="Paddock not found")
    img = ndvi_median_image(p["geometry"], start_year, end_year)
    vis = {"min": 0.1, "max": 0.9, "palette": ["#440154","#3b528b","#21908d","#5dc963","#fde725"]}
    url = tile_url_for(img, vis)
    return {"tile_url": url}
