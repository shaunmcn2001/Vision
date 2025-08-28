
from typing import Dict, Any, Optional
import ee

def _geom(geojson: Dict[str, Any]) -> ee.Geometry:
    if geojson.get("type") == "FeatureCollection":
        return ee.FeatureCollection([ee.Feature(f["geometry"]) for f in geojson["features"]]).geometry()
    if geojson.get("type") == "Feature":
        return ee.Geometry(geojson["geometry"])
    return ee.Geometry(geojson)

def _s2_mask(img: ee.Image) -> ee.Image:
    scl = img.select("SCL")
    mask = scl.neq(0).And(scl.neq(2)).And(scl.neq(3)).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
    return img.updateMask(mask)

def ndvi_median_image(geometry: Dict[str, Any], start_year: int, end_year: int) -> ee.Image:
    region = _geom(geometry)
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filterBounds(region)
           .filterDate(f"{start_year}-01-01", f"{end_year}-12-31")
           .map(_s2_mask)
           .map(lambda img: img.addBands(img.normalizedDifference(["B8","B4"]).rename("NDVI"))))
    ndvi = col.select("NDVI").median()
    return ndvi.clip(region)

def zones_image(geometry: Dict[str, Any], start_year: int, end_year: int, k: int = 5) -> ee.Image:
    region = _geom(geometry)
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filterBounds(region)
           .filterDate(f"{start_year}-01-01", f"{end_year}-12-31")
           .map(_s2_mask)
           .map(lambda img: img.addBands(img.normalizedDifference(["B8","B4"]).rename("NDVI"))))
    ndvi_med = col.select("NDVI").median().rename("NDVI_MED")
    ndvi_p80 = col.select("NDVI").reduce(ee.Reducer.percentile([80])).rename(["NDVI_P80"])
    features = ndvi_med.addBands(ndvi_p80)
    training = features.sample(region=region, scale=10, numPixels=5000, geometries=False, seed=13)
    clusterer = ee.Clusterer.wekaKMeans(k).train(training)
    clustered = features.cluster(clusterer).rename("ZONE").clip(region)
    return clustered

def tile_url_for(image: ee.Image, vis: Dict[str, Any]) -> str:
    # Use classic getMapId flow to get a tile URL template
    mp = image.getMapId(vis)
    # mp['tile_fetcher'].url_format is like: 'https://earthengine.googleapis.com/map/{mapid}/{z}/{x}/{y}?token={token}'
    return mp["tile_fetcher"].url_format
