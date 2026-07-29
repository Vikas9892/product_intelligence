"""`DuplicateExplainer`: explains one duplicate-verification decision (Phase 16).

Reads a `DuplicateVerification` (Phase 15) — its cross-encoder score, raw
retrieval similarity, and the business-rule `VerificationReason`s already
attached to it — and produces a unified `ExplanationTrace`: the two score
signals as a `ConfidenceBreakdown`, and each verification reason mapped
into a `DecisionReason`. The natural-language summary is exactly the
phase's own example shape ("Products share the same brand, category, 94%
title similarity, and nearly identical embeddings"). Pure and read-only —
it maps a decision that already happened, never re-running verification.
"""

from app.models.decision_reason import DecisionReason
from app.models.decision_weight import DecisionWeight
from app.models.duplicate_verification import DuplicateVerification
from app.models.explanation_trace import ExplanationTrace
from app.services.explanations.base_explainer import BaseExplainer
from app.services.explanations.explanation_builder import ExplanationBuilder


class DuplicateExplainer(BaseExplainer[DuplicateVerification]):
    """Explains a DuplicateVerification's cross-encoder + business-rule evidence."""

    def __init__(self, *, builder: ExplanationBuilder | None = None) -> None:
        self._builder = builder if builder is not None else ExplanationBuilder()

    def explain(self, subject: DuplicateVerification) -> ExplanationTrace:
        """Explain why `subject` was (or wasn't) judged a duplicate."""
        reasons = [
            DecisionReason(code=reason.code, description=reason.message)
            for reason in subject.reasons
        ]

        components: list[DecisionWeight] = []
        if subject.cross_encoder_score is not None:
            components.append(
                self._builder.weight("cross_encoder_score", subject.cross_encoder_score, 1.0)
            )
        if subject.retrieval_similarity is not None:
            components.append(
                self._builder.weight("retrieval_similarity", subject.retrieval_similarity, 1.0)
            )
        breakdown = (
            self._builder.breakdown(components, total=subject.confidence) if components else None
        )

        lead_in = (
            "Judged a duplicate because" if subject.is_duplicate else "Not a duplicate because"
        )
        return ExplanationTrace(
            decision_type="duplicate",
            summary=self._builder.summarize(lead_in, reasons),
            subject_id=str(subject.matched_product) if subject.matched_product else None,
            reasons=reasons,
            breakdown=breakdown,
            confidence=subject.confidence,
        )
