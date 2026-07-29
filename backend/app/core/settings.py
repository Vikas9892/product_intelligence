"""Typed, validated application configuration schema.

Settings are grouped by concern (application, database, AI models, storage,
security, logging) as nested `BaseModel`s, then composed into one
`Settings` root that `pydantic-settings` populates from environment
variables and a `.env` file. Nested groups are addressed with a `__`
delimiter, e.g.:

    APPLICATION__PORT=8000
    DATABASE__URL=postgresql://...
    SECURITY__SECRET_KEY=...

This module defines the *schema* only — it does not instantiate `Settings`
or decide caching. That's `app.core.config`'s job. Keeping the two separate
means this file has no side effects and every class in it can be
constructed directly in a unit test without touching real environment
variables or `.env`.
"""

from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core import constants, paths


class ApplicationSettings(BaseModel):
    """Core app identity, HTTP server, and edge-middleware settings."""

    name: str = constants.DEFAULT_APP_NAME
    version: str = constants.DEFAULT_APP_VERSION
    environment: constants.Environment = constants.Environment.LOCAL
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    api_prefix: str = constants.API_V1_PREFIX

    #: `Host` headers the app will answer for (TrustedHostMiddleware).
    #: `["*"]` (accept any Host) is a fine local-dev default but is
    #: rejected in production — see `Settings._validate_production_safety`.
    trusted_hosts: list[str] = Field(default_factory=lambda: ["*"])

    #: Origins allowed to make cross-origin browser requests (CORSMiddleware).
    #: Empty by default — no cross-origin access until a deployment opts in
    #: by listing its actual frontend origin(s).
    cors_allowed_origins: list[str] = Field(default_factory=list)


class DatabaseSettings(BaseModel):
    """Primary datastore connection.

    Defaults to a relative SQLite file so the app runs with zero config
    locally. Production must override this — enforced in
    `Settings._validate_production_safety` below.
    """

    url: str = "sqlite+aiosqlite:///./storage/app.db"
    echo: bool = False
    pool_size: int = Field(default=5, ge=1, le=100)


class AIModelSettings(BaseModel):
    """AI provider and model configuration.

    `openai_api_key`/`embedding_model`/`llm_model` reserve the shape for a
    later, OpenAI-based *LLM* phase — no calls to them are made yet;
    "embedding_model" turned out to describe neither the image nor the
    text embedding model this codebase actually ended up using, so it
    stays reserved rather than repurposed. `clip_model_name`/
    `embedding_device`/`embedding_batch_size` are Phase 4's actual,
    in-use *image* embedding configuration; `text_model_name`/
    `text_device`/`text_batch_size`/`text_normalize` are Phase 6's actual,
    in-use *text* embedding configuration (Sentence Transformers, not
    OpenAI). All are kept as distinctly-named fields rather than sharing
    `embedding_model`, since a CLIP checkpoint name, a Sentence
    Transformers checkpoint name, and an OpenAI text-embedding model name
    are three unrelated settings that happen to share the word
    "embedding".
    """

    openai_api_key: SecretStr | None = None
    embedding_model: str = "text-embedding-3-small"
    llm_model: str = "gpt-4o-mini"
    request_timeout_seconds: float = Field(default=30.0, gt=0)

    #: Hugging Face Hub model id for the CLIP vision encoder.
    clip_model_name: str = constants.DEFAULT_CLIP_MODEL_NAME
    #: "auto" (use CUDA if available, else CPU), or an explicit torch
    #: device string ("cpu", "cuda", "cuda:0", ...).
    embedding_device: str = "auto"
    #: How many images `CLIPEmbeddingService.generate_embeddings` sends
    #: through the model in a single forward pass.
    embedding_batch_size: int = Field(default=8, gt=0)

    #: Hugging Face Hub model id for the Sentence Transformers text encoder.
    text_model_name: str = constants.DEFAULT_TEXT_MODEL_NAME
    #: Same "auto"/"cpu"/"cuda[:N]" convention as `embedding_device`.
    text_device: str = "auto"
    #: How many strings `SentenceTransformerEmbeddingService.embed_batch`
    #: sends through the model in a single forward pass.
    text_batch_size: int = Field(default=32, gt=0)
    #: Whether text embeddings are L2-normalized so cosine similarity
    #: reduces to a dot product — `CLIPEmbeddingService` normalizes
    #: manually (Phase 4); Sentence Transformers normalizes natively via
    #: `encode(normalize_embeddings=...)`, so this is a passthrough flag
    #: rather than a fixed behavior.
    text_normalize: bool = True


