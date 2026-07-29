"""`BaseExplainer`: the interface every decision explainer implements (Phase 16).

An abstract seam between "some AI decision object" and the
`ExplanationTrace` that explains it — mirroring `BaseReranker`/
`BaseVectorStore`/`BaseQueue`. Generic over the subject type `T` so a
concrete explainer (`HybridSearchExplainer`, `DuplicateExplainer`, ...)
is fully typed against exactly the decision object it explains, and
`ExplanationService` can hold a heterogeneous set of them without any
`Any`. Explainers are pure and side-effect-free: `explain` reads a
decision and returns its trace, never mutating the decision or touching
inference — the phase's own "explanation generation must not affect
inference results" requirement, made structural.
"""

from abc import ABC, abstractmethod

from app.models.explanation_trace import ExplanationTrace


class BaseExplainer[T](ABC):
    """Turns one kind of AI decision object into an `ExplanationTrace`."""

    @abstractmethod
    def explain(self, subject: T) -> ExplanationTrace:
        """Return a human-readable, structured explanation of `subject`."""
        raise NotImplementedError
