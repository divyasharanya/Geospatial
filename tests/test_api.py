import io
import json
import zipfile
from pathlib import Path

import geopandas as gpd
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

from app.database import Base, engine
from app.main import app
from app.services.measurement import measure_geometry
from shapely.geometry import Polygon as ShapelyPolygon

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"

def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def upload(path: Path):
    content_type = "application/zip" if path.suffix.lower() == ".zip" else "application/vnd.google-earth.kml+xml"
    return client.post("/api/files/", files={"file": (path.name, path.read_bytes(), content_type)})

def test_samples_upload_and_print_measurements():
    for sample in (SAMPLES / "features.kml", SAMPLES / "square_shapefile.zip"):
        response = upload(sample)
        assert response.status_code == 201, response.text
        file_data = response.json()
        results = client.get(f"/api/files/{file_data['id']}/measurements/").json()
        print(f"{sample.name}: {json.dumps(results['items'], indent=2)}")
        assert results["total"] > 0
        assert client.get(f"/api/files/{file_data['id']}/").json()["status"] == "COMPLETED"

def test_nested_uppercase_shapefile_and_square_area():
    source = SAMPLES / "square_shapefile.zip"
    payload = io.BytesIO()
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(payload, "w") as archive:
        for item in original.infolist():
            name = Path(item.filename)
            archive.writestr(str(name.parent / (name.stem + name.suffix.upper())), original.read(item.filename))
    response = client.post("/api/files/", files={"file": ("SAMPLE.ZIP", payload.getvalue(), "application/zip")})
    assert response.status_code == 201, response.text
    item = client.get(f"/api/files/{response.json()['id']}/measurements/").json()["items"][0]
    assert abs(item["area_m2"] - 1_000_000) < 0.01
    assert item["measurement_crs"] == "EPSG:32631"

def test_kml_folders_multigeometry_and_z_drop():
    response = upload(SAMPLES / "features.kml")
    assert response.status_code == 201, response.text
    items = client.get(f"/api/files/{response.json()['id']}/measurements/?limit=100").json()["items"]
    assert len(items) >= 4
    assert any(item["geometry_type"] in {"MultiPoint", "GeometryCollection"} for item in items)
    point = next(item for item in items if item["geometry_type"] == "Point")
    assert len(point["geometry"]["coordinates"]) == 2

def test_corrupt_zip_and_unsupported_suffix_are_client_errors():
    assert client.post("/api/files/", files={"file": ("broken.zip", b"not zip", "application/zip")}).status_code == 400
    assert client.post("/api/files/", files={"file": ("shape.SHP", b"bad", "application/octet-stream")}).status_code == 400

def test_missing_prj_failure_is_persisted_and_retrievable():
    payload = io.BytesIO()
    with zipfile.ZipFile(SAMPLES / "square_shapefile.zip") as source, zipfile.ZipFile(payload, "w") as archive:
        for item in source.infolist():
            if Path(item.filename).suffix.lower() != ".prj":
                archive.writestr(item.filename, source.read(item.filename))
    response = client.post("/api/files/", files={"file": ("no_crs.zip", payload.getvalue(), "application/zip")})
    assert response.status_code == 422, response.text
    failed = response.json()
    assert failed["id"] and failed["status"] == "FAILED" and failed["error"]
    fetched = client.get(f"/api/files/{failed['id']}/")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "FAILED" and fetched.json()["error"]

def test_empty_geometry_is_unsupported_without_error():
    result = measure_geometry(ShapelyPolygon(), "EPSG:32631")
    assert result["supported"] is False
    assert result["area_m2"] is None
