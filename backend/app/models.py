from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

ROLES = ("viewer", "engineer", "admin")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    service: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(40))
    environment: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(20), default="simulated")
    region: Mapped[str] = mapped_column(String(40), default="sim-region-1")
    hourly_usd: Mapped[float] = mapped_column(Float)
    attached: Mapped[bool] = mapped_column(Boolean, default=True)
    data_source: Mapped[str] = mapped_column(String(20))

    metrics: Mapped[list[MetricSample]] = relationship(back_populates="resource", cascade="all, delete-orphan")
    costs: Mapped[list[CostRecord]] = relationship(back_populates="resource", cascade="all, delete-orphan")


class MetricSample(Base):
    __tablename__ = "metric_samples"
    __table_args__ = (UniqueConstraint("resource_id", "timestamp"), Index("ix_metric_ts", "timestamp"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    cpu_pct: Mapped[float] = mapped_column(Float)
    memory_pct: Mapped[float] = mapped_column(Float)
    disk_pct: Mapped[float] = mapped_column(Float)
    network_mbps: Mapped[float] = mapped_column(Float)
    available: Mapped[bool] = mapped_column(Boolean)
    data_source: Mapped[str] = mapped_column(String(20))

    resource: Mapped[Resource] = relationship(back_populates="metrics")


class CostRecord(Base):
    __tablename__ = "cost_records"
    __table_args__ = (UniqueConstraint("resource_id", "date"), Index("ix_cost_date", "date"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    cost_usd: Mapped[float] = mapped_column(Float)
    data_source: Mapped[str] = mapped_column(String(20))

    resource: Mapped[Resource] = relationship(back_populates="costs")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    resource: Mapped[str | None] = mapped_column(String(120), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    acknowledged_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_source: Mapped[str] = mapped_column(String(20))
