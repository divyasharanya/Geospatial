# geospatial-measurement-api

FastAPI service for KML and zipped ESRI Shapefile uploads, persistent feature measurements, and paginated retrieval.

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Default SQLite storage is `./geospatial.db`; source uploads are stored under `./uploads`. Override with `DATABASE_URL` and `UPLOAD_DIR`. Docker: `docker build -t geospatial-measurement-api .` followed by `docker run --rm -p 8000:8000 geospatial-measurement-api`.

## Samples and API

Ready-to-upload examples are in `samples/`: `features.kml` contains polygon, line, point, folders, and a MultiGeometry; `square_shapefile.zip` contains a 1 km by 1 km polygon and its `.shp`, `.shx`, `.dbf`, and `.prj` sidecars inside a nested folder. `python scripts/create_samples.py` regenerates the zipped shapefile sample. Tests upload both sample files and print their measurements.

Upload with multipart field `file` (maximum 50 MiB):

```bash
curl -F 'file=@samples/features.kml' http://localhost:8000/api/files/
curl -F 'file=@samples/square_shapefile.zip' http://localhost:8000/api/files/
curl http://localhost:8000/api/files/{id}/
curl 'http://localhost:8000/api/files/{id}/measurements/?limit=100&offset=0'
```

Successful upload response (example):

```json
{"id":"4e8ccf90-282f-42d4-87d0-aec6ab473d53","filename":"square_shapefile.zip","feature_count":1,"crs":"EPSG:32631","status":"COMPLETED","error":null}
```

`GET /api/files/{id}/` returns the file record:

```json
{"id":"4e8ccf90-282f-42d4-87d0-aec6ab473d53","filename":"square_shapefile.zip","feature_count":1,"crs":"EPSG:32631","status":"COMPLETED","error":null}
```

A measurements response contains a paginated `items` array. One item looks like:

```json
{"index":0,"geometry_type":"Polygon","geometry":{"type":"Polygon","coordinates":[[[500000,0],[501000,0],[501000,1000],[500000,1000],[500000,0]]]},"crs":"EPSG:32631","properties":{"name":"1 km x 1 km square"},"supported":true,"area_m2":1000000.0,"area_hectares":100.0,"length_m":null,"length_km":null,"measurement_crs":"EPSG:32631"}
```

Processing failures return 422 with the saved record ID, status, and error; use that ID with the GET endpoint to inspect it. Invalid input returns 400, unknown IDs 404, and invalid pagination 422. OpenAPI docs are at `/docs`.

## Architecture and CRS decisions

`app/api` provides HTTP routes; `app/services` validates, reads, and measures data; SQLAlchemy models persist file records and feature JSON/numeric values; Pydantic schemas define responses. Upload processing is synchronous. ZIP paths are checked before isolated extraction. All shapefile component suffixes are treated case-insensitively; matching `.shp`, `.shx`, and `.dbf` files are required.

Shapely `make_valid` repairs invalid geometries and Z coordinates are dropped. Polygon/MultiPolygon area and LineString/MultiLineString length are measured in metres. Geographic data uses a centroid-selected UTM zone, with EPSG:6933 near the poles; projected metre CRSs are used directly. Other projected CRSs are converted to a local metric CRS. Points have no measurement. Empty/null and unsupported geometries are marked unsupported. Missing CRS cannot be measured and results in a persisted FAILED record. Returned geometries retain the source coordinates and CRS.

## Tests

Run `python -m pytest -q`. The tests upload both bundled samples and print each measurement result, and cover nested/uppercase shapefile entries, area sanity, KML folders/MultiGeometry/Z, missing `.prj`, corrupt ZIP, and empty geometry.

## Learnings and future scope

- I learned that calculating area in degrees gives misleading results, so I project geographic data before measuring.
- I learned how a feature's centroid helps choose its local UTM zone for metric measurements.
- I learned that shapefiles rely on matching sidecar files such as `.shp`, `.shx`, `.dbf`, and `.prj`.

Future work could add background processing for large files, storage retention policies, database migrations, and explicit antimeridian handling.
