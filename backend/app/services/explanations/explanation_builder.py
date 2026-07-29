"""`ExplanationBuilder`: pure helpers for assembling explanation primitives (Phase 16).

Stateless, deterministic construction of `DecisionWeight`s,
`ConfidenceBreakdown`s, and natural-language summaries from already-decided
inputs. Owns no decision logic and no I/O — it only phrases and structures
what a decision already produced, the same "compute the presentation, not
the decision" separation `RecommendationReason` -> explanation string
already draws. Every concrete explainer (Milestones 2-3) composes this
builder rather than re-implementing weight math or sentence assembly.
"""

from collections.abc import Sequence

from app.models.confidence_breakdown import ConfidenceBreakdown
from app.models.decision_reason import DecisionReason
from app.models.decision_weight import DecisionWeight


class ExplanationBuilder:
    """Assembles weights, confidence breakdowns, and natural-language summaries."""

    def weight(self, name: str, value: float, weight: float) -> DecisionWeight:
        """Build a `DecisionWeight`, computing `contribution = value * weight` once."""
        return DecisionWeight(name=name, value=value, weight=weight, contribution=value * weight)

    def breakdown(
        self, components: Sequence[DecisionWeight], *, total: float
    ) -> ConfidenceBreakdown:
        """Group `components` into a `ConfidenceBreakdown` with the given `total`."""
        return ConfidenceBreakdown(components=list(components), total=total)

    def summarize(self, lead_in: str, reasons: Sequence[DecisionReason]) -> str:
        """Join `reasons`' descriptions into one natural-language sentence after `lead_in`.

        Produces "`lead_in` A, B, and C." — an Oxford-comma list of the
        reason descriptions. With no reasons, returns `lead_in` alone
        (trimmed of a trailing colon/space), so a caller always gets a
        non-empty, grammatical summary. Purely presentational: the
        descriptions themselves come from whichever explainer built the
        reasons.
        """
        descriptions = [reason.description for reason in reasons if reason.description]
        prefix = lead_in.rstrip(": ").strip()
        if not descriptions:
            return f"{prefix}." if prefix else ""
        joined = _join_with_and(descriptions)
        return f"{prefix}: {joined}." if prefix else f"{joined}."


def _join_with_and(items: Sequence[str]) -> str:
    """Join items as "a", "a and b", or "a, b, and c" (Oxford comma)."""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"
