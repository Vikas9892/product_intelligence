"""Internal domain model: `RecommendationResult`, the final output of one recommendation request.

Built exclusively by `RecommendationEngineService` (`app/services/
recommendation/recommendation_engine_service.py`) — see that module's own
docstring for the full pipeline (retrieve candidates, remove the target
itself, score, rank, diversify, explain).
"""

from pydantic import BaseModel, Field

from app.models.recommendation_candidate import RecommendationCandidate
from app.models.recommendation_type import RecommendationType


class RecommendationResult(BaseModel):
    """A ranked list of recommendations for one target product, plus how they were produced."""

    recommendations: list[RecommendationCandidate] = Field(default_factory=list)
    processing_time: float = Field(ge=0)
    recommendation_type: RecommendationType
