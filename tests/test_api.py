import io
import zipfile
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Polygon, LineString, Point, MultiPolygon
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine

client = TestClient(app)

def _zip_shapefile(tmp_path, include_prj=True):
    shp_dir = tmp_path / "shape"
    shp_dir.mkdir()
    poly = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    frame = gpd.GeoDataFrame({"name": ["square", "line", "point", "multi"]}, geometry=[
        poly, LineString([(0, 0), (1000, 0)]), Point(10, 10),
        MultiPolygon([Polygon([(0,0),(10,0),(10,10),(0,10)]), Polygon([(20,0),(30,0),(30,10),(20,10)])])
    ], crs="EPSG:32631")
    shp = shp_dir / "sample.shp"
    frame.to_file(shp, engine="pyogrio")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in shp_dir.iterdir():
            if include_prj or path.suffix.lower() != ".prj":
                archive.write(path, path.name)
    return buffer.getvalue()

def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def test_shapefile_measurements_and_pagination(tmp_path):
    payload = _zip_shapefile(tmp_path)
    response = client.post("/api/files/", files={"file": ("sample.zip", payload, "application/zip")})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["feature_count"] == 4
    results = client.get(f"/api/files/{data['id']}/measurements/?limit=2").json()
    assert results["total"] == 4 and len(results["items"]) == 2
    assert abs(results["items"][0]["area_m2"] - 1_000_000) < 1
    assert abs(results["items"][0]["area_hectares"] - 100) < 0.001
    next_page = client.get(f"/api/files/{data['id']}/measurements/?offset=1").json()["items"]
    assert next_page[0]["length_m"] == 1000
    assert next_page[1]["geometry_type"] == "Point" and next_page[1]["area_m2"] is None
    assert next_page[2]["geometry_type"] == "MultiPolygon" and next_page[2]["area_m2"] is not None

def test_kml_upload(tmp_path):
    kml = b'''<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>p</name><Point><coordinates>3,4,100</coordinates></Point></Placemark></Document></kml>'''
    response = client.post("/api/files/", files={"file": ("sample.kml", kml, "application/vnd.google-earth.kml+xml")})
    assert response.status_code == 201, response.text
    result = client.get(f"/api/files/{response.json()['id']}/measurements/").json()["items"][0]
    assert result["geometry_type"] == "Point"
    assert result["geometry"]["coordinates"] == [3.0, 4.0]

def test_bad_zip_and_missing_required_sidecars(tmp_path):
    corrupt = client.post("/api/files/", files={"file": ("broken.zip", b"not zip", "application/zip")})
    assert corrupt.status_code == 400
    missing = client.post("/api/files/", files={"file": ("missing.zip", _zip_shapefile(tmp_path, include_prj=False), "application/zip")})
    assert missing.status_code == 422

def test_invalid_extension_and_missing_id():
    assert client.post("/api/files/", files={"file": ("x.txt", b"x", "text/plain")}).status_code == 400
    assert client.get("/api/files/no-such-id/").status_code == 404
