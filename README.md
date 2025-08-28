
# VisionZones — FastAPI + Earth Engine (Dockerized)

Deploy this containerized app on Render or Google Cloud Run.

## Features
- Upload a GeoJSON boundary
- Run Sentinel-2 NDVI-based clustering (k-means, 3/5/7 zones)
- Export zone GeoTIFFs to Google Cloud Storage
- Check status and download ZIPs of outputs

## Deploy on Render
1. Push this repo to GitHub.
2. New Web Service → Environment: **Docker**.
3. Health check path: `/healthz`.
4. Add secrets: `EE_PROJECT`, `EE_SERVICE_ACCOUNT_EMAIL`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`, `GCS_BUCKET`, `APP_BASE_URL`.
5. Deploy.

## Endpoints
- `GET /` → service info
- `GET /healthz` → health check
- `POST /start` → start job
- `GET /status?job_id=...` → job status
- `GET /download-zip?job_id=...` → download outputs
- `GET /docs` → API docs (Swagger UI)
