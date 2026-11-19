from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.logger import logger
from backend.models import User
from backend.schemas import (
    PasswordChangeRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from backend.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
alias_router = APIRouter(prefix="/auth", tags=["Authentication (Alias)"])


def _register_user(payload: UserRegisterRequest, db: Session) -> TokenResponse:
    email_norm = payload.email.strip().lower()
    full_name_clean = payload.full_name.strip()
    if not full_name_clean:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Full name cannot be blank.",
        )

    existing = db.query(User).filter(User.email == email_norm).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        full_name=full_name_clean,
        email=email_norm,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    logger.info("Registered new analyst account: %s", email_norm)
    token = create_access_token(user.id, user.email)
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            created_at=user.created_at,
        ),
    )


def _login_user(payload: UserLoginRequest, db: Session) -> TokenResponse:
    email_norm = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email_norm).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )
    token = create_access_token(user.id, user.email)
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            created_at=user.created_at,
        ),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@alias_router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return _register_user(payload, db)


@router.post("/login", response_model=TokenResponse)
@alias_router.post("/login", response_model=TokenResponse)
def login(payload: UserLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return _login_user(payload, db)


@router.get("/me", response_model=UserResponse)
@alias_router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        full_name=current_user.full_name,
        email=current_user.email,
        created_at=current_user.created_at,
    )


@router.put("/password")
@alias_router.put("/password")
def update_password(
    payload: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password updated successfully."}
