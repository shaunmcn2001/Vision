
import io, zipfile, json
from typing import Dict, Any
from fastkml import kml
from shapely.geometry import mapping, shape, Polygon, MultiPolygon
from shapely.ops import unary_union

def _parse_kml_bytes(kml_bytes: bytes):
    doc = kml.KML()
    doc.from_string(kml_bytes)
    geoms = []

    def visit(el):
        from fastkml.kml import Placemark
        if isinstance(el, Placemark) and el.geometry is not None:
            geoms.append(shape(el.geometry.geojson))
        for c in getattr(el, 'features', []) or []:
            visit(c)

    for f in doc.features():
        visit(f)

    if not geoms:
        raise ValueError("No geometries found in KML.")

    merged = unary_union(geoms)
    if isinstance(merged, Polygon):
        geom = mapping(merged)
    else:
        geom = mapping(MultiPolygon([g for g in merged.geoms]))

    fc = {"type": "FeatureCollection",
          "features": [{"type": "Feature", "properties": {}, "geometry": geom}]}
    return fc

def maybe_kmz_to_geojson(filename: str, raw: bytes) -> Dict[str, Any]:
    name = (filename or "").lower()
    if name.endswith(".kmz"):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            kml_name = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
            if not kml_name:
                raise ValueError("KMZ contains no .kml file.")
            kml_bytes = z.read(kml_name)
        return _parse_kml_bytes(kml_bytes)
    elif name.endswith(".kml"):
        return _parse_kml_bytes(raw)
    else:
        raise ValueError("Not a KMZ/KML file")
