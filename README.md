
# VisionZones — Docker + Web UI + Optional Worker

## What's new
- **/ui**: simple browser uploader + status poller
- **Optional background queue**: if `REDIS_URL` is set, `/start` enqueues jobs to Redis and the **worker** service processes them.

## Deploy on Render
1. New Web Service → Environment: **Docker** (uses this Dockerfile).
2. Health check: `/healthz`.
3. Secrets (web service): `EE_PROJECT`, `EE_SERVICE_ACCOUNT_EMAIL`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`, `GCS_BUCKET`, `APP_BASE_URL` (optional), `REDIS_URL` (optional).
4. (Optional) Create **Worker** service from `render.yaml` (it uses `python -m app.worker`). Set the same secrets plus `REDIS_URL`.

## UI
Open `<URL>/ui` to upload a GeoJSON and watch status. When done, click **Download ZIP**.

## API
- `POST /start` → returns `job_id`
- `GET /status?job_id=...`
- `GET /download-zip?job_id=...`
