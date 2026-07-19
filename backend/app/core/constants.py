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

# --- Security ---
# An obviously-fake fallback so local dev works with zero config. Settings
# validation rejects this value outside local/test environments — see
# Settings._validate_production_safety in settings.py.
INSECURE_DEFAULT_SECRET_KEY = "insecure-dev-secret-key-change-me-1234567890"

# --- Storage ---
SUPPORTED_IMAGE_EXTENSIONS: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")
DEFAULT_UPLOAD_MAX_SIZE_MB = 10

# --- Pagination ---
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