class VectorStoreSettings(BaseModel):
    """Qdrant vector store configuration for semantic product search (Phases 5-6).

    Two independent collections (Phase 6) — `image_collection_name`/
    `image_vector_size` for `CLIPEmbeddingService` output,
    `text_collection_name`/`text_vector_size` for
    `SentenceTransformerEmbeddingService` output — each auto-created by
    `QdrantVectorStore` on first use if it doesn't already exist. Each
    `*_vector_size` must match its corresponding embedding model's actual
    output dimension (`ai_models.clip_model_name`/`ai_models.text_model_name`)
    — kept as separate settings rather than read from `ai_models` directly,
    because a vector store's collection shape and an embedding model's
    output shape are conceptually independent facts that only happen to
    need the same value today.
    """

    url: str = "http://localhost:6333"
    image_collection_name: str = constants.DEFAULT_IMAGE_COLLECTION_NAME
    image_vector_size: int = Field(default=constants.DEFAULT_IMAGE_VECTOR_SIZE, gt=0)
    text_collection_name: str = constants.DEFAULT_TEXT_COLLECTION_NAME
    text_vector_size: int = Field(default=constants.DEFAULT_TEXT_VECTOR_SIZE, gt=0)
    #: Default number of neighbors a search returns when a caller doesn't
    #: specify `top_k` explicitly.
    default_top_k: int = Field(default=constants.DEFAULT_SEARCH_TOP_K, gt=0)


class HybridSearchSettings(BaseModel):
    """Score-fusion weights for `HybridSearchService` (Phase 6).

    `Final Score = image_weight * ImageScore + text_weight * TextScore`,
    with a missing modality contributing zero — see
    `HybridSearchService`'s own docstring for the full fusion algorithm.
    Kept as their own settings group (mirroring `VectorStoreSettings`
    being separate from `AIModelSettings`) rather than folded into
    `AIModelSettings`, since these are ranking/fusion behavior, not model
    configuration.
    """

    image_weight: float = Field(default=0.7, ge=0)
    text_weight: float = Field(default=0.3, ge=0)


class CatalogIntelligenceSettings(BaseModel):
    """Catalog enrichment configuration for `CatalogIntelligenceService` (Phase 7).

    `enabled` gates whether `ProductService` runs catalog enrichment at
    all; `enable_text_attributes`/`enable_image_attributes` separately
    gate whether `CatalogIntelligenceService` itself calls each
    extraction service — a deployment might want image analysis but not
    text (or vice versa) without disabling enrichment entirely.
    `attribute_confidence_threshold` is the quality gate an
    `AttributePrediction`/`CatalogTag` must clear to survive into the
    final `CatalogIntelligenceResult`; the three `quality_*_weight`
    fields are `CatalogIntelligenceService`'s quality-score formula,
    kept configurable rather than hardcoded constants.
    """

    enabled: bool = True
    enable_text_attributes: bool = True
    enable_image_attributes: bool = True
    attribute_confidence_threshold: float = Field(default=0.60, ge=0, le=1)
    max_generated_tags: int = Field(default=20, gt=0)
    quality_completeness_weight: float = Field(default=0.50, ge=0)
    quality_confidence_weight: float = Field(default=0.30, ge=0)
    quality_consistency_weight: float = Field(default=0.20, ge=0)


