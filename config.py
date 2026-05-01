"""
OmniDiag AI — Configuration Management

Loads settings from environment variables and .env files.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field

# Load .env file if present
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    with open(_env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Config:
    """Application configuration."""

    # MiMo API
    mimo_api_base: str = os.getenv("MIMO_API_BASE", "https://api.xiaomimimo.com/v1")
    mimo_api_key: str = os.getenv("MIMO_API_KEY", "")
    mimo_model: str = os.getenv("MIMO_MODEL", "mimo-v2.5-pro")
    mimo_max_tokens: int = int(os.getenv("MIMO_MAX_TOKENS", "8192"))

    # Probe settings
    probe_timeout: int = int(os.getenv("PROBE_TIMEOUT", "120"))
    probe_encoding: str = os.getenv("PROBE_ENCODING", "utf-8")

    # Output settings
    output_format: str = os.getenv("OUTPUT_FORMAT", "json+markdown")
    save_raw_probe: bool = os.getenv("SAVE_RAW_PROBE", "true").lower() == "true"

    # RAG settings
    rag_enabled: bool = os.getenv("RAG_ENABLED", "true").lower() == "true"
    rag_max_context: int = int(os.getenv("RAG_MAX_CONTEXT", "5000"))

    def validate(self) -> list[str]:
        """Validate configuration and return list of issues."""
        issues = []
        if not self.mimo_api_key:
            issues.append("MIMO_API_KEY is not set")
        if self.mimo_max_tokens < 1024:
            issues.append("MIMO_MAX_TOKENS should be at least 1024")
        return issues


# Singleton
config = Config()
