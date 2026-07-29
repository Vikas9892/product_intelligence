"""Unit tests for `ExplanationBuilder`."""

from app.models.decision_reason import DecisionReason
from app.models.decision_weight import DecisionWeight
from app.services.explanations.explanation_builder import ExplanationBuilder


class TestWeight:
    def test_computes_contribution(self) -> None:
        builder = ExplanationBuilder()

        weight = builder.weight("embedding", 0.9, 0.7)

        assert weight.contribution == 0.9 * 0.7


class TestBreakdown:
    def test_groups_components_with_a_total(self) -> None:
        builder = ExplanationBuilder()
        components = [DecisionWeight(name="a", value=1.0, weight=0.5, contribution=0.5)]

        breakdown = builder.breakdown(components, total=0.5)

        assert breakdown.total == 0.5
        assert breakdown.components == components


class TestSummarize:
    def test_single_reason(self) -> None:
        builder = ExplanationBuilder()
        reasons = [DecisionReason(code="a", description="same brand")]

        assert builder.summarize("Products match", reasons) == "Products match: same brand."

    def test_two_reasons_join_with_and(self) -> None:
        builder = ExplanationBuilder()
        reasons = [
            DecisionReason(code="a", description="same brand"),
            DecisionReason(code="b", description="same category"),
        ]

        summary = builder.summarize("Products match", reasons)

        assert summary == "Products match: same brand and same category."

    def test_three_reasons_use_an_oxford_comma(self) -> None:
        builder = ExplanationBuilder()
        reasons = [
            DecisionReason(code="a", description="same brand"),
            DecisionReason(code="b", description="same category"),
            DecisionReason(code="c", description="94% title similarity"),
        ]

        summary = builder.summarize("Products match", reasons)

        assert summary == ("Products match: same brand, same category, and 94% title similarity.")

    def test_no_reasons_returns_the_lead_in_alone(self) -> None:
        builder = ExplanationBuilder()

        assert builder.summarize("No match found", []) == "No match found."

    def test_strips_a_trailing_colon_from_the_lead_in(self) -> None:
        builder = ExplanationBuilder()
        reasons = [DecisionReason(code="a", description="same brand")]

        assert builder.summarize("Match because:", reasons) == "Match because: same brand."
