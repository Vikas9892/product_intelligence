"""Unit tests for `DuplicateExplainer`."""

from uuid import uuid4

from app.models.duplicate_verification import DuplicateVerification
from app.models.verification_reason import VerificationReason
from app.services.explanations.duplicate_explainer import DuplicateExplainer


class TestDuplicateExplainer:
    def test_maps_verification_reasons_and_scores(self) -> None:
        matched = uuid4()
        verification = DuplicateVerification(
            is_duplicate=True,
            confidence=0.95,
            cross_encoder_score=0.98,
            retrieval_similarity=0.94,
            matched_product=matched,
            reasons=[
                VerificationReason(code="same_brand", message="the same brand"),
                VerificationReason(code="title_similarity", message="94% title similarity"),
            ],
        )

        trace = DuplicateExplainer().explain(verification)

        assert trace.decision_type == "duplicate"
        assert trace.subject_id == str(matched)
        assert trace.confidence == 0.95
        assert {r.code for r in trace.reasons} == {"same_brand", "title_similarity"}
        assert trace.summary.startswith("Judged a duplicate because")
        assert "the same brand" in trace.summary
        assert "94% title similarity" in trace.summary
        assert trace.breakdown is not None
        assert {c.name for c in trace.breakdown.components} == {
            "cross_encoder_score",
            "retrieval_similarity",
        }

    def test_not_a_duplicate_uses_the_negative_lead_in(self) -> None:
        verification = DuplicateVerification(
            is_duplicate=False,
            confidence=0.2,
            cross_encoder_score=0.3,
            reasons=[VerificationReason(code="brand_mismatch", message="a different brand")],
        )

        trace = DuplicateExplainer().explain(verification)

        assert trace.summary.startswith("Not a duplicate because")

    def test_no_scores_yields_no_breakdown(self) -> None:
        verification = DuplicateVerification(is_duplicate=False, confidence=0.0)

        trace = DuplicateExplainer().explain(verification)

        assert trace.breakdown is None
        assert trace.subject_id is None
