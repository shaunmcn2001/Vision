# VisionZones — UI + KMZ support + Optional Worker (Docker)

## New
- `/` now **redirects** to `/ui`.
- `/start` accepts **KMZ** uploads; converts KMZ→GeoJSON in-memory (fastkml + shapely).
- Optional **Redis RQ worker**: set `REDIS_URL` to enable job queue; otherwise threadpool.

## Deploy on Render
- Environment: **Docker**
- Health check: `/healthz`
- Secrets: `EE_PROJECT`, `EE_SERVICE_ACCOUNT_EMAIL`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`, `GCS_BUCKET`, optional `APP_BASE_URL`, optional `REDIS_URL`.
