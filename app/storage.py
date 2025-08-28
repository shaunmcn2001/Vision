
import io
from typing import Iterator
from google.cloud import storage
import zipfile

def zip_gcs_prefix(bucket_name: str, prefix: str) -> Iterator[bytes]:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = list(client.list_blobs(bucket_or_name=bucket, prefix=prefix))

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for b in blobs:
            if b.name.endswith("/"):
                continue
            data = b.download_as_bytes()
            arcname = b.name[len(prefix):] if b.name.startswith(prefix) else b.name
            zf.writestr(arcname, data)
    mem.seek(0)
    yield from iter(lambda: mem.read(1024 * 64), b"")
