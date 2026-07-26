"""Internal domain model: `SimilaritySignal`, one dimension of a similarity comparison.

`SimilarityScorer` (Phase 8) computes one `SimilaritySignal` per signal
kind — `"image"`, `"text"`, `"metadata"`, `"attribute"` — when comparing a
newly-uploaded product against one retrieved candidate. Kept as its own
model (rather than four bare floats) so the weighted-confidence formula's
inputs are self-describing and independently inspectable/loggable, the
same reasoning `AttributePrediction` (Phase 7) already established for
"a value plus how confident we are in it plus where it came from."
"""

from pydantic import BaseModel, Field


class SimilaritySignal(BaseModel):
    """One named similarity score, its configured weight, and its contribution to the total.

    `contribution` is simply `score * weight`, computed once by whichever
    code builds this signal (see `SimilarityScorer._signal`) rather than
    re-derived by every reader — a `SimilaritySignal` is a self-contained
    record of "this is what this signal contributed," not a formula a
    caller has to re-evaluate.
    """

    name: str
    score: float = Field(ge=0, le=1)
    weight: float = Field(ge=0, le=1)
    contribution: float = Field(ge=0, le=1)
