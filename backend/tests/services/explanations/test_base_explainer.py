"""Unit tests for `BaseExplainer` — the generic explainer interface."""

from app.models.explanation_trace import ExplanationTrace
from app.services.explanations.base_explainer import BaseExplainer


class _StringExplainer(BaseExplainer[str]):
    """A trivial concrete explainer used only to exercise the interface."""

    def explain(self, subject: str) -> ExplanationTrace:
        return ExplanationTrace(decision_type="test", summary=f"Explained {subject}.")


class TestBaseExplainer:
    def test_a_concrete_subclass_returns_a_trace(self) -> None:
        explainer: BaseExplainer[str] = _StringExplainer()

        trace = explainer.explain("widget")

        assert trace.decision_type == "test"
        assert trace.summary == "Explained widget."
