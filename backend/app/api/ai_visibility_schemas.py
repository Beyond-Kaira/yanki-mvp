"""Standalone AI visibility (GEO) module runs — mod-4."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AiVisibilityMode = Literal["measured", "simulated"]


class AiVisibilityPromptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    category: str = Field(default="general", max_length=120)


class CreateAiVisibilityRunRequest(BaseModel):
    """Enqueue a GEO execute + scoring run for an existing brand context."""

    model_config = ConfigDict(extra="forbid")

    brand_context_id: uuid.UUID
    prompts: list[AiVisibilityPromptIn] = Field(min_length=1, max_length=50)
    mode: AiVisibilityMode = "measured"

    @model_validator(mode="after")
    def _validate_prompts_non_empty(self) -> CreateAiVisibilityRunRequest:
        if not self.prompts:
            raise ValueError("at least one prompt is required")
        return self
