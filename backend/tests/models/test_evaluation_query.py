"""Unit tests for `EvaluationQuery`/`GroundTruth`/`EvaluationTaskType`."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.evaluation_query import EvaluationQuery, EvaluationTaskType, GroundTruth


class TestEvaluationTaskType:
    def test_has_the_three_expected_members(self) -> None:
        assert {member.value for member in EvaluationTaskType} == {
            "retrieval",
            "recommendation",
            "duplicate",
        }


class TestGroundTruth:
    def test_defaults(self) -> None:
        ground_truth = GroundTruth()

        assert ground_truth.expected_products == []
        assert ground_truth.is_duplicate is None

    def test_constructs_with_all_fields(self) -> None:
        product_id = uuid4()

        ground_truth = GroundTruth(expected_products=[product_id], is_duplicate=True)

        assert ground_truth.expected_products == [product_id]
        assert ground_truth.is_duplicate is True


class TestEvaluationQuery:
    def test_a_retrieval_query_accepts_text(self) -> None:
        query = EvaluationQuery(
            query_id="q1",
            task_type=EvaluationTaskType.RETRIEVAL,
            text="red running shoes",
            ground_truth=GroundTruth(expected_products=[uuid4()]),
        )

        assert query.text == "red running shoes"

    def test_task_type_defaults_to_retrieval(self) -> None:
        query = EvaluationQuery(query_id="q1", text="red shoes", ground_truth=GroundTruth())

        assert query.task_type is EvaluationTaskType.RETRIEVAL

    def test_a_retrieval_query_without_text_or_image_path_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="needs 'text' and/or 'image_path'"):
            EvaluationQuery(query_id="q1", ground_truth=GroundTruth())

    def test_a_retrieval_query_with_only_whitespace_text_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="needs 'text' and/or 'image_path'"):
            EvaluationQuery(query_id="q1", text="   ", ground_truth=GroundTruth())

    def test_a_recommendation_query_requires_a_product_id(self) -> None:
        with pytest.raises(ValidationError, match="needs 'product_id'"):
            EvaluationQuery(
                query_id="q1",
                task_type=EvaluationTaskType.RECOMMENDATION,
                ground_truth=GroundTruth(),
            )

    def test_a_recommendation_query_with_a_product_id_is_valid(self) -> None:
        query = EvaluationQuery(
            query_id="q1",
            task_type=EvaluationTaskType.RECOMMENDATION,
            product_id=uuid4(),
            ground_truth=GroundTruth(expected_products=[uuid4()]),
        )

        assert query.product_id is not None

    def test_a_duplicate_query_requires_a_product_id(self) -> None:
        with pytest.raises(ValidationError, match="needs 'product_id'"):
            EvaluationQuery(
                query_id="q1", task_type=EvaluationTaskType.DUPLICATE, ground_truth=GroundTruth()
            )

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        query = EvaluationQuery(
            query_id="q1",
            task_type=EvaluationTaskType.RECOMMENDATION,
            product_id=uuid4(),
            ground_truth=GroundTruth(expected_products=[uuid4()]),
            top_k=5,
        )

        dumped = query.model_dump(mode="json")
        restored = EvaluationQuery.model_validate(dumped)

        assert restored == query

    def test_rejects_a_non_positive_top_k(self) -> None:
        with pytest.raises(ValidationError):
            EvaluationQuery(query_id="q1", text="shoes", ground_truth=GroundTruth(), top_k=0)
