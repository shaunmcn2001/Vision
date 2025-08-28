
import os, hashlib, json
from typing import List, Dict, Any, Optional
from google.cloud import firestore

def _client():
    project = os.environ.get("FIRESTORE_PROJECT_ID") or os.environ.get("EE_PROJECT")
    if not project:
        raise RuntimeError("FIRESTORE_PROJECT_ID or EE_PROJECT must be set")
    return firestore.Client(project=project)

def _id_for_geom(geojson: Dict[str, Any]) -> str:
    h = hashlib.sha256(json.dumps(geojson, sort_keys=True).encode()).hexdigest()[:16]
    return h

def bounds_of(geojson: Dict[str, Any]):
    def coords(g):
        t = g.get("type")
        if t == "Polygon":
            for ring in g["coordinates"]:
                for x, y in ring:
                    yield x, y
        elif t == "MultiPolygon":
            for poly in g["coordinates"]:
                for ring in poly:
                    for x, y in ring:
                        yield x, y
    if geojson.get("type")=="Feature":
        g = geojson["geometry"]
    elif geojson.get("type")=="FeatureCollection":
        g = geojson["features"][0]["geometry"]
    else:
        g = geojson
    xs, ys = zip(*list(coords(g)))
    return [min(xs), min(ys), max(xs), max(ys)]

def create_paddock(name: str, geometry: Dict[str, Any]) -> Dict[str, Any]:
    db = _client()
    pid = _id_for_geom(geometry)
    doc = {
        "id": pid,
        "name": name,
        "geometry": geometry,
        "bounds": bounds_of(geometry),
    }
    db.collection("paddocks").document(pid).set(doc)
    return doc

def list_paddocks() -> List[Dict[str, Any]]:
    db = _client()
    docs = db.collection("paddocks").stream()
    return [d.to_dict() for d in docs]

def get_paddock(pid: str) -> Optional[Dict[str, Any]]:
    db = _client()
    snap = db.collection("paddocks").document(pid).get()
    return snap.to_dict() if snap.exists else None
