"""
BlastShield Configuration — pydantic-settings based.

All settings are read from environment variables or .env file.
Fails fast at startup if required values (GROQ_API_KEY) are missing.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application-wide settings sourced from environment variables."""

    # ── Required ──
    groq_api_key: str = Field(..., description="Groq API key for LLM gateway")

    # ── LLM ──
    blastshield_model: str = Field(
        default="moonshotai/kimi-k2-instruct-0905",
        description="Model identifier for Groq completions",
    )
    llm_timeout: int = Field(default=30, description="LLM request timeout in seconds")
    llm_max_retries: int = Field(default=3, description="Max LLM retry attempts")
    llm_temperature: float = Field(default=0.1, description="LLM temperature")
    llm_max_tokens_per_scan: int = Field(
        default=4096, description="Token budget cap per scan"
    )

    # ── Risk Thresholds ──
    llm_risk_threshold: int = Field(
        default=30,
        description="Minimum risk score to invoke LLM (0-100). Below this, deterministic-only.",
    )

    # ── Scanning ──
    max_file_size_bytes: int = Field(
        default=500_000, description="Max file size to accept (bytes)"
    )
    background_file_threshold: int = Field(
        default=10,
        description="Files above this count trigger background worker instead of inline scan",
    )
    test_harness_enabled: bool = Field(
        default=False,
        description="Feature flag: enable edge-case test harness (runs generated code in subprocess)",
    )
    test_harness_timeout: int = Field(
        default=5, description="Timeout per generated test case in seconds"
    )

    # ── Cache ──
    cache_ttl_seconds: int = Field(
        default=3600, description="Time-to-live for file-level cache entries"
    )

    # ── Server ──
    port: int = Field(default=5001, description="Server port")
    host: str = Field(default="0.0.0.0", description="Server bind host")
    cors_origins: list[str] = Field(
        default=["*"], description="Allowed CORS origins"
    )

    # ── Audit ──
    audit_log_path: str = Field(
        default="audit.jsonl", description="Path to JSON-lines audit log file"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Singleton instance — imported by other modules
settings = Settings()
