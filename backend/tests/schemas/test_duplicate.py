"""Unit tests for the duplicate-check schemas."""

from uuid import uuid4

from app.schemas.duplicate import (
    DuplicateCandidateInfo,
    DuplicateCheckResponse,
    DuplicateSignalBreakdown,
)


class TestDuplicateCandidateInfo:
    def test_constructs_with_all_fields(self) -> None:
        product_id = uuid4()

        info = DuplicateCandidateInfo(
            product_id=product_id,
            image_similarity=0.9,
            text_similarity=0.8,
            metadata_similarity=0.7,
            attribute_similarity=0.6,
            overall_similarity=0.8,
        )

        assert info.product_id == product_id
        assert info.overall_similarity == 0.8


class TestDuplicateSignalBreakdown:
    def test_constructs_with_all_fields(self) -> None:
        breakdown = DuplicateSignalBreakdown(image=0.9, text=0.8, metadata=0.7, attribute=0.6)

        assert breakdown.image == 0.9
        assert breakdown.text == 0.8
        assert breakdown.metadata == 0.7
        assert breakdown.attribute == 0.6


class TestDuplicateCheckResponse:
    def test_round_trips_through_model_dump_and_validate(self) -> None:
        matched_product = uuid4()
        response = DuplicateCheckResponse(
            duplicate=True,
            confidence=0.95,
            reason="Overall similarity 0.95 meets the threshold.",
            matched_product=matched_product,
            signals=DuplicateSignalBreakdown(image=0.9, text=0.8, metadata=0.7, attribute=0.6),
            top_candidates=[
                DuplicateCandidateInfo(
                    product_id=matched_product,
                    image_similarity=0.9,
                    text_similarity=0.8,
                    metadata_similarity=0.7,
                    attribute_similarity=0.6,
                    overall_similarity=0.95,
                )
            ],
        )

        dumped = response.model_dump(mode="json")
        restored = DuplicateCheckResponse.model_validate(dumped)

        assert restored == response

    def test_matched_product_and_signals_default_to_none(self) -> None:
        response = DuplicateCheckResponse(
            duplicate=False, confidence=0.0, reason="No candidates were found."
        )

        assert response.matched_product is None
        assert response.signals is None
        assert response.top_candidates == []
