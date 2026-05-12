from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})


class DecimalModel(ApiModel):
    @field_serializer("*", when_used="json")
    def _serialize_decimal(self, value: Any):
        if isinstance(value, Decimal):
            return str(value)
        return value


class HealthResponse(ApiModel):
    status: str


class VersionResponse(ApiModel):
    app: str
    api_version: str


class ErrorResponse(ApiModel):
    detail: str


class TimestampedResponse(ApiModel):
    generated_at: datetime
