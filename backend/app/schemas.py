from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["viewer", "engineer", "admin"]
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, examples=["engineer@example.com"])
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: str = Field(max_length=255, pattern=EMAIL_PATTERN)
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=256, description="At least 12 characters, with letters and digits")
    role: Role = "viewer"

    @field_validator("password")
    @classmethod
    def strong_enough(cls, value: str) -> str:
        if not (any(c.isalpha() for c in value) and any(c.isdigit() for c in value)):
            raise ValueError("password must contain letters and digits")
        return value


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    is_active: bool | None = None


class AlertOut(BaseModel):
    id: int
    fingerprint: str
    category: str
    severity: Literal["info", "warning", "critical"]
    status: Literal["open", "acknowledged", "resolved"]
    resource: str | None
    title: str
    message: str
    value: float | None
    threshold: float | None
    observed_at: datetime
    first_seen: datetime
    last_seen: datetime
    acknowledged_by: str | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    data_source: str


class AlertPage(BaseModel):
    total: int
    items: list[AlertOut]


class AdvisorRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000, examples=["Where can we cut cloud spend this month?"])


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


TokenResponse.model_rebuild()
