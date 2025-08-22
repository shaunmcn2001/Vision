python
import os, io, json, datetime, zipfile, tempfile
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import ee
from google.cloud import storage
import geopandas as gpd
from shapely.geometry import mapping

# -------- Environment / Config --------
EE_SERVICE_ACCOUNT_EMAIL = os.environ["EE_SERVICE_ACCOUNT_EMAIL"]
EE_PROJECT               = os.environ["EE_PROJECT"]
GCS_BUCKET               = os.environ["GCS_BUCKET"]
GOOGLE_APPLICATION_CREDENTIALS_JSON = os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]

# -------- Earth Engine init (service account) --------
sa_key = json.loads(GOOGLE_APPLICATION_CREDENTIALS_JSON)
ee.ServiceAccountCredentials(EE_SERVICE_ACCOUNT_EMAIL, key_data=json.dumps(sa_key)).authorize()
ee.Initialize(project=EE_PROJECT)

# -------- GCS client --------
gcs_client = storage.Client.from_service_account_info(sa_key)
bucket = gcs_client.bucket(GCS_BUCKET)

app = FastAPI(title="Sentinel-2 Indices Exporter", version="1.0.0")

INDICES = ["NDVI", "EVI", "SAVI", "NDRE", "NDWI", "NDMI", "NBR"]

# ---- Helpers ----
def mask_scl(img: ee.Image) -> ee.Image:
    """Mask Sentinel-2 L2A using SCL (remove clouds, shadow, cirrus, snow)."""
    scl = img.select('SCL')
    ok  = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
    return img.updateMask(ok)

def add_indices(img: ee.Image) -> ee.Image:
    """Add common indices as Float32 bands."""
    B2=img.select('B2'); B3=img.select('B3'); B4=img.select('B4')
    B5=img.select('B5'); B8=img.select('B8'); B11=img.select('B11'); B12=img.select('B12')
    ndvi = img.normalizedDifference(['B8','B4']).rename('NDVI').toFloat()
    evi  = img.expression('2.5*((NIR-RED)/(NIR+6*RED-7.5*BLUE+1))',
                          {'NIR':B8,'RED':B4,'BLUE':B2}).rename('EVI').toFloat()
    savi = img.expression('((NIR-RED)/(NIR+RED+0.5))*1.5',
                          {'NIR':B8,'RED':B4}).rename('SAVI').toFloat()
    ndre = img.normalizedDifference(['B8','B5']).rename('NDRE').toFloat()
    ndwi = img.normalizedDifference(['B3','B8']).rename('NDWI').toFloat()
    ndmi = img.normalizedDifference(['B8','B11']).rename('NDMI').toFloat()
    nbr  = img.normalizedDifference(['B8','B12']).rename('NBR').toFloat()
    return img.addBands([ndvi,evi,savi,ndre,ndwi,ndmi,nbr])

def s2_collection(aoi: ee.Geometry) -> ee.ImageCollection:
    return (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(aoi)
            .map(mask_scl)
            .map(add_indices))

def auto_utm_crs(aoi: ee.Geometry) -> str:
    """Return EPSG code string for UTM zone of AOI (326xx north / 327xx south)."""
    cen = aoi.centroid(10).coordinates()
    lon = ee.Number(cen.get(0)).getInfo()
    lat = ee.Number(cen.get(1)).getInfo()
    zone = int((lon + 180) // 6 + 1)
    return f"EPSG:{326 if lat >= 0 else 327}{zone:02d}"

def read_boundary_to_geometry(upload: UploadFile) -> ee.Geometry:
    """Accepts GeoJSON, KML/KMZ, or zipped Shapefile; returns ee.Geometry (WGS84)."""
    suffix = os.path.splitext(upload.filename)[1].lower()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, upload.filename)
        with open(path, "wb") as f:
            f.write(upload.file.read())

        # KMZ: unzip to KML
        if suffix == ".kmz":
            import zipfile
            with zipfile.ZipFile(path) as z:
                kml_name = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
                if not kml_name:
                    raise HTTPException(400, "KMZ did not contain a KML file.")
                z.extract(kml_name, td)
                path = os.path.join(td, kml_name)

        # If it's a zipped shapefile, geopandas can read the zip path directly
        gdf = gpd.read_file(path).to_crs(4326)
        if gdf.empty:
            raise HTTPException(400, "Boundary file is empty or unsupported.")
        geom = mapping(gdf.unary_union)  # dissolve to single geometry
        return ee.Geometry(geom)

