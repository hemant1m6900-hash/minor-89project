from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import check_db_connection, engine, get_db
from backend.models import User
from backend.schemas import ThresholdSettings
from backend.security import get_current_user
from backend.services.analytics_service import get_user_thresholds, save_user_thresholds

router = APIRouter(prefix="/api/settings", tags=["Settings"])


@router.get("")
def get_settings_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    app_settings = get_settings()
    return {
        "thresholds": get_user_thresholds(db, current_user.id),
        "system": {
            "database_dialect": "SQLite (ecommerce_intelligence.db)" if engine.dialect.name == "sqlite" else engine.dialect.name,
            "database_connected": check_db_connection(),
            "upload_dir": str(app_settings.upload_dir),
        },
    }


@router.put("")
def update_settings_endpoint(
    payload: ThresholdSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    saved = save_user_thresholds(db, current_user.id, payload.model_dump())
    return {"thresholds": saved, "message": "Settings updated successfully."}
