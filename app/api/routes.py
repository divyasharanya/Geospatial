import logging
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import FileRecord, FeatureRecord
from ..schemas import FileSummary, FeatureResult, MeasurementPage
from ..services.files import create_upload, UploadError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/files", tags=["files"])

@router.post("/", response_model=FileSummary, status_code=201, responses={422: {"model": FileSummary}})
def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        record = create_upload(file.filename, file.file, db)
    except UploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    summary = FileSummary.model_validate(record)
    if record.status == "FAILED":
        # Return the persisted ID with the failure so clients can inspect it later.
        return JSONResponse(status_code=422, content=summary.model_dump())
    return summary

@router.get("/{file_id}/", response_model=FileSummary)
def get_file(file_id: str, db: Session = Depends(get_db)):
    record = db.get(FileRecord, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    return record

@router.get("/{file_id}/measurements/", response_model=MeasurementPage)
def get_measurements(file_id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    if not db.get(FileRecord, file_id):
        raise HTTPException(status_code=404, detail="File not found")
    total = db.scalar(select(func.count()).select_from(FeatureRecord).where(FeatureRecord.file_id == file_id)) or 0
    rows = db.scalars(select(FeatureRecord).where(FeatureRecord.file_id == file_id).order_by(FeatureRecord.feature_index).offset(offset).limit(limit)).all()
    items = [FeatureResult(index=row.feature_index, geometry_type=row.geometry_type, geometry=row.geometry,
        crs=row.crs, properties=row.properties, supported=row.supported, area_m2=row.area_m2,
        area_hectares=row.area_hectares, length_m=row.length_m, length_km=row.length_km,
        measurement_crs=row.measurement_crs) for row in rows]
    return MeasurementPage(items=items, total=total, limit=limit, offset=offset)
