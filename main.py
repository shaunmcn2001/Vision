import os, io, json, datetime, zipfile as zf, tempfile
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import ee
from google.cloud import storage

# Lightweight vector I/O (bundled wheels)
import pyogrio
from shapely.geometry import mapping
from shapely.ops import unary_union

# -------------------- ENV / CONFIG --------------------
EE_SERVICE_ACCOUNT_EMAIL = os.environ["EE_SERVICE_ACCOUNT_EMAIL"]
EE_PROJECT               = os.environ["EE_PROJECT"]
GCS_BUCKET               = os.environ["GCS_BUCKET"]
GOOGLE_APPLICATION_CREDENTIALS_JSON = os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]

# Earth Engine init with service account
sa_key = json.loads(GOOGLE_APPLICATION_CREDENTIALS_JSON)
credentials = ee.ServiceAccountCredentials(EE_SERVICE_ACCOUNT_EMAIL, key_data=json.dumps(sa_key))
ee.Initialize(credentials, project=EE_PROJECT)

# GCS client
gcs = storage.Client.from_service_account_info(sa_key)
bucket = gcs.bucket(GCS_BUCKET)

app = FastAPI(title="Sentinel-2 Indices Exporter", version="1.1.0")

# CORS (optional – open for now)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

INDICES_DEFAULT = ["NDVI","EVI","SAVI","NDRE","NDWI","NDMI","NBR"]
WORLDCOVER_DATASET = "ESA/WorldCover/v200"  # 10 m, 2021

# -------------------- SENTINEL-2 PIPELINE --------------------
def mask_scl(img: ee.Image) -> ee.Image:
    """Mask clouds/shadows using S2 SCL band."""
    scl = img.select('SCL')
    ok  = (scl.neq(3)   # shadow
           .And(scl.neq(8))  # cloud medium
           .And(scl.neq(9))  # cloud high
           .And(scl.neq(10)) # cirrus
           .And(scl.neq(11)))# snow/ice
    return img.updateMask(ok)

def add_indices(img: ee.Image) -> ee.Image:
    """Add vegetation/water/stress indices and cast to Float32."""
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

def s2_collection(aoi_geom: ee.Geometry, worldcover_exclude: List[int]) -> ee.ImageCollection:
    """
    Build a clean S2 collection and apply a WorldCover mask that excludes
    classes in `worldcover_exclude` (e.g., 10=Trees, 80=Water, 50=Built-up).
    """
    s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
          .filterBounds(aoi_geom)
          .map(mask_scl))

    # Build non-excluded mask
    wc = ee.ImageCollection(WORLDCOVER_DATASET).first().select('Map').clip(aoi_geom)
    # Start with "keep everything"
    non_excluded = ee.Image(1)
    # Apply exclusions
    for code in worldcover_exclude:
        non_excluded = non_excluded.And(wc.neq(code))
    non_excluded = non_excluded.rename('non_excluded')

    # Apply mask then add indices
    s2 = (s2.map(lambda img: img.updateMask(non_excluded))
            .map(add_indices))
    return s2

def monthly_image(s2: ee.ImageCollection, aoi: ee.Geometry, y: int, m: int, idx: str) -> ee.Image:
    """Single-band Float32 monthly composite; fully masked if month empty."""
    start = ee.Date.fromYMD(y, m, 1)
    end   = start.advance(1, 'month')
    col   = (s2.filterDate(start, end)
               .filterBounds(aoi)
               .select(idx))
    band  = f"{idx}_{y}_{m:02d}"
    img = ee.Image(ee.Algorithms.If(
        col.size().gt(0),
        col.median().toFloat().rename(band),
        ee.Image.constant(0).toFloat().updateMask(ee.Image.constant(0)).rename(band)
    )).clip(aoi)
    return img

def auto_utm_crs(aoi: ee.Geometry) -> str:
    """Return EPSG string for UTM zone based on AOI centroid (326xx north / 327xx south)."""
    cen = aoi.centroid(10).coordinates()
    lon = ee.Number(cen.get(0)).getInfo()
    lat = ee.Number(cen.get(1)).getInfo()
    zone = int((lon + 180) // 6 + 1)
    return f"EPSG:{326 if lat >= 0 else 327}{zone:02d}"

# -------------------- BOUNDARY READER --------------------
def read_boundary_to_ee_geometry(upload: UploadFile) -> ee.Geometry:
    """
    Accept GeoJSON, Shapefile.zip, KML, KMZ; convert to WGS84 and return ee.Geometry.
    Tip: GeoJSON or Shapefile.zip are the safest.
    """
    suffix = os.path.splitext(upload.filename)[1].lower()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, upload.filename)
        with open(path, "wb") as f:
            f.write(upload.file.read())

        # KMZ → extract KML
        if suffix == ".kmz":
            with zf.ZipFile(path) as z:
                kml_name = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
                if not kml_name:
                    raise HTTPException(400, "KMZ did not contain a KML file.")
                z.extract(kml_name, td)
                path = os.path.join(td, kml_name)

        # Shapefile.zip → extract then point to .shp
        if suffix == ".zip":
            with zf.ZipFile(path) as z:
                z.extractall(td)
            shp = None
            for name in os.listdir(td):
                if name.lower().endswith(".shp"):
                    shp = os.path.join(td, name)
                    break
            if not shp:
                raise HTTPException(400, "Zip did not contain a .shp")
            path = shp

        try:
            gdf = pyogrio.read_dataframe(path)
        except Exception as e:
            raise HTTPException(400, f"Could not read boundary file: {e}")

        if gdf.empty:
            raise HTTPException(400, "Boundary file is empty.")

        # Ensure WGS84
        if gdf.crs is None:
            # Assume already WGS84 if no CRS is set
            pass
        else:
            try:
                gdf = gdf.to_crs(4326)
            except Exception as e:
                raise HTTPException(400, f"Failed to reproject to EPSG:4326: {e}")

        geom = unary_union(gdf.geometry.values)
        return ee.Geometry(mapping(geom))

