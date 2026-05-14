from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChangeEvent(BaseModel):
    """OpenMetadata webhook ChangeEvent payload."""

    id: Optional[str] = None
    eventType: str  # EntityCreated | EntityUpdated | EntityDeleted | EntitySoftDeleted
    entityType: str  # table | database | databaseSchema | databaseService | tag | glossaryTerm | …
    entityId: Optional[str] = None
    entityFullyQualifiedName: Optional[str] = None
    userName: Optional[str] = None
    timestamp: Optional[int] = None
    changeDescription: Optional[Dict[str, Any]] = None
    currentVersion: Optional[float] = None
    entity: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"  # tolerate unknown fields added in future OMD versions


class SiteEvent(BaseModel):
    """Envelope that wraps a ChangeEvent with originating site metadata."""

    site_code: str
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event: ChangeEvent
