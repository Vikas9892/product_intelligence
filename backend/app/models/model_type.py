"""`ModelType`: which kind of AI model one registered `ModelInfo` describes (Phase 13).

Mirrors every existing model-loading service this codebase already has,
one `ModelType` per: `CLIPEmbeddingService` (`IMAGE_EMBEDDING`),
`SentenceTransformerEmbeddingService` (`TEXT_EMBEDDING`), and
`CrossEncoderService` (`RERANKER`) — `ModelRegistry` (`app/services/
model_registry.py`) tracks each type's own set of registered versions
and its own currently-active one independently.
"""

from enum import StrEnum


class ModelType(StrEnum):
    """Which model-loading service a registered model belongs to."""

    IMAGE_EMBEDDING = "image_embedding"
    TEXT_EMBEDDING = "text_embedding"
    RERANKER = "reranker"
