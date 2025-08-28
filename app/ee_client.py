
import os
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

    if sa_email and creds_json:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(creds_json)
            key_path = f.name
        credentials = ee.ServiceAccountCredentials(sa_email, key_path)
        ee.Initialize(credentials=credentials, project=project)
    else:
        ee.Initialize(project=project)

    _ee_initialized = True
