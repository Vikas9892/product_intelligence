"""`ExplanationService`: the facade the explanation API depends on (Phase 16).

Assembles `ExplanationTrace`s from structured decision inputs, composing
`ExplanationBuilder` for the presentation work. Kept as the single seam
routes depend on (rather than each route composing explainers directly),
matching every other `*Service` facade in this codebase. Accepts an
optional `MetricsRegistry` (per this project's observability convention);
the actual explanation metrics — latency, count, average confidence,
decision-type distribution — are wired in Milestone 5, so this milestone
only stores the registry.

Holds no mutable per-request state, so one instance is safe to share
across concurrent requests — the same reasoning every other stateless
service here documents.
"""

from collections.abc import Sequence

from app.core.logging import get_logger
from app.metrics.metrics_registry import MetricsRegistry
from app.models.confidence_breakdown import ConfidenceBreakdown
from app.models.decision_reason import DecisionReason
from app.models.explanation_trace import ExplanationTrace
from app.services.explanations.explanation_builder import ExplanationBuilder

logger = get_logger(__name__)


class ExplanationService:
    """Builds explanation traces from structured decision inputs."""

    def __init__(
        self,
        *,
        builder: ExplanationBuilder | None = None,
        metrics_registry: MetricsRegistry | None = None,
    ) -> None:
        self._builder = builder if builder is not None else ExplanationBuilder()
        self._metrics = metrics_registry if metrics_registry is not None else MetricsRegistry()

    def build_trace(
        self,
        *,
        decision_type: str,
        lead_in: str,
        reasons: Sequence[DecisionReason],
        subject_id: str | None = None,
        breakdown: ConfidenceBreakdown | None = None,
        confidence: float | None = None,
    ) -> ExplanationTrace:
        """Assemble an `ExplanationTrace` from already-decided inputs.

        `lead_in` seeds the natural-language summary (e.g. "Products
        match because"); `reasons`' descriptions are joined onto it by
        `ExplanationBuilder`. Never recomputes the decision — it only
        phrases and structures what the caller already decided.
        """
        summary = self._builder.summarize(lead_in, reasons)
        trace = ExplanationTrace(
            decision_type=decision_type,
            summary=summary,
            subject_id=subject_id,
            reasons=list(reasons),
            breakdown=breakdown,
            confidence=confidence,
        )
        logger.info(
            "Explanation built: decision_type=%s, subject_id=%s, reasons=%d",
            decision_type,
            subject_id,
            len(trace.reasons),
        )
        return trace
