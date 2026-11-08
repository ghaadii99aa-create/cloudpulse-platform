"""Password hashing (PBKDF2-SHA256, stdlib) and JWT access tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

import jwt

PBKDF2_ITERATIONS = 600_000
_ALGORITHM = "HS256"


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt, digest = encoded.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(candidate, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, role: str, secret: str, minutes: int) -> tuple[str, int]:
    now = datetime.now(UTC)
    claims = {"sub": str(user_id), "role": role, "iat": now, "exp": now + timedelta(minutes=minutes), "type": "access"}
    return jwt.encode(claims, secret, algorithm=_ALGORITHM), minutes * 60


def decode_access_token(token: str, secret: str) -> dict:
    """Raises jwt.PyJWTError on any invalid, expired or tampered token."""
    claims = jwt.decode(token, secret, algorithms=[_ALGORITHM], options={"require": ["exp", "sub"]})
    if claims.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return claims


class SlidingWindowLimiter:
    """In-process limiter. Enough for a single-instance demo; use Redis when scaling out."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit, self.window = limit, window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def _trim(self, key: str, now: float) -> deque[float]:
        events = self._events[key]
        while events and now - events[0] > self.window:
            events.popleft()
        return events

    def blocked(self, key: str) -> bool:
        return len(self._trim(key, time.monotonic())) >= self.limit

    def hit(self, key: str) -> None:
        now = time.monotonic()
        self._trim(key, now).append(now)

    def reset(self, key: str) -> None:
        self._events.pop(key, None)
