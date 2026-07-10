"""
Marrow — Centralized Configuration

Loads environment variables from .env file.
All config values flow through this module — nothing reads os.environ directly.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Locate project root (one level up from app/) ──────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Load .env if it exists ────────────────────────────────────────────────
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


class Config:
    """Single source of truth for all configuration."""

    # ── Fireworks AI ──────────────────────────────────────────────────────
    # Credentials and endpoint for the Fireworks inference API.
    # When a valid key is present, the reasoner routes queries to
    # DeepSeek V4 running on AMD Instinct MI300X accelerators.
    # If the key is missing or placeholder, the system gracefully
    # falls back to the deterministic rule-based reasoner.
    FIREWORKS_API_KEY: str = os.getenv("FIREWORKS_API_KEY", "")
    FIREWORKS_BASE_URL: str = os.getenv(
        "FIREWORKS_BASE_URL",
        "https://api.fireworks.ai/inference/v1"
    )
    FIREWORKS_MODEL: str = os.getenv(
        "FIREWORKS_MODEL",
        "accounts/fireworks/models/llama-v3p1-70b-instruct",
    )



    # ── Flask ─────────────────────────────────────────────────────────────
    # Secret key for session signing and CSRF protection.
    # Auto-generates a random key if none is provided in .env.
    FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())
    FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # ── Database ──────────────────────────────────────────────────────────
    DB_PATH: str = os.getenv("DATABASE_URL", str(PROJECT_ROOT / "marrow.db"))

    # ── Data paths ────────────────────────────────────────────────────────
    # Paths to the AWS Cost Explorer and Security Hub JSON exports.
    # In production, these would point to live API responses;
    # for the hackathon demo, they reference bundled sample data.
    BILLING_DATA_PATH: str = os.getenv(
        "BILLING_DATA_PATH",
        str(PROJECT_ROOT / "data" / "sample_billing.json"),
    )
    FINDINGS_DATA_PATH: str = os.getenv(
        "FINDINGS_DATA_PATH",
        str(PROJECT_ROOT / "data" / "sample_findings.json"),
    )

    @classmethod
    def require_fireworks_key(cls) -> str:
        """Return the API key or raise with a clear message."""
        if not cls.FIREWORKS_API_KEY:
            raise EnvironmentError(
                "FIREWORKS_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )
        return cls.FIREWORKS_API_KEY
