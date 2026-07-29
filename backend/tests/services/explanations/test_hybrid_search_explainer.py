"""Unit tests for `HybridSearchExplainer`."""

from uuid import uuid4

from app.models.search import HybridSearchResult, SearchModality
from app.services.explanations.hybrid_search_explainer import HybridSearchExplainer


def _result(
    *, score: float = 0.90, image_score: float = 0.91, text_score: float = 0.88
) -> HybridSearchResult:
    return HybridSearchResult(
        product_id=uuid4(),
        score=score,
        metadata={},
        matched_modalities=[SearchModality.IMAGE, SearchModality.TEXT],
        image_score=image_score,
        text_score=text_score,
    )


class TestHybridSearchExplainer:
    def test_breakdown_has_image_and_text_contributions(self) -> None:
        explainer = HybridSearchExplainer(image_weight=0.7, text_weight=0.3)
        result = _result(image_score=0.9, text_score=0.8, score=0.87)

        trace = explainer.explain(result)

        assert trace.decision_type == "hybrid_search"
        assert trace.breakdown is not None
        names = {c.name for c in trace.breakdown.components}
        assert names == {"image_similarity", "text_similarity"}
        image = next(c for c in trace.breakdown.components if c.name == "image_similarity")
        assert image.contribution == 0.9 * 0.7
        assert trace.breakdown.total == 0.87

    def test_confidence_is_the_final_score(self) -> None:
        explainer = HybridSearchExplainer(image_weight=0.7, text_weight=0.3)

        trace = explainer.explain(_result(score=0.9))

        assert trace.confidence == 0.9

    def test_summary_mentions_both_modalities(self) -> None:
        explainer = HybridSearchExplainer(image_weight=0.7, text_weight=0.3)

        summary = explainer.explain(_result(image_score=0.91, text_score=0.88)).summary

        assert "image similarity" in summary
        assert "text similarity" in summary

    def test_subject_id_is_the_product_id(self) -> None:
        explainer = HybridSearchExplainer(image_weight=0.7, text_weight=0.3)
        result = _result()

        trace = explainer.explain(result)

        assert trace.subject_id == str(result.product_id)
