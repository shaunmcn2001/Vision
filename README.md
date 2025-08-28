markdown
# Sentinel‑2 Indices Exporter (Render)

A tiny FastAPI app that:
- Accepts a field boundary (GeoJSON / KML / KMZ / Shapefile.zip)
- Computes monthly **NDVI, EVI, SAVI, NDRE, NDWI, NDMI, NBR** from **Sentinel‑2 L2A** with SCL cloud mask
- Exports one **GeoTIFF per month** to **Google Cloud Storage** in your bucket
- Lets the user download a **ZIP** of all files for a job via `/download-zip?job_id=...`

## Deploy on Render

1) **Create a Google Cloud project** (or use an existing one).

2) **Enable APIs** (APIs & Services → Enable):
   - *Earth Engine API*
   - *Cloud Storage API*

3) **Create a Service Account** (IAM & Admin → Service Accounts):
   - Name it e.g. `ee-render-sa`.
   - Create a JSON key (download it).

4) **Grant roles**:
   - On the **project**: `Viewer` (or more granular) is fine for EE metadata.
   - On your **GCS bucket** (Storage → Browser → your bucket → Permissions):
     - Add the service account with **Storage Object Admin**.

5) **Register your Cloud Project for Earth Engine**  
   In the Earth Engine Code Editor → *Gear icon* → **Cloud Projects** → Add your Google Cloud project.  
   Alternatively, follow: https://developers.google.com/earth-engine/cloud/projects

6) **Create a GCS bucket** (e.g., `gee-exports-yourproj`). Keep it regional and standard class.

7) **Render Setup**
   - New → **Web Service** → Connect this repo.
   - `render.yaml` is included; Render will use:
     ```
     build: pip install --upgrade pip && pip install -r requirements.txt
     start: uvicorn main:app --host 0.0.0.0 --port 10000
     ```
   - The app requires **Python 3.11+** (specified in `runtime.txt`).
   - Add **Environment Variables** (mark as *Secret*):
     - `EE_SERVICE_ACCOUNT_EMAIL` = your service account email
     - `EE_PROJECT` = your Google Cloud project ID
     - `GCS_BUCKET` = your bucket name
     - `GOOGLE_APPLICATION_CREDENTIALS_JSON` = **the full JSON** contents of the key file

8) **Open the app** once it deploys.

## Usage

### Start a job
`POST /start` (form-data):
- `file` = your boundary (GeoJSON/KML/KMZ/zip shapefile)
- `start_year` = e.g. 2018
- `end_year` = e.g. 2025
- `indices` (optional CSV) e.g. `NDVI,NDRE,NDMI`

**Response:**
```json
{ "job_id": "job_20250822_120102", "bucket": "your-bucket", "indices": ["NDVI", ...], "years": [2018, 2025] }
```

### Check status
`GET /status?job_id=job_20250822_120102`  
Returns simple counts of files seen in your bucket under that job prefix.

### Download zip
`GET /download-zip?job_id=job_20250822_120102`  
Streams a ZIP to your browser containing all files for that job.

## Notes
- All rasters are **Float32**, **10 m**, projected in **auto‑UTM** based on your AOI.
- Empty months export as fully **masked** images (no bogus zeros).
- For huge jobs, consider splitting years or indices across runs.
- This app writes to **GCS** (not Drive). You can share signed URLs or download zips via the endpoint above.
