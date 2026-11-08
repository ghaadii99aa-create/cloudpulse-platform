from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import get_current_user, get_db, get_settings, require_role
from ..models import User
from ..schemas import LoginRequest, TokenResponse, UserCreate, UserOut, UserUpdate
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(tags=["auth"])

# A valid hash to compare against when the user does not exist, so response time does not reveal which emails exist.
_DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password", iterations=600_000)


def _authenticate(request: Request, db: Session, settings: Settings, email: str, password: str) -> TokenResponse:
    limiter = request.app.state.login_limiter
    key = email.strip().lower()
    if limiter.blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again in a few minutes.")
    user = db.scalar(select(User).where(User.email == key))
    valid = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if not user or not valid or not user.is_active:
        limiter.hit(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    limiter.reset(key)
    token, expires = create_access_token(user.id, user.role, settings.jwt_secret, settings.jwt_expire_minutes)
    return TokenResponse(access_token=token, expires_in=expires, user=UserOut.model_validate(user))


@router.post("/auth/login", response_model=TokenResponse, summary="Log in with email and password (JSON)")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return _authenticate(request, db, settings, body.email, body.password)


@router.post("/auth/token", response_model=TokenResponse, summary="OAuth2 password flow (used by the Swagger Authorize button)")
def token(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db),
          settings: Settings = Depends(get_settings)):
    return _authenticate(request, db, settings, form.username, form.password)


@router.get("/auth/me", response_model=UserOut, summary="The authenticated user")
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list[UserOut], summary="List users (admin)")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_role("admin"))):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Create a user (admin)")
def create_user(body: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_role("admin"))):
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    user = User(email=body.email.lower(), full_name=body.full_name, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut, summary="Change a user's name, role or active flag (admin)")
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(require_role("admin"))):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin.id and (body.role not in (None, "admin") or body.is_active is False):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admins cannot demote or deactivate themselves")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user
