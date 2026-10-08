"""Application settings."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(
    os.environ.get("MELI_PROJECT_ROOT", Path(__file__).resolve().parents[3])
).resolve()

load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"

SEC_USER_AGENT: str | None = os.getenv("SEC_USER_AGENT")