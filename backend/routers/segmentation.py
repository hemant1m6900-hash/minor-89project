from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User
from backend.schemas import RFMRunRequest
from backend.security import get_current_user
from backend.services.rfm_service import compute_rfm_segmentation

router = APIRouter(prefix="/api/segmentation", tags=["RFM Segmentation"])


@router.get("/rfm")
def get_rfm(
    n_clusters: int = Query(default=5, ge=2, le=8),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return compute_rfm_segmentation(db, current_user.id, requested_clusters=n_clusters)


@router.post("/rfm")
def run_rfm(
    payload: RFMRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return compute_rfm_segmentation(db, current_user.id, requested_clusters=payload.n_clusters)
