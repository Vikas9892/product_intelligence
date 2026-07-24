"""Fixed, non-configurable values shared across the backend.

Anything here is a value the codebase itself decides, not something an
operator should tune per-deployment — if it needs to differ between local,
staging, and production, it belongs in `settings.py` (as an environment
variable) instead, not here.
"""

from enum import StrEnum


class Environment(StrEnum):
    """Deployment environments the application can run in."""

    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"

    @property
    def is_production(self) -> bool:
        return self is Environment.PRODUCTION


class LogLevel(StrEnum):
    """Supported logging verbosity levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# --- API ---
API_V1_PREFIX = "/api/v1"

# --- Application identity ---
DEFAULT_APP_NAME = "product-intelligence-backend"
DEFAULT_APP_VERSION = "0.1.0"
DEFAULT_APP_DESCRIPTION = (
    "Multi-Modal Product Intelligence Engine — backend API. "
    "Ingests product text and images, then exposes search and AI-assisted "
    "metadata over HTTP."
)

# --- Security ---
# An obviously-fake fallback so local dev works with zero config. Settings
# validation rejects this value outside local/test environments — see
# Settings._validate_production_safety in settings.py.
INSECURE_DEFAULT_SECRET_KEY = "insecure-dev-secret-key-change-me-1234567890"

# --- Storage ---
SUPPORTED_IMAGE_EXTENSIONS: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")
# .jpg and .jpeg both map to "image/jpeg" — fewer MIME types than extensions.
SUPPORTED_IMAGE_MIME_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})
DEFAULT_UPLOAD_MAX_SIZE_MB = 10

# --- Image processing (Phase 3) ---
# Pillow's own format names (`Image.format` after a successful decode) —
# distinct from SUPPORTED_IMAGE_MIME_TYPES above, which is the client's
# *declared* Content-Type and cannot be trusted. This is checked against
# what Pillow actually decoded, independent of file extension or header.
SUPPORTED_IMAGE_PIL_FORMATS: frozenset[str] = frozenset({"JPEG", "PNG", "WEBP"})
# Every processed image is re-encoded to this format regardless of its
# original one — see ImageProcessingService for why standardizing the
# output format simplifies everything downstream (no alpha channel to
# worry about, one decoder for every later phase to support).
PROCESSED_IMAGE_FORMAT = "JPEG"
PROCESSED_IMAGE_EXTENSION = ".jpg"
# A generous safety ceiling (rejects decompression-bomb-scale images
# before any resizing work) — distinct from DEFAULT_PROCESSED_IMAGE_SIZE_PX,
# which is the much smaller target size images are actually resized to.
DEFAULT_MAX_IMAGE_DIMENSION_PX = 8000
DEFAULT_PROCESSED_IMAGE_SIZE_PX = 1024

# --- Image embeddings (Phase 4) ---
# openai/clip-vit-base-patch32's projection dimension is 512 — a
# well-known, moderately-sized CLIP checkpoint appropriate as a default.
DEFAULT_CLIP_MODEL_NAME = "openai/clip-vit-base-patch32"

# --- Pagination ---
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
