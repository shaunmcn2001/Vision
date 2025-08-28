# Platform Setup and Deployment Guide

## ✅ Platform Status
The Sentinel-2 Indices Exporter platform is now **fully functional** and ready for deployment!

## 🚀 Quick Start

### 1. Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn main:app --host 0.0.0.0 --port 8000

# Test the platform
python test_platform.py
```

### 2. Deploy to Render

The platform is configured for deployment on Render with the included `render.yaml` file.

**Required Environment Variables:**
- `EE_SERVICE_ACCOUNT_EMAIL`: Your Google Earth Engine service account email
- `EE_PROJECT`: Your Google Cloud project ID
- `GCS_BUCKET`: Your Google Cloud Storage bucket name  
- `GOOGLE_APPLICATION_CREDENTIALS_JSON`: Complete JSON content of your service account key

**Steps:**
1. Connect your GitHub repository to Render
2. Add the environment variables in Render dashboard (mark as secret)
3. Deploy - Render will automatically use the `render.yaml` configuration

## 🔧 Key Fixes Applied

### 1. **Fixed Startup Command**
- **Issue**: `render.yaml` referenced `app:app` but FastAPI instance is in `main.py`
- **Fix**: Updated to `main:app` in `render.yaml`
- **Added**: `app.py` for backwards compatibility

### 2. **Environment Variable Handling**
- **Issue**: App crashed if environment variables weren't set
- **Fix**: Added graceful error handling and informative messages
- **Benefit**: App starts and shows helpful configuration status

### 3. **Import Fixes**
- **Issue**: zipfile import inconsistency (`zipfile` vs `zf`)
- **Fix**: Consistent use of `zf` alias throughout codebase

### 4. **API Error Handling**
- **Added**: Service availability checks in all endpoints
- **Added**: Clear error messages when credentials are missing
- **Added**: Helpful health endpoint for debugging

## 📋 API Endpoints

### `GET /` - Home
Returns platform information and default settings.

### `GET /health` - Health Check
Shows service status and configuration problems.

### `POST /start` - Start Export Job
Accepts boundary files and starts satellite data export.

### `GET /status?job_id=<id>` - Job Status
Check progress of export jobs.

### `GET /download-zip?job_id=<id>` - Download Results
Download processed satellite imagery as ZIP.

## 🧪 Testing

Run the included test suite:
```bash
python test_platform.py
```

This tests:
- ✅ API endpoints respond correctly
- ✅ Error handling works properly  
- ✅ App loads with/without credentials
- ✅ Service availability checks

## 📝 Notes

- Platform gracefully handles missing credentials for development
- All endpoints provide clear error messages
- Health endpoint helps diagnose configuration issues
- Compatible with both `main:app` and `app:app` startup methods
- Ready for production deployment on Render