class DuplicateDetectionSettings(BaseModel):
    """Duplicate detection configuration for `DuplicateDetectionService` (Phase 8).

    The phase spec lists a separate `ENABLE_DUPLICATE_DETECTION` flag
    alongside `DUPLICATE_MODE`'s own `OFF`/`WARN`/`BLOCK` values; since
    `OFF` already means "don't run duplicate detection," a second on/off
    flag would just be a redundant, independently-settable way to express
    the same disablement (and could disagree with `mode` — `enabled=True`
    with `mode=OFF`, or vice versa). `mode` alone is the single source of
    truth here, the same "one flag, not two disagreeing ones" reasoning
    applied. `threshold` is the minimum `overall_similarity` a candidate
    must reach to be treated as a match; `top_k` bounds how many
    candidates `HybridSearchService` retrieves for scoring; the four
    `*_weight` fields are `SimilarityScorer`'s confidence formula and are
    required to sum to `1.0` (validated below) since they represent a
    complete split of "how much each signal counts."
    """

    mode: constants.DuplicateDetectionMode = constants.DuplicateDetectionMode.WARN
    threshold: float = Field(default=0.90, ge=0, le=1)
    top_k: int = Field(default=10, gt=0)
    image_weight: float = Field(default=0.35, ge=0)
    text_weight: float = Field(default=0.25, ge=0)
    metadata_weight: float = Field(default=0.20, ge=0)
    attribute_weight: float = Field(default=0.20, ge=0)

    @model_validator(mode="after")
    def _validate_weights_sum_to_one(self) -> "DuplicateDetectionSettings":
        total = self.image_weight + self.text_weight + self.metadata_weight + self.attribute_weight
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                "duplicate_detection's image_weight + text_weight + metadata_weight + "
                f"attribute_weight must sum to 1.0 (got {total})"
            )
        return self


class RecommendationSettings(BaseModel):
    """Recommendation configuration for `RecommendationEngineService` (Phase 9).

    Unlike `DuplicateDetectionSettings` (which collapsed its own
    would-be `enabled` flag into `mode`'s `OFF` value, since the two could
    disagree), there's no separate mode enum here to collapse into —
    `enabled` is the one on/off switch. `top_k` is the default number of
    recommendations returned (a per-request `top_k` can still override
    it); `diversity_enabled` toggles the round-robin-by-brand diversity
    filter. The four `*_weight` fields are `RecommendationScorer`'s final-
    score formula and are required to sum to `1.0` (validated below),
    matching `DuplicateDetectionSettings`'s own reasoning: they represent
    a complete split of "how much each signal counts." `cache_ttl_seconds`
    (Phase 12) is how long `RecommendationCacheRepository` keeps a
    product's worker-precomputed recommendations before a fresh
    `GET /products/{id}/recommendations` call recomputes them live.
    """

    enabled: bool = True
    top_k: int = Field(default=10, gt=0)
    diversity_enabled: bool = True
    similarity_weight: float = Field(default=0.55, ge=0)
    attribute_weight: float = Field(default=0.20, ge=0)
    tag_weight: float = Field(default=0.15, ge=0)
    quality_weight: float = Field(default=0.10, ge=0)
    cache_ttl_seconds: float = Field(default=3600.0, gt=0)

    @model_validator(mode="after")
    def _validate_weights_sum_to_one(self) -> "RecommendationSettings":
        total = (
            self.similarity_weight + self.attribute_weight + self.tag_weight + self.quality_weight
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                "recommendation's similarity_weight + attribute_weight + tag_weight + "
                f"quality_weight must sum to 1.0 (got {total})"
            )
        return self


class EvaluationSettings(BaseModel):
    """Offline evaluation/benchmark configuration for `RetrievalEvaluator` (Phase 10).

    `top_k` is the default cutoff used when an evaluation query doesn't
    specify its own; `benchmark_output_dir` is where `scripts/benchmark.py`
    writes `benchmark.json`/`benchmark.md`. `latency_metrics_enabled` lets
    an operator turn off per-query latency measurement (still cheap, but
    not free) without disabling evaluation entirely.
    """

    enabled: bool = True
    top_k: int = Field(default=10, gt=0)
    benchmark_output_dir: Path = paths.REPORTS_DIR
    latency_metrics_enabled: bool = True


