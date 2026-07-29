"""Unit tests for `DuplicateVerification`."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.duplicate_candidate import DuplicateCandidate
from app.models.duplicate_verification import DuplicateVerification
from app.models.verification_reason import VerificationReason


class TestDuplicateVerification:
    def test_defaults(self) -> None:
        verification = DuplicateVerification(is_duplicate=False, confidence=0.0)

        assert verification.cross_encoder_score is None
        assert verification.retrieval_similarity is None
        assert verification.matched_product is None
        assert verification.reasons == []
        assert verification.top_candidates == []

    def test_constructs_with_all_fields(self) -> None:
        product_id = uuid4()
        verification = DuplicateVerification(
            is_duplicate=True,
            confidence=0.97,
            cross_encoder_score=0.98,
            retrieval_similarity=0.94,
            matched_product=product_id,
            reasons=[VerificationReason(code="same_brand", message="Same brand (Nike)")],
            top_candidates=[
                DuplicateCandidate(
                    product_id=product_id,
                    image_similarity=0.9,
                    text_similarity=0.9,
                    metadata_similarity=0.9,
                    attribute_similarity=0.9,
                    overall_similarity=0.9,
                )
            ],
        )

        assert verification.is_duplicate is True
        assert verification.confidence == 0.97
        assert verification.cross_encoder_score == 0.98
        assert verification.retrieval_similarity == 0.94
        assert verification.matched_product == product_id
        assert verification.reasons[0].code == "same_brand"

    def test_rejects_a_confidence_above_one(self) -> None:
        with pytest.raises(ValidationError):
            DuplicateVerification(is_duplicate=True, confidence=1.5)

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        verification = DuplicateVerification(
            is_duplicate=True,
            confidence=0.9,
            cross_encoder_score=0.95,
            reasons=[VerificationReason(code="same_category", message="Same category")],
        )

        restored = DuplicateVerification.model_validate(verification.model_dump(mode="json"))

        assert restored == verification
