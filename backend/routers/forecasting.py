from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User
from backend.schemas import ForecastRunRequest
from backend.security import get_current_user
from backend.services.forecast_service import list_forecastable_products, run_demand_forecast

router = APIRouter(prefix="/api/forecasting", tags=["Demand Forecasting"])


@router.get("/products")
def forecast_products(
    granularity: str = Query(default="weekly", pattern="^(weekly|monthly)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return {"products": list_forecastable_products(db, current_user.id, granularity=granularity)}


@router.post("/run")
def forecast_run(
    payload: ForecastRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return run_demand_forecast(
        db=db,
        user_id=current_user.id,
        product_id=payload.product_id,
        granularity=payload.granularity,
        horizon=payload.horizon,
    )
