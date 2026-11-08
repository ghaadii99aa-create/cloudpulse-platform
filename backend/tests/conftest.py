from __future__ import annotations

import os

import pandas as pd
import pytest

from app.config import Settings
from app.services.dataset import Dataset
from cloudpulse_analytics import SimulationConfig, generate_billing, generate_metrics, generate_resources

# Fixed clock so every test sees the same data. 14:00 sits near the daily load peak of the simulation.
SIM_END = "2026-11-08 14:00"
ADMIN = ("admin@cloudpulse.test", "admin-Passw0rd-for-tests")


def make_settings(**overrides) -> Settings:
    base = dict(environment="test", database_url=os.getenv("TEST_DATABASE_URL", "sqlite://"), jwt_secret="t" * 48,
                jwt_expire_minutes=30, cors_origins=("http://localhost:5173",), admin_email=ADMIN[0], admin_password=ADMIN[1],
                seed_on_startup=True, simulation_end=SIM_END)
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return make_settings()


@pytest.fixture(scope="session")
def dataset() -> Dataset:
    end = pd.Timestamp(SIM_END)
    resources = generate_resources()
    resources["provider"], resources["region"] = "simulated", "sim-region-1"
    billing = generate_billing(SimulationConfig(end=str(end.normalize() - pd.Timedelta(days=1))))
    metrics = generate_metrics(SimulationConfig(end=SIM_END))
    return Dataset.from_frames(resources, billing, metrics, version=("test",))
