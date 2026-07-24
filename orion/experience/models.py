"""Pydantic models for the Experience Engine: ExperienceReport and the
Knowledge Store's KnowledgeItem.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeItemType(str, Enum):
    """The only six kinds of reusable knowledge the Knowledge Store
    holds -- exactly the taxonomy this Sprint specifies, nothing more
    invented on top of it."""

    PATTERN = "PATTERN"
    DECISION = "DECISION"
    LESSON = "LESSON"
    RISK = "RISK"
    OPPORTUNITY = "OPPORTUNITY"
    BEST_PRACTICE = "BEST_PRACTICE"


class KnowledgeItem(BaseModel):
    """One reusable piece of knowledge, always traceable to the mission
    that produced it -- the Knowledge Store never holds an item with no
    source."""

    id: str
    type: KnowledgeItemType
    title: str
    description: str
    source_mission_id: str
    project_id: str = ""
    tags: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    created_at: str


class ExperienceReport(BaseModel):
    """What one mission taught ORION, structured so a future question
    like "what did we learn" or "what can we reuse" never requires
    re-reading the mission's full execution history -- this report is
    the answer, already computed.
    """

    mission_id: str
    project_id: str = ""
    mission_summary: str
    objectives_achieved: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    artifacts_generated: list[str] = Field(default_factory=list)
    execution_metrics: dict[str, Any] = Field(default_factory=dict)
    errors_encountered: list[str] = Field(default_factory=list)
    fixes_applied: list[str] = Field(default_factory=list)
    patterns_detected: list[str] = Field(default_factory=list)
    reusable_components: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    knowledge_item_ids: list[str] = Field(default_factory=list)
    confidence_score: float
    generated_at: str
