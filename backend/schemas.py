from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UserRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)


class UserLoginRequest(BaseModel):
    email: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6, max_length=128)


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    created_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class CleaningOptions(BaseModel):
    drop_duplicates: bool = True
    trim_whitespace: bool = True
    missing_numeric: str = Field(default="zero", pattern="^(zero|median|drop)$")
    missing_text: str = Field(default="unknown", pattern="^(unknown|empty|drop)$")


class DatasetImportRequest(BaseModel):
    dataset_type: str = Field(..., pattern="^(products|customers|orders|sales|transactions|inventory)$")
    column_mapping: Dict[str, str]
    cleaning_options: CleaningOptions = Field(default_factory=CleaningOptions)


class RFMRunRequest(BaseModel):
    n_clusters: int = Field(default=5, ge=2, le=8)


class ForecastRunRequest(BaseModel):
    product_id: Optional[int] = None
    granularity: str = Field(default="weekly", pattern="^(weekly|monthly)$")
    horizon: int = Field(default=4, ge=1, le=12)


class ThresholdSettings(BaseModel):
    low_stock_threshold: int = Field(default=10, ge=1, le=10000)
    at_risk_days: int = Field(default=60, ge=7, le=730)
    rfm_clusters: int = Field(default=5, ge=2, le=8)
    forecast_horizon: int = Field(default=4, ge=1, le=12)
    anomaly_z_threshold: float = Field(default=2.0, ge=1.2, le=5.0)
