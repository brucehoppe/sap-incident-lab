from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


class Settings(BaseSettings):
    """Typed, validated configuration. See DESIGN.md section 6 for the contract.

    Missing root/output must not crash startup (health still has to report why);
    validation therefore happens lazily via `validate_for_evidence_access()`
    rather than as a required field, and the `_config_error` property records
    the first problem found so `health` can surface it without re-deriving it.
    """

    model_config = SettingsConfigDict(
        env_prefix="INCIDENT_LAB_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "sap-incident-lab"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    root: Path | None = None
    output: Path | None = None

    model: str = Field(default="qwen3:8b", min_length=1)
    ollama_url: str = "http://127.0.0.1:11434"

    num_ctx: int = Field(default=8192, ge=2048, le=32768)
    num_predict: int = Field(default=1200, ge=100, le=4096)

    max_chunk_lines: int = Field(default=120, ge=1)
    max_chunk_chars: int = Field(default=8000, ge=1)
    chunk_overlap_lines: int = Field(default=15, ge=0)

    max_file_mb: int = Field(default=20, ge=1)
    max_chunks_per_job: int = Field(default=20, ge=1)

    evidence_max_lines: int = Field(default=120, ge=1)
    evidence_max_chars: int = Field(default=16000, ge=1)

    timeout_seconds: int = Field(default=180, ge=1)

    @field_validator("ollama_url")
    @classmethod
    def _require_loopback(cls, value: str) -> str:
        from urllib.parse import urlparse

        host = urlparse(value).hostname
        if host not in _LOOPBACK_HOSTS:
            raise ValueError(
                f"INCIDENT_LAB_OLLAMA_URL host {host!r} is not loopback; "
                "this server refuses non-local Ollama endpoints (see DESIGN.md section 6)"
            )
        return value

    @model_validator(mode="after")
    def _overlap_less_than_lines(self) -> Settings:
        if self.chunk_overlap_lines >= self.max_chunk_lines:
            raise ValueError("chunk_overlap_lines must be smaller than max_chunk_lines")
        return self

    def evidence_config_error(self) -> str | None:
        """Return why the evidence root/output aren't usable yet, or None if they are.

        Used by the health tool and by tools that touch the filesystem — never
        raised at import/construction time, so tool discovery works even with
        no configuration at all.
        """
        if self.root is None:
            return "INCIDENT_LAB_ROOT is not set"
        if self.output is None:
            return "INCIDENT_LAB_OUTPUT is not set"
        if not self.root.is_absolute():
            return f"INCIDENT_LAB_ROOT must be absolute, got {self.root}"
        if not self.output.is_absolute():
            return f"INCIDENT_LAB_OUTPUT must be absolute, got {self.output}"
        if not self.root.is_dir():
            return "INCIDENT_LAB_ROOT does not exist or is not a directory"
        root_r = self.root.resolve()
        output_r = self.output.resolve() if self.output.exists() else self.output
        if root_r == output_r or root_r in output_r.parents or output_r in root_r.parents:
            return "INCIDENT_LAB_ROOT and INCIDENT_LAB_OUTPUT must not contain each other"
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
