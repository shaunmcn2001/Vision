
import io, zipfile, json
from typing import Dict, Any, List, Tuple
from fastkml import kml
from shapely.geometry import mapping, shape, Polygon, MultiPolygon
from shapely.ops import unary_union
import shapefile  # pyshp

def _merge_geoms(geoms):
    merged = unary_union(geoms)
    if isinstance(merged, Polygon):
        geom = mapping(merged)
    else:
        geom = mapping(MultiPolygon([g for g in merged.geoms]))
    return {"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":geom}]}

def from_kmz_or_kml(filename: str, raw: bytes) -> Dict[str, Any]:
    name = (filename or "").lower()
    if name.endswith(".kmz"):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            kml_name = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
            if not kml_name:
                raise ValueError("KMZ contains no .kml")
            raw = z.read(kml_name)
    # now parse KML
    doc = kml.KML()
    doc.from_string(raw)
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
        raise ValueError("No geometries found in KML")
    return _merge_geoms(geoms)

def from_geojson(raw: bytes) -> Dict[str, Any]:
    obj = json.loads(raw.decode("utf-8"))
    # normalize into FeatureCollection with Polygon/MultiPolygon
    if obj.get("type") == "FeatureCollection":
        # merge all polygonal features
        polys = []
        for f in obj["features"]:
            g = f.get("geometry") or {}
            if g and g.get("type") in ("Polygon","MultiPolygon"):
                polys.append(shape(g))
        if not polys:
            raise ValueError("No polygon geometry in FeatureCollection")
        return _merge_geoms(polys)
    elif obj.get("type") == "Feature":
        g = obj.get("geometry") or {}
        if g.get("type") not in ("Polygon","MultiPolygon"):
            raise ValueError("Feature is not Polygon/MultiPolygon")
        return {"type":"FeatureCollection","features":[{"type":"Feature","properties":{}, "geometry":g}]}
    elif obj.get("type") in ("Polygon","MultiPolygon"):
        return {"type":"FeatureCollection","features":[{"type":"Feature","properties":{}, "geometry":obj}]}
    else:
        raise ValueError("Unsupported GeoJSON type")

def from_shapefile_zip(raw: bytes) -> Dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        # Collect components
        shp_name = next((n for n in z.namelist() if n.lower().endswith(".shp")), None)
        shx_name = next((n for n in z.namelist() if n.lower().endswith(".shx")), None)
        dbf_name = next((n for n in z.namelist() if n.lower().endswith(".dbf")), None)
        if not (shp_name and shx_name and dbf_name):
            raise ValueError("ZIP must contain .shp, .shx, .dbf")
        shp = io.BytesIO(z.read(shp_name))
        shx = io.BytesIO(z.read(shx_name))
        dbf = io.BytesIO(z.read(dbf_name))
        r = shapefile.Reader(shp=shp, shx=shx, dbf=dbf)
        geoms = []
        for s in r.shapes():
            # Only polygons
            if s.shapeType in (shapefile.POLYGON, shapefile.POLYGONZ, shapefile.POLYGONM):
                parts = list(s.parts) + [len(s.points)]
                rings = []
                for i in range(len(parts)-1):
                    ring = [(x,y) for x,y,*rest in s.points[parts[i]:parts[i+1]]]
                    rings.append(ring)
                if len(rings) >= 1:
                    geoms.append(Polygon(rings[0], holes=rings[1:]))
        if not geoms:
            raise ValueError("No polygon geometry in shapefile")
        return _merge_geoms(geoms)

def parse_boundary(filename: str, raw: bytes) -> Dict[str, Any]:
    name = (filename or "").lower()
    if name.endswith(".kmz") or name.endswith(".kml"):
        return from_kmz_or_kml(filename, raw)
    if name.endswith(".zip"):
        return from_shapefile_zip(raw)
    # else try GeoJSON
    return from_geojson(raw)
