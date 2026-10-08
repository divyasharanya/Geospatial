# geospatial-measurement-api

FastAPI service that accepts KML or zipped ESRI Shapefile datasets, stores each upload and its processed feature measurements in SQLite, and exposes paginated results.

## Setup

Requires Python 3.10+ and GDAL support for the installed pyogrio/Fiona wheels. Install and run:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The default database is `./geospatial.db`; uploaded originals are kept under `./uploads`. Set `DATABASE_URL` and `UPLOAD_DIR` to override these locations. Docker is also supported with `docker build -t geospatial-measurement-api .` then `docker run -p 8000:8000 geospatial-measurement-api`.

## API

Upload using multipart field `file` (maximum 50 MiB):

```bash
curl -F 'file=@roads.kml' http://localhost:8000/api/files/
curl -F 'file=@parcels.zip' http://localhost:8000/api/files/
curl http://localhost:8000/api/files/{id}/
curl 'http://localhost:8000/api/files/{id}/measurements/?limit=100&offset=0'
```

Upload returns a file summary. Measurements return `{items,total,limit,offset}`; every item includes its feature index, geometry, source CRS, properties, supported flag, measurement CRS, and nullable area/length values. Invalid input gets 400, processing failures get 422, unknown ids get 404, and invalid pagination gets FastAPI's 422 response. Interactive OpenAPI docs are at `/docs`.

## Architecture

`app/api` handles HTTP and validation; `app/services` validates uploads and reads/measures geospatial data; `app/models.py` defines SQLAlchemy file and feature tables; `app/schemas.py` defines response contracts. Processing is synchronous: a successful upload is fully parsed and measured before the response returns. SQLite stores JSON geometry/properties alongside numeric measurements to support stable pagination without reparsing.

## CRS handling and design decisions

Geometry is made valid with Shapely `make_valid`; Z coordinates are dropped. Polygonal areas and line lengths are measured after projecting geographic features to a centroid-selected UTM zone. Features near the poles use EPSG:6933. Projected metre CRSs are measured directly; other projected CRSs are transformed to a local metric CRS. Point geometries have no measurement; null, empty, and unsupported geometry types are marked unsupported. Measurements are never calculated in angular degrees. Feature geometry remains in its input CRS in the response.

ZIPs are inspected for traversal paths and required `.shp`, `.shx`, `.dbf` members before GDAL reads them. A `.prj` file is not required by the container validation, but a missing CRS prevents metric measurement and produces a processing error (422). This keeps CRS assumptions explicit rather than silently assigning one.

## Tests

Run `pytest`. The suite covers KML Z removal, zipped shapefile polygon area (1 km² sanity check), line, point, multipolygon, corrupt ZIP, missing CRS sidecar, validation and 404 behavior.

## Learnings and future scope

Per-feature local projections avoid treating angular units as metres and make measurements useful across zones, with expected local-projection distortion for very large geometries. Synchronous processing keeps the API simple for modest files; a production deployment should consider a task queue, object storage, upload quotas/authentication, geometry simplification, and explicit antimeridian handling. File retention and database migrations also need operational policies as usage grows.