def monthly_image(s2: ee.ImageCollection, aoi: ee.Geometry, y: int, m: int, idx: str) -> ee.Image:
    start = ee.Date.fromYMD(y, m, 1)
    end   = start.advance(1, 'month')
    col = s2.filterDate(start, end).filterBounds(aoi).select(idx)
    # Float32 single band; masked if empty
    img = ee.Image(ee.Algorithms.If(
        col.size().gt(0),
        col.median().toFloat(),
        ee.Image.constant(0).toFloat().updateMask(ee.Image.constant(0))
    )).rename(f"{idx}_{y}_{m:02d}").clip(aoi)
    return img

def list_blobs(prefix: str):
    return list(bucket.list_blobs(prefix=prefix))

# -------- API --------
@app.get("/")
def home():
    return {"ok": True, "message": "POST /start to launch exports; GET /download-zip?job_id=... to fetch."}

@app.post("/start")
async def start_job(file: UploadFile = File(...),
                    start_year: int = Form(...),
                    end_year: int   = Form(...),
                    indices: Optional[str] = Form(None)):
    """
    Upload boundary + choose years/indices; starts all Earth Engine exports to GCS.
    indices: optional CSV string, e.g., "NDVI,NDRE,NDMI"
    """
    try:
        aoi = read_boundary_to_geometry(file)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(400, f"Could not read boundary: {e}")

    idx_list = [s.strip().upper() for s in (indices.split(",") if indices else INDICES) if s.strip()]
    for idx in idx_list:
        if idx not in INDICES:
            raise HTTPException(400, f"Unknown index: {idx}")

    s2 = s2_collection(aoi)
    crs = auto_utm_crs(aoi)

    job_id = datetime.datetime.utcnow().strftime("job_%Y%m%d_%H%M%S")
    # Launch all exports: gs://bucket/{job_id}/{IDX}/{IDX_YYYY_MM}.tif
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            for idx in idx_list:
                img = monthly_image(s2, aoi, y, m, idx)
                prefix = f"{job_id}/{idx}/{idx}_{y}_{m:02d}"
                task = ee.batch.Export.image.toCloudStorage(
                    image=img,
                    description=f"{idx}_{y}_{m:02d}",
                    bucket=GCS_BUCKET,
                    fileNamePrefix=prefix,
                    region=aoi,
                    scale=10,
                    crs=crs,
                    maxPixels=1e13
                )
                task.start()

    return {"job_id": job_id, "bucket": GCS_BUCKET, "indices": idx_list, "years": [start_year, end_year]}

@app.get("/status")
def status(job_id: str):
    """Simple status: count files written under gs://bucket/{job_id}/."""
    blobs = list_blobs(prefix=f"{job_id}/")
    total = len(blobs)
    by_index = {}
    for b in blobs:
        parts = b.name.split("/")
        if len(parts) >= 2:
            by_index.setdefault(parts[1], 0)
            by_index[parts[1]] += 1
    return {"job_id": job_id, "files_found": total, "by_index": by_index}

@app.get("/download-zip")
def download_zip(job_id: str):
    """Stream a ZIP of all files in gs://bucket/{job_id}/ to the browser."""
    blobs = list_blobs(prefix=f"{job_id}/")
    if not blobs:
        raise HTTPException(404, "No files yet for this job_id. Try again later or check /status.")

    def iterfile():
        with io.BytesIO() as mem:
            with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                for b in blobs:
                    arcname = "/".join(b.name.split("/")[1:])  # strip job_id prefix in zip
                    zf.writestr(arcname, b.download_as_bytes())
            mem.seek(0)
            yield from mem
    filename = f"{job_id}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iterfile(), media_type="application/zip", headers=headers)