# -------------------- HELPERS --------------------
def list_blobs(prefix: str):
    return list(bucket.list_blobs(prefix=prefix))

# -------------------- API --------------------
@app.get("/")
def home():
    return {
        "ok": True,
        "message": "POST /start with a boundary to launch exports; GET /download-zip?job_id=... to fetch all files.",
        "defaults": {
            "indices": INDICES_DEFAULT,
            "exclude_worldcover_classes": [10, 80, 50]  # trees, water, built-up
        }
    }

@app.get("/health")
def health():
    return {"ok": True, "bucket": GCS_BUCKET, "project": EE_PROJECT}

@app.post("/start")
async def start_job(
    file: UploadFile = File(...),
    start_year: int = Form(...),
    end_year: int   = Form(...),
    # CSV of indices or empty → default set
    indices: Optional[str] = Form(None),
    # CSV of WorldCover classes to exclude or empty → 10,80,50
    exclude_classes: Optional[str] = Form(None),
    # scale in meters (default 10)
    scale: int = Form(10),
):
    """
    Start exports to GCS:
    - One GeoTIFF per month per index
    - Mask out ESA WorldCover classes (trees=10, water=80, built=50 by default)
    """
    try:
        aoi = read_boundary_to_ee_geometry(file)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(400, f"Boundary error: {e}")

    idx_list = [s.strip().upper() for s in (indices.split(",") if indices else INDICES_DEFAULT) if s.strip()]
    for idx in idx_list:
        if idx not in INDICES_DEFAULT:
            raise HTTPException(400, f"Unknown index: {idx}")

    if exclude_classes:
        try:
            excl = [int(s.strip()) for s in exclude_classes.split(",") if s.strip()]
        except:
            raise HTTPException(400, "exclude_classes must be CSV of integers like '10,80,50'")
    else:
        excl = [10, 80, 50]

    s2 = s2_collection(aoi, excl)
    crs = auto_utm_crs(aoi)
    asset_name = "aoi"  # used only in GCS path; can be customized by parsing file name

    # Unique job id folder
    job_id = datetime.datetime.utcnow().strftime("job_%Y%m%d_%H%M%S")

    # Launch tasks: gs://bucket/{job_id}/{IDX}/{IDX_YYYY_MM}.tif
    for y in range(int(start_year), int(end_year) + 1):
        for m in range(1, 13):
            for idx in idx_list:
                img    = monthly_image(s2, aoi, y, m, idx)
                prefix = f"{job_id}/{idx}/{idx}_{y}_{m:02d}"
                task = ee.batch.Export.image.toCloudStorage(
                    image=img,
                    description=f"{idx}_{y}_{m:02d}",
                    bucket=GCS_BUCKET,
                    fileNamePrefix=prefix,
                    region=aoi,
                    scale=scale,
                    crs=crs,
                    maxPixels=1e13
                )
                task.start()

    return {
        "job_id": job_id,
        "bucket": GCS_BUCKET,
        "years": [start_year, end_year],
        "indices": idx_list,
        "excluded_worldcover_classes": excl,
        "note": "Use GET /status?job_id=... then /download-zip?job_id=..."
    }

@app.get("/status")
def status(job_id: str):
    """List how many files have arrived for this job (by index)."""
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
def download_zip(job_id: str, index: Optional[str] = None):
    """
    Stream a ZIP of all files for this job_id.
    Optional: ?index=NDVI to only include that index.
    """
    prefix = f"{job_id}/" if not index else f"{job_id}/{index}/"
    blobs = list_blobs(prefix=prefix)
    if not blobs:
        raise HTTPException(404, "No files for this job yet (or wrong job_id/index).")

    def stream():
        with io.BytesIO() as mem:
            with zf.ZipFile(mem, mode="w", compression=zf.ZIP_DEFLATED) as z:
                for b in blobs:
                    arcname = "/".join(b.name.split("/")[1:])  # strip job_id
                    z.writestr(arcname, b.download_as_bytes())
            mem.seek(0)
            yield from mem

    filename = f"{job_id}{'' if not index else '_' + index}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(stream(), media_type="application/zip", headers=headers)
