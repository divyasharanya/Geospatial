import io
import logging
import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO

import geopandas as gpd
from sqlalchemy.orm import Session

from ..models import FileRecord, FeatureRecord
from .measurement import measure_geometry, _json_value

logger = logging.getLogger(__name__)
MAX_BYTES = 50 * 1024 * 1024
DATA_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))

class UploadError(Exception):
    pass

def validate_upload(filename: str | None, stream: BinaryIO) -> tuple[str, bytes]:
    if not filename:
        raise UploadError("A filename is required")
    safe_name = Path(filename.replace("\\", "/")).name
    ext = Path(safe_name).suffix.lower()
    if ext not in {".kml", ".zip"}:
        raise UploadError("Only .kml and .zip files are supported")
    stream.seek(0)
    chunks, total = [], 0
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_BYTES:
            raise UploadError("File exceeds the 50 MB limit")
        chunks.append(chunk)
    data = b"".join(chunks)
    if ext == ".zip":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                stems: dict[str, set[str]] = {}
                for entry in entries:
                    normalized = entry.filename.replace("\\", "/")
                    parts = normalized.split("/")
                    if normalized.startswith("/") or any(part == ".." for part in parts) or (parts and ":" in parts[0]):
                        raise UploadError("ZIP contains an unsafe path")
                    if not entry.is_dir():
                        member = Path(parts[-1])
                        stems.setdefault(member.stem.lower(), set()).add(member.suffix.lower())
                required = {".shp", ".shx", ".dbf"}
                if not any(required.issubset(suffixes) for suffixes in stems.values()):
                    raise UploadError("ZIP must contain matching .shp, .shx, and .dbf files")
        except zipfile.BadZipFile as exc:
            raise UploadError("Invalid or corrupt ZIP file") from exc
    return safe_name, data

def _read_layers(path: Path, ext: str):
    if ext == ".kml":
        layers = gpd.list_layers(path)
        if layers.empty:
            return []
        return [gpd.read_file(path, layer=row["name"], engine="pyogrio") for _, row in layers.iterrows()]
    # Extract the validated archive into an isolated temp directory. This supports
    # both root-level and nested shapefiles and handles uppercase sidecar suffixes.
    with tempfile.TemporaryDirectory(prefix="geospatial-") as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(path) as archive:
            archive.extractall(root)
        candidates = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".shp"]
        if not candidates:
            raise ValueError("ZIP contains no shapefile")
        return [gpd.read_file(candidate, engine="pyogrio") for candidate in sorted(candidates)]

def process_file(record: FileRecord, db: Session) -> None:
    try:
        layers = _read_layers(Path(record.stored_path), Path(record.filename).suffix.lower())
        feature_index = 0
        file_crs = None
        for frame in layers:
            if frame.crs:
                file_crs = frame.crs.to_string()
            for _, row in frame.iterrows():
                geom = row.geometry
                if geom is not None and getattr(geom, "has_z", False):
                    from shapely import force_2d
                    geom = force_2d(geom)
                props = {str(key): _json_value(value) for key, value in row.drop(labels=[frame.geometry.name]).items()}
                measured = measure_geometry(geom, frame.crs.to_string() if frame.crs else None)
                db.add(FeatureRecord(file_id=record.id, feature_index=feature_index,
                    geometry_type=measured["geometry_type"], geometry=measured["geometry"],
                    crs=measured["crs"], properties=props, supported=measured["supported"],
                    area_m2=measured["area_m2"], area_hectares=measured["area_hectares"],
                    length_m=measured["length_m"], length_km=measured["length_km"],
                    measurement_crs=measured["measurement_crs"]))
                feature_index += 1
        record.crs, record.feature_count, record.status = file_crs, feature_index, "COMPLETED"
        db.commit()
    except Exception as exc:
        logger.exception("Failed to process uploaded file %s", record.id)
        db.rollback()
        record = db.get(FileRecord, record.id)
        if record:
            record.status, record.error = "FAILED", str(exc)[:2000]
            db.commit()

def create_upload(filename: str | None, stream: BinaryIO, db: Session) -> FileRecord:
    name, data = validate_upload(filename, stream)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4()
    dest = DATA_DIR / f"{file_id}{Path(name).suffix.lower()}"
    dest.write_bytes(data)
    record = FileRecord(id=str(file_id), filename=name, stored_path=str(dest), status="PROCESSING")
    db.add(record)
    db.commit()
    db.refresh(record)
    process_file(record, db)
    db.refresh(record)
    return record
