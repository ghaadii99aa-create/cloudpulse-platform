from __future__ import annotations

from collections.abc import Callable, Iterator

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import Settings
from .models import ROLES, User
from .security import decode_access_token
from .services.dataset import Dataset

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    yield from request.app.state.database.session()


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, message, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db),
                     settings: Settings = Depends(get_settings)) -> User:
    if not token:
        raise _unauthorized("Not authenticated")
    try:
        claims = decode_access_token(token, settings.jwt_secret)
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise _unauthorized("Invalid or expired token") from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("User is inactive or no longer exists")
    return user


def require_role(minimum: str) -> Callable[[User], User]:
    """Roles are ordered viewer < engineer < admin; a higher role inherits lower permissions."""
    rank = ROLES.index(minimum)

    def checker(user: User = Depends(get_current_user)) -> User:
        if ROLES.index(user.role) < rank:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires {minimum} role or higher")
        return user

    return checker


def get_dataset(request: Request, db: Session = Depends(get_db)) -> Dataset:
    try:
        return request.app.state.store.get(db)
    except LookupError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
