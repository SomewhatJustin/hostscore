"""Pydantic schemas for the Airbnb listing assessor backend."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import (
    AliasChoices,
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    conint,
    confloat,
)


class ImpactLevel(str, Enum):
    """Impact level for recommended fixes."""

    high = "high"
    medium = "medium"
    low = "low"


class AssessmentRequest(BaseModel):
    """Incoming payload for assessing an Airbnb listing."""

    url: AnyHttpUrl = Field(..., description="Public Airbnb listing URL.")
    force: bool = Field(
        default=False,
        description=(
            "Skip cache when true. Use sparingly to avoid unnecessary fetching."
        ),
    )


class SectionScores(BaseModel):
    """Individual section scores."""

    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    photos: conint(ge=0, le=100)
    copy_score: conint(ge=0, le=100) = Field(
        ...,
        validation_alias=AliasChoices("copy", "copy_score"),
        serialization_alias="copy",
    )
    amenities_clarity: conint(ge=0, le=100)
    trust_signals: conint(ge=0, le=100)


class PhotoStats(BaseModel):
    """Structured metadata about listing photos."""

    count: int
    coverage: List[str] = Field(default_factory=list)
    missing_coverage: List[str] = Field(default_factory=list)
    key_spaces_covered: Optional[int] = Field(default=None, ge=0)
    key_spaces_total: Optional[int] = Field(default=None, ge=0)
    has_exterior_night: bool = False
    alt_text_ratio: Optional[confloat(ge=0.0, le=1.0)] = None
    uses_legacy_gallery: bool = False
    key_space_metrics_supported: bool = True


class TrustSignals(BaseModel):
    """Signals that reinforce listing trustworthiness."""

    review_count: conint(ge=0) = 0
    review_snippets: List[str] = Field(default_factory=list)
    has_house_rules: bool = False
    house_rule_count: conint(ge=0) = 0
    has_summary: bool = False
    summary_length: conint(ge=0) = 0
    description_length: conint(ge=0) = 0


class CopyStats(BaseModel):
    """Metadata and heuristics derived from the listing copy."""

    word_count: int
    flesch: Optional[float] = None
    second_person_pct: Optional[float] = Field(
        default=None, description="Percentage of sentences using second-person voice."
    )
    has_sections: bool = False


class AmenityAudit(BaseModel):
    """Cross-reference between listed amenities and textual evidence."""

    listed: List[str] = Field(default_factory=list)
    text_hits: List[str] = Field(default_factory=list)
    likely_present_not_listed: List[str] = Field(default_factory=list)
    listed_no_text_evidence: List[str] = Field(default_factory=list)


class TopFix(BaseModel):
    """Single actionable suggestion for improving the listing."""

    impact: ImpactLevel = ImpactLevel.medium
    reason: str
    how_to_fix: str


class AssessmentResponse(BaseModel):
    """Top-level response schema returned to the frontend."""

    overall: conint(ge=0, le=100)
    section_scores: SectionScores
    photo_stats: PhotoStats
    copy_stats: CopyStats
    amenities: AmenityAudit
    trust_signals: TrustSignals
    top_fixes: List[TopFix] = Field(default_factory=list)

    model_config = {
        "json_schema_extra": {
            "example": {
                "overall": 82,
                "section_scores": {
                    "photos": 78,
                    "copy": 84,
                    "amenities_clarity": 75,
                    "trust_signals": 90,
                },
                "photo_stats": {
                    "count": 27,
                    "coverage": ["bedroom", "bath", "kitchen"],
                    "missing_coverage": ["exterior_day", "living"],
                    "key_spaces_covered": 3,
                    "key_spaces_total": 5,
                    "has_exterior_night": False,
                    "alt_text_ratio": 0.65,
                    "uses_legacy_gallery": False,
                    "key_space_metrics_supported": True,
                },
                "copy_stats": {
                    "word_count": 214,
                    "flesch": 68.3,
                    "second_person_pct": 1.4,
                    "has_sections": True,
                },
                "trust_signals": {
                    "review_count": 2,
                    "review_snippets": [
                        "Incredible stay—spotless and walkable to everything!",
                        "Host was responsive and made check-in a breeze."
                    ],
                    "has_house_rules": True,
                    "house_rule_count": 5,
                    "has_summary": True,
                    "summary_length": 140,
                    "description_length": 620,
                },
                "amenities": {
                    "listed": ["wifi", "parking", "ac"],
                    "text_hits": ["parking", "desk"],
                    "likely_present_not_listed": ["desk"],
                    "listed_no_text_evidence": ["iron"],
                },
                "top_fixes": [
                    {
                        "impact": "high",
                        "reason": "photos missing exterior night",
                        "how_to_fix": (
                            "Add 1 exterior night photo; show lit pathway and parking"
                        ),
                    }
                ],
            }
        }
    }
