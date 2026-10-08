import logging
import math
from typing import Any
import geopandas as gpd
from pyproj import CRS
from shapely import make_valid
from shapely.geometry import mapping

logger = logging.getLogger(__name__)

def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value
    if hasattr(value, "item"):
        return _json_value(value.item())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)

def _measurement_crs(geom, source: CRS) -> CRS:
    if source.is_geographic:
        centroid = geom.centroid
        if abs(centroid.y) >= 84 or abs(centroid.y) <= -80:
            return CRS.from_epsg(6933)
        zone = max(1, min(60, int((centroid.x + 180) // 6) + 1))
        return CRS.from_epsg((32600 if centroid.y >= 0 else 32700) + zone)
    if source.is_projected:
        axes = source.axis_info
        # Only use a projected CRS as-is when its horizontal units are metres.
        if len(axes) >= 2 and all(axis.unit_name.lower() in {"metre", "meter"} for axis in axes[:2]):
            return source
        # Convert non-metre projected coordinates through lon/lat to a local metric CRS.
        lonlat = gpd.GeoSeries([geom], crs=source).to_crs("EPSG:4326").iloc[0]
        return _measurement_crs(lonlat, CRS.from_epsg(4326))
    raise ValueError(f"Unsupported CRS for measurement: {source.to_string()}")

def measure_geometry(geometry, source_crs: str | None) -> dict:
    result = {"geometry_type": geometry.geom_type if geometry is not None else None,
              "geometry": mapping(geometry) if geometry is not None else None,
              "crs": source_crs, "supported": True, "area_m2": None,
              "area_hectares": None, "length_m": None, "length_km": None,
              "measurement_crs": None}
    if geometry is None or geometry.is_empty:
        result["supported"] = False
        return result
    geom = make_valid(geometry) if not geometry.is_valid else geometry
    result["geometry_type"] = geom.geom_type
    result["geometry"] = mapping(geom)
    kind = geom.geom_type
    if kind not in {"Polygon", "MultiPolygon", "LineString", "MultiLineString", "Point", "MultiPoint"}:
        result["supported"] = False
        return result
    if kind in {"Point", "MultiPoint"}:
        return result
    if source_crs is None:
        raise ValueError("Input layer has no CRS")
    source = CRS.from_user_input(source_crs)
    target = _measurement_crs(geom, source)
    result["measurement_crs"] = target.to_string()
    projected = gpd.GeoSeries([geom], crs=source).to_crs(target).iloc[0]
    if kind in {"Polygon", "MultiPolygon"}:
        result["area_m2"] = float(projected.area)
        result["area_hectares"] = float(projected.area / 10_000)
    else:
        result["length_m"] = float(projected.length)
        result["length_km"] = float(projected.length / 1_000)
    return result
