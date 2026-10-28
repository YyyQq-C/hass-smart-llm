"""Constants for the Smart LLM integration."""

from __future__ import annotations

DOMAIN = "smart_llm"

PROVIDER_CURSOR = "cursor"

CONF_PROVIDER = "provider"
CONF_API_KEY_ENCRYPTED = "api_key_encrypted"
CONF_API_KEY_EXPIRES_AT = "api_key_expires_at"
CONF_EMAIL = "email"
CONF_BRIDGE_BASE_URL = "bridge_base_url"
CONF_MODEL = "model"
CONF_AVAILABLE_MODELS = "available_models"
CONF_ACKNOWLEDGE_BRIDGE = "acknowledge_bridge"

# Same endpoints the Cursor TypeScript SDK uses for `Cursor.auth.login()`.
CURSOR_WEBSITE_URL = "https://cursor.com"
CURSOR_API_BASE_URL = "https://api2.cursor.sh"
CURSOR_LOGIN_PATH = "/loginDeepControl"
CURSOR_POLL_PATH = "/auth/poll"
CURSOR_CREATE_API_KEY_PATH = "/aiserver.v1.DashboardService/CreateUserApiKey"
CURSOR_GET_ME_PATH = "/aiserver.v1.DashboardService/GetMe"

# OpenAI-compatible Cursor Bridge. Unofficial community service.
DEFAULT_BRIDGE_BASE_URL = "https://cursorbridge.dev/v1"
DEFAULT_MODEL = "default"

# The SDK mints a key that expires after 90 days.
API_KEY_TTL_MS = 90 * 24 * 60 * 60 * 1000
API_KEY_NAME = "Home Assistant Smart LLM"

# Poll budget matches the SDK: ~20 minutes with backoff from 1s to 10s.
POLL_MAX_ATTEMPTS = 150
POLL_BASE_DELAY_MS = 1000
POLL_MAX_DELAY_MS = 10_000
POLL_BACKOFF = 1.2

MAX_TOOL_ITERATIONS = 10

DATA_KEY_MATERIAL = "smart_llm_key_material"

STORAGE_DIR = ".storage"
KEK_FILENAME = "smart_llm.kek"
INSTANCE_UUID_FILENAME = "core.uuid"
