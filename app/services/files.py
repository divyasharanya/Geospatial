import logging
import os
import tempfile
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
            with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
                entries = archive.infolist()
                for item in entries:
                    normalized = item.filename.replace("\\", "/")
                    if normalized.startswith("/") or any(part == ".." for part in normalized.split("/")):
                        raise UploadError("ZIP contains an unsafe path")
                names = {Path(e.filename.replace("\\", "/")).name.lower() for e in entries if not e.is_dir()}
                if not {".shp", ".shx", ".dbf"}.issubset({Path(n).suffix for n in names}):
                    raise UploadError("ZIP must contain .shp, .shx, and .dbf files")
        except zipfile.BadZipFile as exc:
            raise UploadError("Invalid or corrupt ZIP file") from exc
    return safe_name, data

def _read_layers(path: Path, ext: str):
    if ext == ".kml":
        import fiona
        try:
            fiona.drvsupport.supported_drivers["KML"] = "rw"
        except Exception:
            pass
        layers = gpd.list_layers(path)
        if layers.empty:
            return []
        return [gpd.read_file(path, layer=row["name"], engine="pyogrio") for _, row in layers.iterrows()]
    return [gpd.read_file(path, engine="pyogrio")]

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
                    geom = __import__("shapely").force_2d(geom)
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
    file_id = __import__("uuid").uuid4()
    dest = DATA_DIR / f"{file_id}{Path(name).suffix.lower()}"
    dest.write_bytes(data)
    record = FileRecord(id=str(file_id), filename=name, stored_path=str(dest), status="PROCESSING")
    db.add(record)
    db.commit()
    db.refresh(record)
    process_file(record, db)
    db.refresh(record)
    return record