class RerankerSettings(BaseModel):
    """Cross-encoder reranking configuration for `RerankerService` (Phase 11).

    `enabled` defaults to `False` — unlike every other feature flag in
    this codebase, turning this one on adds a *real transformer model
    load and inference call* to every hybrid search/recommendation/
    duplicate-detection request it applies to, not a deterministic,
    already-cheap computation (`CatalogIntelligenceSettings.enabled`,
    `RecommendationSettings.enabled`, ... are all safe to default on for
    exactly that reason). Defaulting reranking on would silently break
    this project's own "zero-config, runs locally without extra setup"
    promise (see `DatabaseSettings`'s docstring) the first time any route
    that searches by text is hit without a Qdrant-backed catalog and
    internet access to fetch the model. `top_n` is how many top
    hybrid-search candidates get reranked (the "50" in "Hybrid Search ->
    Top 50 -> Cross Encoder"); `batch_size` bounds how many query-product
    pairs `CrossEncoderService` scores in one model forward pass, the
    same reasoning `AIModelSettings.embedding_batch_size`/`text_batch_size`
    already establish. `device` follows the exact same "auto"/"cpu"/
    "cuda[:N]" convention `embedding_device`/`text_device` do.
    """

    enabled: bool = False
    model_name: str = constants.DEFAULT_RERANKER_MODEL_NAME
    top_n: int = Field(default=50, gt=0)
    batch_size: int = Field(default=16, gt=0)
    device: str = "auto"


class AsyncPipelineSettings(BaseModel):
    """Background job/queue/worker pipeline configuration (Phase 12).

    `enabled` defaults to `True` — unlike `RerankerSettings.enabled`
    (Phase 11, which stays off by default because it bolts an optional,
    heavy refinement onto already-working synchronous endpoints), this
    flag *is* the phase's own deliverable: turning it off intentionally
    falls back to the old, fully-synchronous `POST /products/upload`
    behavior (still supported, for simple local dev without Redis
    running), but the async pipeline is what production is meant to run.
    `queue_backend` is currently only ever `"redis"` — kept as a string
    rather than an enum with one member so a second backend can be added
    later without a schema-breaking rename, the same reasoning
    `AIModelSettings.openai_api_key` reserves shape ahead of need.
    `max_retries`/`retry_delay_seconds` are `RedisQueue`'s exponential-
    backoff policy (`ProductWorker`); `worker_concurrency` is how many
    `ProductWorker` loops `WorkerManager` runs concurrently;
    `job_timeout_seconds` is reserved for a future stuck-job watchdog —
    not enforced yet (see `WorkerManager`'s own docstring).
    """

    enabled: bool = True
    queue_backend: str = "redis"
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "product_processing"
    max_retries: int = Field(default=5, ge=0)
    retry_delay_seconds: float = Field(default=5.0, gt=0)
    worker_concurrency: int = Field(default=4, gt=0)
    job_timeout_seconds: float = Field(default=300.0, gt=0)


class MetricsSettings(BaseModel):
    """Observability configuration for the metrics/health layer (Phase 14).

    `enabled` gates whether any of this phase's instrumentation records
    metrics at all — every call site checks this once (see
    `MetricsRegistry`'s own docstring) rather than each of the dozen+
    instrumented services re-reading settings individually.
    `prometheus_enabled` separately gates only the `GET /metrics` HTTP
    endpoint (`enabled=True, prometheus_enabled=False` still records
    metrics in-process, just doesn't expose them — e.g. for a deployment
    that scrapes metrics some other way). `health_endpoints_enabled`
    gates `GET /system/health`/`GET /system/stats` independently of
    both, since a health check has nothing to do with whether metrics
    are being recorded. `namespace` is the prefix prepended to every
    metric name (`prometheus_client`'s own `namespace=` constructor
    argument) — `product_upload_seconds` becomes
    `product_intelligence_product_upload_seconds`.
    """

    enabled: bool = True
    prometheus_enabled: bool = True
    health_endpoints_enabled: bool = True
    namespace: str = "product_intelligence"


