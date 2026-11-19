from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db
from backend.logger import logger
from backend.models import Dataset, UploadedFile as UploadedFileModel, User
from backend.schemas import DatasetImportRequest
from backend.security import get_current_user
from backend.services.csv_processor import (
    compute_sha256,
    profile_dataframe,
    read_csv_bytes,
)
from backend.services.ingestion_service import ingest_dataframe_to_db, purge_dataset_records

router = APIRouter(prefix="/api/datasets", tags=["Datasets & CSV Ingestion"])
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@router.get("")
def list_datasets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    datasets = (
        db.query(Dataset)
        .filter(Dataset.user_id == current_user.id)
        .order_by(Dataset.created_at.desc())
        .all()
    )
    out = []
    for d in datasets:
        uf = d.uploaded_file
        out.append(
            {
                "id": d.id,
                "name": d.name,
                "original_filename": uf.original_filename if uf else "",
                "dataset_type": d.dataset_type,
                "detected_type": d.detected_type,
                "import_status": d.import_status,
                "row_count": d.row_count,
                "column_count": d.column_count,
                "rows_parsed": d.rows_parsed,
                "rows_imported": d.rows_imported,
                "rows_skipped": d.rows_skipped,
                "duplicates_removed": d.duplicates_removed,
                "error_message": d.error_message,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
        )
    return out


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_csv(
    file: UploadFile = File(...),
    name: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .csv files are supported.",
        )

    raw_bytes = await file.read()
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="CSV file exceeds the 50 MB limit.",
        )

    file_hash = compute_sha256(raw_bytes)

    # Prevent duplicate uploads of the exact same file
    existing_file = (
        db.query(UploadedFileModel)
        .join(Dataset, Dataset.uploaded_file_id == UploadedFileModel.id)
        .filter(
            UploadedFileModel.user_id == current_user.id,
            UploadedFileModel.file_hash == file_hash,
        )
        .first()
    )
    if existing_file and existing_file.dataset:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate CSV detected: '{existing_file.original_filename}' (Dataset '{existing_file.dataset.name}') has the exact same SHA-256 hash. Use Re-Import in Data Management instead.",
        )

    try:
        df = read_csv_bytes(raw_bytes)
        profile = profile_dataframe(df, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Preserve original CSV locally
    settings = get_settings()
    safe_name = Path(file.filename).name.replace(" ", "_")
    stored_filename = f"{uuid.uuid4().hex}_{safe_name}"
    stored_path = settings.upload_dir / stored_filename
    stored_path.write_bytes(raw_bytes)

    uf_record = UploadedFileModel(
        user_id=current_user.id,
        original_filename=file.filename,
        stored_path=str(stored_path),
        file_hash=file_hash,
        file_size=len(raw_bytes),
        mime_type=file.content_type or "text/csv",
    )
    db.add(uf_record)
    db.flush()

    dataset_label = (name or Path(file.filename).stem).strip()[:250]
    dataset = Dataset(
        user_id=current_user.id,
        uploaded_file_id=uf_record.id,
        name=dataset_label,
        dataset_type=profile["detected_type"],
        detected_type=profile["detected_type"],
        classification_confidence=profile["classification_confidence"],
        import_status="profiled",
        row_count=profile["row_count"],
        column_count=profile["column_count"],
        columns_profile=profile["columns"],
        column_mapping=profile["suggested_mapping"],
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    logger.info("Uploaded and profiled CSV '%s' as dataset_id=%s", file.filename, dataset.id)
    return {
        "dataset_id": dataset.id,
        "filename": file.filename,
        "dataset_type": dataset.dataset_type,
        **profile,
    }


@router.get("/{dataset_id}")
def get_dataset_detail(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.user_id == current_user.id)
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    uf = dataset.uploaded_file
    return {
        "id": dataset.id,
        "name": dataset.name,
        "original_filename": uf.original_filename if uf else "",
        "stored_path": uf.stored_path if uf else "",
        "file_hash": uf.file_hash if uf else "",
        "dataset_type": dataset.dataset_type,
        "detected_type": dataset.detected_type,
        "import_status": dataset.import_status,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "columns": dataset.columns_profile or [],
        "column_mapping": dataset.column_mapping or {},
        "cleaning_options": dataset.cleaning_options or {},
        "error_message": dataset.error_message,
    }


@router.get("/{dataset_id}/preview")
def preview_dataset_for_mapping(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.user_id == current_user.id)
        .first()
    )
    if not dataset or not dataset.uploaded_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset or preserved file not found.")

    file_path = Path(dataset.uploaded_file.stored_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preserved local CSV file is missing from storage.",
        )

    raw_bytes = file_path.read_bytes()
    df = read_csv_bytes(raw_bytes)
    profile = profile_dataframe(df, dataset.uploaded_file.original_filename)
    return {
        "dataset_id": dataset.id,
        "filename": dataset.uploaded_file.original_filename,
        "dataset_type": dataset.dataset_type,
        **profile,
        "suggested_mapping": dataset.column_mapping or profile["suggested_mapping"],
    }


@router.post("/{dataset_id}/import")
def import_dataset(
    dataset_id: int,
    payload: DatasetImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.user_id == current_user.id)
        .first()
    )
    if not dataset or not dataset.uploaded_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    file_path = Path(dataset.uploaded_file.stored_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preserved local CSV file could not be located on disk.",
        )

    try:
        raw_df = read_csv_bytes(file_path.read_bytes())
        result = ingest_dataframe_to_db(
            db=db,
            dataset=dataset,
            raw_df=raw_df,
            dataset_type=payload.dataset_type,
            column_mapping=payload.column_mapping,
            cleaning=payload.cleaning_options,
        )
        logger.info(
            "Imported dataset_id=%s type=%s rows=%s",
            dataset.id,
            payload.dataset_type,
            result["rows_imported"],
        )
        return result
    except ValueError as exc:
        dataset.import_status = "failed"
        dataset.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        db.rollback()
        logger.exception("Dataset import error for dataset_id=%s", dataset_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database import failed: {exc}",
        )


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.user_id == current_user.id)
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    uf = dataset.uploaded_file
    stored_path = Path(uf.stored_path) if uf else None

    purge_dataset_records(db, current_user.id, dataset.id)
    db.delete(dataset)
    if uf:
        db.delete(uf)
    db.commit()

    if stored_path and stored_path.exists():
        try:
            stored_path.unlink()
        except OSError as exc:
            logger.warning("Could not delete local CSV %s: %s", stored_path, exc)

    return {"message": "Dataset and associated records deleted.", "dataset_id": dataset_id}
