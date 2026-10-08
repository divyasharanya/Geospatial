from typing import Any
from pydantic import BaseModel, ConfigDict

class FileSummary(BaseModel):
    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: str
    model_config = ConfigDict(from_attributes=True)

class FeatureResult(BaseModel):
    index: int
    geometry_type: str | None
    geometry: dict[str, Any] | None
    crs: str | None
    properties: dict[str, Any]
    supported: bool
    area_m2: float | None
    area_hectares: float | None
    length_m: float | None
    length_km: float | None
    measurement_crs: str | None

class MeasurementPage(BaseModel):
    items: list[FeatureResult]
    total: int
    limit: int
    offset: int
