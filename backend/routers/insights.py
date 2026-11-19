from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User
from backend.security import get_current_user
from backend.services.insights_service import generate_smart_alerts

router = APIRouter(prefix="/api/insights", tags=["Smart Insights & Alerts"])


@router.get("/alerts")
def get_alerts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return generate_smart_alerts(db, current_user.id)


@router.get("/recommendations")
def get_recommendations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return generate_smart_alerts(db, current_user.id)
