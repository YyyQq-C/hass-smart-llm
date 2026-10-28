"""Constants for the Smart LLM integration."""

from __future__ import annotations

DOMAIN = "smart_llm"

PROVIDER_CURSOR = "cursor"
PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"

PROVIDER_LABELS = {
    PROVIDER_CURSOR: "Cursor",
    PROVIDER_OPENAI: "OpenAI",
    PROVIDER_ANTHROPIC: "Anthropic",
}

# Device page links. These stay in code so translation files contain no URLs.
PROVIDER_CONFIG_URL = {
    PROVIDER_CURSOR: "https://cursor.com/dashboard",
    PROVIDER_OPENAI: "https://platform.openai.com/api-keys",
    PROVIDER_ANTHROPIC: "https://console.anthropic.com/settings/keys",
}

# Assist entity, device, and config-entry title. Never include an email address.
AGENT_NAME = "Cursor"

# Entry ids whose options flow is signing out to link a different Cursor account.
# Setup must not start a competing reauth flow while this set contains the entry.
DATA_SWITCH_IN_PROGRESS = "smart_llm_switch_in_progress"

CONF_PROVIDER = "provider"
CONF_API_KEY = "api_key"
CONF_API_KEY_ENCRYPTED = "api_key_encrypted"
CONF_API_KEY_EXPIRES_AT = "api_key_expires_at"
CONF_EMAIL = "email"
CONF_BRIDGE_BASE_URL = "bridge_base_url"
CONF_BASE_URL = "base_url"
CONF_CONNECTION_MODE = "connection_mode"
CONF_MODEL = "model"
CONF_AVAILABLE_MODELS = "available_models"
CONF_ACKNOWLEDGE_BRIDGE = "acknowledge_bridge"

# Official cloud API, or the same key sent to a caller-supplied base URL.
CONNECTION_OFFICIAL = "official"
CONNECTION_COMPATIBLE = "compatible"

# Same endpoints the Cursor TypeScript SDK uses for `Cursor.auth.login()`.
CURSOR_WEBSITE_URL = "https://cursor.com"
CURSOR_API_BASE_URL = "https://api2.cursor.sh"
CURSOR_LOGIN_PATH = "/loginDeepControl"
CURSOR_POLL_PATH = "/auth/poll"
CURSOR_CREATE_API_KEY_PATH = "/aiserver.v1.DashboardService/CreateUserApiKey"
CURSOR_GET_ME_PATH = "/aiserver.v1.DashboardService/GetMe"
# User API key -> short-lived access token. The token is not stored.
CURSOR_EXCHANGE_API_KEY_PATH = "/auth/exchange_user_api_key"
# Current billing period. Amounts are US cents. Not a Cursor Bridge route.
CURSOR_PERIOD_USAGE_PATH = "/aiserver.v1.DashboardService/GetCurrentPeriodUsage"

# How often Cursor allowance sensors ask for the current period.
CURSOR_USAGE_INTERVAL_MINUTES = 30

# OpenAI-compatible Cursor Bridge. Unofficial community service.
DEFAULT_BRIDGE_BASE_URL = "https://cursorbridge.dev/v1"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_MODEL = "default"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"

# Pinned Messages API version. Sent as the ``anthropic-version`` header.
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MAX_TOKENS = 4096

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


def default_model_for(provider: str) -> str:
    """Suggested model id when the provider has not returned a list yet."""
    if provider == PROVIDER_OPENAI:
        return DEFAULT_OPENAI_MODEL
    if provider == PROVIDER_ANTHROPIC:
        return DEFAULT_ANTHROPIC_MODEL
    return DEFAULT_MODEL
