from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User
from backend.security import get_current_user
from backend.services.analytics_service import (
    get_dashboard_analytics,
    get_data_capabilities,
    get_sales_analytics,
)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/data-capabilities")
def data_capabilities(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return get_data_capabilities(db, current_user.id)


@router.get("/dashboard")
def dashboard_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return get_dashboard_analytics(db, current_user.id)


@router.get("/sales")
def sales_analytics(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    granularity: str = Query(default="monthly", pattern="^(daily|weekly|monthly)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return get_sales_analytics(
        db=db,
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        category=category,
        granularity=granularity,
    )
