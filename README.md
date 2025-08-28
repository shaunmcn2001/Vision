
# VisionZones — Sentinel-2 Productivity Zones API (FastAPI + Earth Engine)

Minimal service to compute field productivity zones (like OneSoil) using Sentinel‑2 L2A with Earth Engine,
export results to Google Cloud Storage, and let users download them as a ZIP.

## What it does
- Accepts a field boundary (GeoJSON) via `/start`.
- Pulls multi‑year Sentinel‑2 NDVI within the boundary, masks clouds via SCL.
- Computes a per‑pixel long‑term NDVI median.
- Clusters into k zones (k=3/5/7) using Earth Engine's KMeans.
- Exports a GeoTIFF (zone IDs) to GCS under `gs://$GCS_BUCKET/{job_id}/zones_k{k}.tif`.
- Lets you check `/status?job_id=...` and download everything with `/download-zip?job_id=...`.

> NOTE: This keeps dependencies lean (no GDAL/Fiona/Rasterio). All heavy geoprocessing is done in Earth Engine.

## Quick start on Render (recommended for MVP)
1. Create a GCP project. Enable **Earth Engine API** and **Cloud Storage**.
2. Create a **service account**; grant Storage Object Admin on your bucket.
3. Create a **GCS bucket** (regional). Register your Cloud project for Earth Engine.
4. Deploy this repo on **Render → New → Web Service (Docker)**.
5. Add env vars:
   - `EE_PROJECT`
   - `EE_SERVICE_ACCOUNT_EMAIL`
   - `GOOGLE_APPLICATION_CREDENTIALS_JSON` (paste full JSON)
   - `GCS_BUCKET`
   - `APP_BASE_URL` (e.g., `https://your-service.onrender.com`)

## API
### `POST /start`
Form-data:
- `file`: GeoJSON file of your field polygon
- `start_year` (int, default: 2018)
- `end_year` (int, default: current year)
- `k` (int, default: 5) — number of zones

Response:
```json
{"job_id":"job_2025-08-28_120102","status":"QUEUED"}
```

### `GET /status?job_id=...`
Returns state and any export paths.

### `GET /download-zip?job_id=...`
Streams a ZIP containing all GCS objects exported under the job prefix.

## Local dev
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 10000
```

Create `.env` with the keys from `.env.example`.

## Production (Google Cloud Run suggested later)
Use the same Dockerfile. Prefer Workload Identity instead of JSON keys.

## Notes
- Input must be **GeoJSON** in EPSG:4326. Use a single Polygon/MultiPolygon.
- For very large fields, consider simplifying geometry.
- For KML/KMZ/SHAPE uploads, add a small conversion worker (out of scope here to keep deps lean).
