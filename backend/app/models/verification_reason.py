"""Internal domain model: `VerificationReason`, one human-readable duplicate-verification reason (Phase 15).

`BusinessRulesEvaluator`/`DuplicateVerificationService` build a list of
these to explain *why* a product was (or wasn't) judged a duplicate — the
phase's own "make explanations human-readable" requirement. Each reason
carries both a stable machine `code` (for a caller that wants to branch
on the reason type without string-matching prose) and a `message` (the
human-readable sentence the API surfaces in its `reasons` array).

Distinct from `RerankReason` (Phase 11), which explains a single
candidate's *rank movement* after reranking; a `VerificationReason`
explains one *business-rule outcome* (same brand, category mismatch,
close price, ...) feeding the final duplicate decision.
"""

from pydantic import BaseModel, Field


class VerificationReason(BaseModel):
    """One explainable factor behind a duplicate-verification decision."""

    #: Stable machine-readable slug, e.g. "same_brand", "category_mismatch",
    #: "title_similarity", "close_price".
    code: str = Field(min_length=1)
    #: Human-readable sentence surfaced in the API's `reasons` array,
    #: e.g. "Same brand (Nike)" or "Title similarity 98%".
    message: str = Field(min_length=1)
