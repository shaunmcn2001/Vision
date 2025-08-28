
import os, time
from typing import Optional, Dict, Any
import ee

def _geom_from_geojson(geojson: Dict[str, Any]) -> ee.Geometry:
    if geojson.get("type") == "FeatureCollection":
        feats = [ee.Feature(f["geometry"]) for f in geojson["features"]]
        return ee.FeatureCollection(feats).geometry()
    if geojson.get("type") == "Feature":
        return ee.Geometry(geojson["geometry"])
    return ee.Geometry(geojson)

def _s2_mask_scl(img: ee.Image) -> ee.Image:
    scl = img.select("SCL")
    mask = scl.neq(0).And(scl.neq(2)).And(scl.neq(3)).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
    return img.updateMask(mask)

def _add_ndvi(img: ee.Image) -> ee.Image:
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
    return img.addBands(ndvi)

def _years_range(start_year: Optional[int], end_year: Optional[int]):
    import datetime
    y0 = start_year or 2018
    y1 = end_year or datetime.date.today().year
    return list(range(y0, y1 + 1))

def run_zone_export(job_id: str, geojson: Dict[str, Any], k: int = 5,
                    start_year: Optional[int] = None, end_year: Optional[int] = None):
    region = _geom_from_geojson(geojson)
    bucket = os.environ["GCS_BUCKET"]
    years = _years_range(start_year, end_year)

    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filterBounds(region)
           .filterDate(f"{years[0]}-01-01", f"{years[-1]}-12-31")
           .map(_s2_mask_scl)
           .map(_add_ndvi)
           .select(["NDVI","B8","B4","SCL"]))

    ndvi_median = col.select("NDVI").median().rename("NDVI_MED")
    ndvi_p80 = col.select("NDVI").reduce(ee.Reducer.percentile([80])).rename(["NDVI_P80"])
    feature_stack = ndvi_median.addBands(ndvi_p80)

    training = feature_stack.sample(region=region, scale=10, numPixels=5000, geometries=False, seed=13)
    clusterer = ee.Clusterer.wekaKMeans(k).train(training)
    clustered = feature_stack.cluster(clusterer).rename("ZONE")

    zone_tif_task = ee.batch.Export.image.toCloudStorage(
        image=clustered.toInt(),
        description=f"{job_id}_zones_k{k}_tif",
        bucket=bucket,
        fileNamePrefix=f"{job_id}/zones_k{k}",
        fileFormat="GeoTIFF",
        region=region,
        scale=10,
        maxPixels=1e13
    )
    zone_tif_task.start()

    while zone_tif_task.active():
        time.sleep(10)

    state = zone_tif_task.status().get("state")
    if state != "COMPLETED":
        raise RuntimeError(f"Raster export failed: {zone_tif_task.status()}")
