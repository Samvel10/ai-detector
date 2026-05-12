from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventContract(BaseModel):
    """
    Minimal global event contract specification.

    This is a schema-only interface for cross-module consistency.
    It does not implement event processing or temporal logic.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1)
    job_id: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    timestamp_sec: float = Field(..., ge=0)
    confidence: float = Field(..., ge=0, le=1)
    source: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