class StorageSettings(BaseModel):
    """Local/object storage for uploaded product assets."""

    upload_dir: Path = paths.UPLOAD_DIR
    max_upload_size_mb: int = Field(default=constants.DEFAULT_UPLOAD_MAX_SIZE_MB, gt=0)
    allowed_image_extensions: tuple[str, ...] = constants.SUPPORTED_IMAGE_EXTENSIONS

    #: Where processed (normalized, resized) images are written — Phase 3.
    processed_dir: Path = paths.PROCESSED_DIR
    #: Hard safety ceiling: reject images larger than this in either
    #: dimension before doing any resizing work (decompression-bomb
    #: protection). Distinct from `processed_image_size_px` below.
    max_image_dimension_px: int = Field(default=constants.DEFAULT_MAX_IMAGE_DIMENSION_PX, gt=0)
    #: Target size images are resized to (preserving aspect ratio) — the
    #: standardized dimension downstream AI models will consume.
    processed_image_size_px: int = Field(default=constants.DEFAULT_PROCESSED_IMAGE_SIZE_PX, gt=0)


class SecuritySettings(BaseModel):
    """Auth/crypto configuration."""

    secret_key: SecretStr = SecretStr(constants.INSECURE_DEFAULT_SECRET_KEY)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, gt=0)

    @field_validator("secret_key")
    @classmethod
    def _minimum_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 16:
            raise ValueError("security.secret_key must be at least 16 characters long")
        return value


class LoggingSettings(BaseModel):
    """Logging behaviour."""

    level: constants.LogLevel = constants.LogLevel.INFO
    json_logs: bool = False


class Settings(BaseSettings):
    """Root settings object composed of the grouped settings above.

    Precedence (highest to lowest): constructor kwargs > environment
    variables > `.env` file > the field defaults declared on each group.
    """

    model_config = SettingsConfigDict(
        env_file=str(paths.ENV_FILE),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    application: ApplicationSettings = Field(default_factory=ApplicationSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    ai_models: AIModelSettings = Field(default_factory=AIModelSettings)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    hybrid_search: HybridSearchSettings = Field(default_factory=HybridSearchSettings)
    catalog_intelligence: CatalogIntelligenceSettings = Field(
        default_factory=CatalogIntelligenceSettings
    )
    duplicate_detection: DuplicateDetectionSettings = Field(
        default_factory=DuplicateDetectionSettings
    )
    recommendation: RecommendationSettings = Field(default_factory=RecommendationSettings)
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings)
    reranker: RerankerSettings = Field(default_factory=RerankerSettings)
    async_pipeline: AsyncPipelineSettings = Field(default_factory=AsyncPipelineSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    @model_validator(mode="after")
    def _validate_production_safety(self) -> "Settings":
        """Fail fast at startup if production is misconfigured.

        Silently "correcting" an insecure production config (e.g. forcing
        debug off) would hide the mistake instead of catching it — raising
        here turns a misconfigured deploy into an immediate boot failure.
        """
        if self.application.environment is constants.Environment.PRODUCTION:
            if self.security.secret_key.get_secret_value() == constants.INSECURE_DEFAULT_SECRET_KEY:
                raise ValueError(
                    "security.secret_key must be overridden in production "
                    "(SECURITY__SECRET_KEY) — the insecure default is not allowed."
                )
            if self.application.debug:
                raise ValueError("application.debug must be false in production.")
            if self.database.url.lower().startswith("sqlite"):
                raise ValueError(
                    "database.url must not be SQLite in production "
                    "(DATABASE__URL) — SQLite is a local/dev/test-only store."
                )
            if self.application.trusted_hosts == ["*"]:
                raise ValueError(
                    "application.trusted_hosts must not be the wildcard default in "
                    "production (APPLICATION__TRUSTED_HOSTS) — accepting any Host "
                    "header allows Host-header injection attacks."
                )
        return self
