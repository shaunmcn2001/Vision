
import os
import json
import tempfile
import ee

_ee_initialized = False

def ensure_ee():
    global _ee_initialized
    if _ee_initialized:
        return

    project = os.environ.get("EE_PROJECT")
    sa_email = os.environ.get("EE_SERVICE_ACCOUNT_EMAIL")
    creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")

    if not project:
        raise RuntimeError("EE_PROJECT not set")

    # Prefer ADC from JSON pasted in env (writes to a temp key file)
    if sa_email and creds_json:
        # Service account key file path
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(creds_json)
            key_path = f.name
        credentials = ee.ServiceAccountCredentials(sa_email, key_path)
        ee.Initialize(credentials=credentials, project=project)
    else:
        # Fall back to default credentials (e.g., Workload Identity on Cloud Run)
        ee.Initialize(project=project)

    _ee_initialized = True
