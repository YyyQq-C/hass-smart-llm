"""Config and options flows for Smart LLM."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    SOURCE_REAUTH,
)
from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT
from homeassistant.core import callback
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    AGENT_NAME,
    CONF_ACKNOWLEDGE_BRIDGE,
    CONF_API_KEY,
    CONF_API_KEY_ENCRYPTED,
    CONF_API_KEY_EXPIRES_AT,
    CONF_AVAILABLE_MODELS,
    CONF_BASE_URL,
    CONF_BRIDGE_BASE_URL,
    CONF_CONNECTION_MODE,
    CONF_EMAIL,
    CONF_MODEL,
    CONF_PROVIDER,
    CONNECTION_COMPATIBLE,
    CONNECTION_OFFICIAL,
    DEFAULT_BRIDGE_BASE_URL,
    DEFAULT_MODEL,
    DOMAIN,
    PROVIDER_ANTHROPIC,
    PROVIDER_CURSOR,
    PROVIDER_LABELS,
    PROVIDER_OPENAI,
)
from .crypto import DecryptionError, mask_secret
from .flow_input import (
    api_key_is_optional,
    parse_api_key,
    parse_connection,
    parse_model_id,
    suggested_model,
)
from .identity import (
    account_unique_id,
    api_provider_unique_id,
    clear_account_switch,
    credential_update_block,
    display_account,
    mark_account_switch,
    options_with_refreshed_models,
    public_title,
    unique_id_for_login,
    without_stored_credentials,
)
from .provider.cursor_auth import (
    LoginHandshake,
    LoginResult,
    async_login_and_mint,
    create_login_handshake,
)
from .provider.cursor_bridge import CursorBridgeClient, normalize_bridge_base_url
from .provider.errors import (
    CursorAuthError,
    CursorLoginError,
    ProviderAPIError,
    ProviderAuthError,
)
from .provider.registry import create_chat_provider, provider_menu_options
from .provider.urls import resolve_base_url
from .secrets import async_decrypt, async_encrypt

_LOGGER = logging.getLogger(__name__)


def masked_provider_title(provider: str, api_key: str) -> str:
    label = PROVIDER_LABELS.get(provider, provider)
    if not api_key.strip():
        return label
    return f"{label} ({mask_secret(api_key)})"


def _ensure_default_model(models: list[str]) -> list[str]:
    if DEFAULT_MODEL not in models:
        return [DEFAULT_MODEL, *models]
    return list(models)


class _CursorBrowserLogin:
    """Shared browser-login steps for the config flow and the options flow."""

    _handshake: LoginHandshake | None = None
    _poll_task: asyncio.Task[None] | None = None
    _login_result: LoginResult | None = None
    _login_error: str | None = None
    _link_step_id: str = "cursor_link"
    _pinned_account: str | None = None

    def _display_account(self) -> str:
        """Account label for forms. Subclasses override this."""
        if self._pinned_account:
            return self._pinned_account
        result = self._login_result
        if result is not None:
            return display_account(result.email)
        return AGENT_NAME

    async def async_step_cursor_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the portal URL, then poll once the user continues."""
        if user_input is not None:
            self._login_error = None
            if self._handshake is None:
                self._handshake = create_login_handshake()
            return await self.async_step_cursor_poll()

        if self._handshake is None:
            self._handshake = create_login_handshake()
        login_url = self._handshake.login_url
        return self.async_show_form(
            step_id=self._link_step_id,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "login_url",
                        description={"suggested_value": login_url},
                    ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
                }
            ),
            description_placeholders={
                "login_url": login_url,
                "account": self._display_account(),
            },
            errors={"base": self._login_error} if self._login_error else {},
        )

    async def async_step_cursor_poll(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Poll Cursor until the browser login finishes or fails."""
        if self._handshake is None:
            return await self.async_step_cursor_link()
        if self._poll_task is None:
            self._poll_task = self.hass.async_create_task(self._async_run_login())
        if not self._poll_task.done():
            return self.async_show_progress(
                step_id="cursor_poll",
                progress_action="authorize",
                description_placeholders={"login_url": self._handshake.login_url},
                progress_task=self._poll_task,
            )
        return self.async_show_progress_done(next_step_id="cursor_done")

    async def async_step_cursor_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Leave the progress spinner and continue."""
        task = self._poll_task
        if task is not None and task.cancelled():
            return self.async_abort(reason="cancelled")
        if task is not None and not task.cancelled():
            error = task.exception()
            if error is not None and self._login_error is None:
                _LOGGER.warning("Cursor login task failed")
                self._login_error = "unknown"
        if self._login_error or self._login_result is None:
            self._poll_task = None
            self._handshake = None
            return await self.async_step_cursor_link()
        return await self._async_login_succeeded()

    async def _async_run_login(self) -> None:
        assert self._handshake is not None
        try:
            self._login_result = await async_login_and_mint(
                async_get_clientsession(self.hass),
                self._handshake,
                on_get_fallback=lambda message: _LOGGER.warning("%s", message),
            )
            self._login_error = None
        except asyncio.CancelledError:
            raise
        except CursorLoginError as err:
            self._login_result = None
            self._login_error = err.code
            _LOGGER.warning("Cursor browser login failed (%s)", err.code)
        except Exception:
            self._login_result = None
            self._login_error = "unknown"
            _LOGGER.exception("Unexpected Cursor browser login failure")

    async def _async_login_succeeded(self) -> ConfigFlowResult:
        raise NotImplementedError


class _ApiKeySetup:
    """API-key steps for OpenAI and Anthropic, shared by both flows."""

    _api_provider: str | None = None
    _plain_api_key: str | None = None
    _connection_mode: str | None = None
    _resolved_base: str | None = None
    _api_models: list[str] | None = None
    _api_list_error: str | None = None
    _refreshed_models: list[str] | None = None
    _refresh_error: str | None = None

    def _provider_label(self) -> str:
        return PROVIDER_LABELS.get(self._api_provider or "", "Smart LLM")

    async def async_step_openai(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect an OpenAI API key."""
        self._api_provider = PROVIDER_OPENAI
        return await self.async_step_api_key()

    async def async_step_anthropic(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect an Anthropic API key."""
        self._api_provider = PROVIDER_ANTHROPIC
        return await self.async_step_api_key()

    async def async_step_api_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose official API or a custom base URL, then check the key."""
        if self._api_provider not in {PROVIDER_OPENAI, PROVIDER_ANTHROPIC}:
            return self.async_abort(reason="unknown")
        errors: dict[str, str] = {}
        suggested: dict[str, Any] = {
            CONF_CONNECTION_MODE: CONNECTION_OFFICIAL,
            CONF_BASE_URL: "",
        }
        if user_input is not None:
            mode = str(
                user_input.get(CONF_CONNECTION_MODE) or CONNECTION_OFFICIAL
            ).strip()
            allow_empty = api_key_is_optional(self._api_provider, mode)
            key, key_errors = parse_api_key(user_input, allow_empty=allow_empty)
            parsed, conn_errors = parse_connection(self._api_provider, user_input)
            errors.update(key_errors)
            errors.update(conn_errors)
            suggested = {
                CONF_CONNECTION_MODE: user_input.get(
                    CONF_CONNECTION_MODE, CONNECTION_OFFICIAL
                ),
                CONF_BASE_URL: user_input.get(CONF_BASE_URL, ""),
            }
            if key:
                suggested[CONF_API_KEY] = key
            if not errors and key is not None and parsed is not None:
                self._plain_api_key = key
                self._connection_mode = parsed.mode
                self._resolved_base = parsed.base_url
                list_error = await self._async_probe_models()
                if list_error == "provider_auth":
                    errors["base"] = "provider_auth"
                    self._plain_api_key = None
                elif list_error == "invalid_url":
                    errors[CONF_BASE_URL] = "invalid_url"
                    self._plain_api_key = None
                elif list_error == "invalid_api_key":
                    errors[CONF_API_KEY] = "invalid_api_key"
                    self._plain_api_key = None
                else:
                    self._api_list_error = list_error
                    return await self.async_step_provider_model()
        return self.async_show_form(
            step_id="api_key",
            data_schema=self.add_suggested_values_to_schema(
                _api_key_schema(), suggested
            ),
            errors=errors,
            description_placeholders={"provider": self._provider_label()},
        )

    async def async_step_provider_model(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the model used by Assist. The key is already in memory."""
        if self._plain_api_key is None or self._api_provider is None:
            return await self.async_step_api_key()
        errors: dict[str, str] = {}
        models = list(self._api_models or [])
        if user_input is not None:
            parsed, conn_errors = parse_connection(self._api_provider, user_input)
            errors.update(conn_errors)
            model = parse_model_id(user_input.get(CONF_MODEL))
            if model is None:
                errors[CONF_MODEL] = "invalid_model"
            prompt = str(user_input.get(CONF_PROMPT) or "").strip()
            llm_api = _clean_llm_api(user_input.get(CONF_LLM_HASS_API))
            if (
                not conn_errors
                and parsed is not None
                and (
                    parsed.mode != self._connection_mode
                    or parsed.base_url != self._resolved_base
                )
            ):
                self._connection_mode = parsed.mode
                self._resolved_base = parsed.base_url
                list_error = await self._async_probe_models()
                self._api_list_error = list_error
                models = list(self._api_models or [])
                if list_error == "invalid_url":
                    errors[CONF_BASE_URL] = "invalid_url"
                elif list_error == "provider_auth":
                    errors["base"] = "provider_auth"
                elif list_error == "invalid_api_key":
                    errors["base"] = "api_key_required"
                elif list_error == "provider_connect":
                    errors["base"] = "provider_connect"
                elif list_error == "provider_no_models":
                    errors["base"] = "provider_no_models"
                elif list_error:
                    errors["base"] = "unknown"
            elif self._api_list_error == "provider_auth":
                errors["base"] = "provider_auth"
            if (
                not errors
                and parsed is not None
                and model is not None
            ):
                return await self._async_create_api_entry(
                    parsed, model, prompt, llm_api
                )
            suggested = {
                key: value
                for key, value in user_input.items()
                if key != CONF_API_KEY and value is not None
            }
        else:
            mode = self._connection_mode or CONNECTION_OFFICIAL
            suggested = {
                CONF_CONNECTION_MODE: mode,
                CONF_BASE_URL: ""
                if mode == CONNECTION_OFFICIAL
                else (self._resolved_base or ""),
                CONF_MODEL: suggested_model(self._api_provider, models),
            }
            if self._api_list_error == "provider_connect":
                errors["base"] = "provider_connect"
            elif self._api_list_error == "provider_no_models":
                errors["base"] = "provider_no_models"
            elif self._api_list_error:
                errors["base"] = "unknown"
        return self.async_show_form(
            step_id="provider_model",
            data_schema=self.add_suggested_values_to_schema(
                _provider_model_schema(self.hass, models),
                suggested,
            ),
            errors=errors,
            description_placeholders={
                "provider": self._provider_label(),
                "masked_key": mask_secret(self._plain_api_key),
                "base_url": self._resolved_base or "",
            },
        )

    async def async_step_api_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update request style, base URL, model, prompt, and Assist tools."""
        entry = self.config_entry
        provider = entry.data.get(CONF_PROVIDER, PROVIDER_OPENAI)
        self._api_provider = provider
        errors: dict[str, str] = {}
        current = dict(entry.options)
        if self._refreshed_models is not None:
            models = list(self._refreshed_models)
        else:
            models = list(current.get(CONF_AVAILABLE_MODELS) or [])
        current_model = current.get(CONF_MODEL)
        if (
            isinstance(current_model, str)
            and current_model
            and current_model not in models
        ):
            models = [current_model, *models]
        if user_input is not None:
            parsed, conn_errors = parse_connection(provider, user_input)
            errors.update(conn_errors)
            model = parse_model_id(user_input.get(CONF_MODEL))
            if model is None:
                errors[CONF_MODEL] = "invalid_model"
            prompt = str(user_input.get(CONF_PROMPT) or "").strip()
            llm_api = _clean_llm_api(user_input.get(CONF_LLM_HASS_API))
            if (
                not errors
                and parsed is not None
                and model is not None
                and parsed.mode == CONNECTION_OFFICIAL
                and provider == PROVIDER_OPENAI
                and not entry.data.get(CONF_API_KEY_ENCRYPTED)
            ):
                errors["base"] = "api_key_required"
            if not errors and parsed is not None and model is not None:
                updated = dict(current)
                updated[CONF_CONNECTION_MODE] = parsed.mode
                if parsed.mode == CONNECTION_COMPATIBLE:
                    updated[CONF_BASE_URL] = parsed.base_url
                else:
                    updated.pop(CONF_BASE_URL, None)
                updated[CONF_MODEL] = model
                stored_models = list(models)
                if model not in stored_models:
                    stored_models.append(model)
                updated[CONF_AVAILABLE_MODELS] = stored_models
                if prompt:
                    updated[CONF_PROMPT] = prompt
                else:
                    updated.pop(CONF_PROMPT, None)
                if llm_api:
                    updated[CONF_LLM_HASS_API] = llm_api
                else:
                    updated.pop(CONF_LLM_HASS_API, None)
                return self.async_create_entry(title="", data=updated)
            suggested = {
                key: value
                for key, value in user_input.items()
                if value is not None
            }
        else:
            mode = current.get(CONF_CONNECTION_MODE, CONNECTION_OFFICIAL)
            suggested = {
                CONF_CONNECTION_MODE: mode,
                CONF_BASE_URL: current.get(CONF_BASE_URL, "")
                if mode == CONNECTION_COMPATIBLE
                else "",
                CONF_MODEL: current.get(CONF_MODEL, suggested_model(provider, models)),
                CONF_PROMPT: current.get(CONF_PROMPT, ""),
            }
            if current.get(CONF_LLM_HASS_API):
                suggested[CONF_LLM_HASS_API] = current[CONF_LLM_HASS_API]
            if self._refresh_error:
                errors["base"] = self._refresh_error
        masked, account = await _identity(self.hass, entry)
        return self.async_show_form(
            step_id="api_settings",
            data_schema=self.add_suggested_values_to_schema(
                _provider_model_schema(self.hass, models),
                suggested,
            ),
            errors=errors,
            description_placeholders={
                "provider": PROVIDER_LABELS.get(provider, provider),
                "masked_key": masked,
                "base_url": _display_base_url(provider, current),
                "account": account,
            },
        )

    async def async_step_update_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace the stored API key after a model-list check."""
        entry = _flow_entry(self)
        provider = entry.data.get(CONF_PROVIDER, PROVIDER_OPENAI)
        self._api_provider = provider
        errors: dict[str, str] = {}
        if user_input is not None:
            key, key_errors = parse_api_key(user_input)
            errors.update(key_errors)
            if not errors and key:
                self._plain_api_key = key
                try:
                    self._resolved_base = resolve_base_url(provider, entry.options)
                    self._connection_mode = entry.options.get(
                        CONF_CONNECTION_MODE, CONNECTION_OFFICIAL
                    )
                except ValueError:
                    errors["base"] = "invalid_url"
                else:
                    list_error = await self._async_probe_models()
                    if list_error == "provider_auth":
                        errors["base"] = "provider_auth"
                    elif list_error in {"provider_connect", "unknown", "invalid_url"}:
                        errors["base"] = (
                            "invalid_url" if list_error == "invalid_url" else "provider_connect"
                        )
                    else:
                        self._plain_api_key = None
                        return await _async_replace_api_key(self, entry, key)
                self._plain_api_key = None
        masked, account = await _identity(self.hass, entry)
        return self.async_show_form(
            step_id="update_key",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"masked_key": masked, "account": account},
        )

    async def async_step_remove_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Forget the stored API key. The provider key is not revoked."""
        entry = self.config_entry
        if user_input is None:
            masked, account = await _identity(self.hass, entry)
            return self.async_show_form(
                step_id="remove_key",
                data_schema=vol.Schema({}),
                description_placeholders={"masked_key": masked, "account": account},
            )
        return await _async_forget_key(self, entry)

    async def _async_probe_models(self) -> str | None:
        """List models. Return an error key, or None when the list loaded."""
        assert self._plain_api_key is not None
        assert self._api_provider is not None
        assert self._resolved_base is not None
        try:
            client = create_chat_provider(
                self._api_provider,
                session=async_get_clientsession(self.hass),
                api_key=self._plain_api_key,
                base_url=self._resolved_base,
            )
            self._api_models = await client.async_list_models()
            return None
        except ProviderAuthError:
            self._api_models = []
            _LOGGER.warning(
                "Model list rejected the API key (provider=%s)", self._api_provider
            )
            return "provider_auth"
        except ProviderAPIError as err:
            self._api_models = []
            _LOGGER.warning(
                "Model list failed (provider=%s, HTTP %s)",
                self._api_provider,
                err.status,
            )
            if err.status == 404:
                return "provider_no_models"
            return "provider_connect"
        except ValueError as err:
            self._api_models = []
            if "is empty" in str(err):
                return "invalid_api_key"
            return "invalid_url"
        except Exception:
            self._api_models = []
            _LOGGER.warning("Model list failed (provider=%s)", self._api_provider)
            return "unknown"

    async def _async_create_api_entry(
        self,
        parsed: Any,
        model: str,
        prompt: str,
        llm_api: list[str] | None,
    ) -> ConfigFlowResult:
        assert self._plain_api_key is not None
        assert self._api_provider is not None
        api_key = self._plain_api_key
        provider = self._api_provider
        if not api_key and not api_key_is_optional(provider, parsed.mode):
            self._plain_api_key = None
            return self.async_abort(reason="unknown")
        unique_id = api_provider_unique_id(
            provider,
            api_key,
            base_url="" if api_key else parsed.base_url,
        )
        existing = await self.async_set_unique_id(unique_id)
        if existing is not None:
            self._plain_api_key = None
            return self.async_abort(reason="provider_already_configured")
        data: dict[str, Any] = {CONF_PROVIDER: provider}
        if api_key:
            data[CONF_API_KEY_ENCRYPTED] = await async_encrypt(self.hass, api_key)
        models = list(self._api_models or [])
        if model not in models:
            models.append(model)
        options: dict[str, Any] = {
            CONF_CONNECTION_MODE: parsed.mode,
            CONF_MODEL: model,
            CONF_AVAILABLE_MODELS: models,
        }
        if parsed.mode == CONNECTION_COMPATIBLE:
            options[CONF_BASE_URL] = parsed.base_url
        if prompt:
            options[CONF_PROMPT] = prompt
        if llm_api:
            options[CONF_LLM_HASS_API] = llm_api
        title = masked_provider_title(provider, api_key)
        self._plain_api_key = None
        return self.async_create_entry(title=title, data=data, options=options)


class SmartLLMConfigFlow(ConfigFlow, _CursorBrowserLogin, _ApiKeySetup, domain=DOMAIN):
    """Walk the user through provider choice, sign-in, and model selection."""

    VERSION = 1

    _models: list[str] | None = None
    _listed_base: str | None = None
    _model_error: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose Cursor, OpenAI, or Anthropic."""
        return self.async_show_menu(
            step_id="user",
            menu_options=provider_menu_options(),
        )

    async def async_step_cursor(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start the Cursor browser login."""
        return await self.async_step_cursor_link()

    async def async_step_reauth(
        self, entry_data: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start browser login, or ask for a new API key."""
        entry = self._get_reauth_entry()
        provider = entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR)
        if provider == PROVIDER_CURSOR:
            return await self.async_step_cursor_link()
        self._api_provider = provider
        return await self.async_step_update_key()

    def _display_account(self) -> str:
        """Masked account, including during reauth before a new login exists."""
        if self._pinned_account:
            return self._pinned_account
        if self.source == SOURCE_REAUTH:
            return display_account(self._get_reauth_entry().data.get(CONF_EMAIL))
        result = self._login_result
        if result is not None:
            return display_account(result.email)
        return AGENT_NAME

    async def _async_login_succeeded(self) -> ConfigFlowResult:
        if self.source == SOURCE_REAUTH:
            return await _async_save_credentials(self, self._get_reauth_entry())
        return await self.async_step_cursor_model()

    async def async_step_cursor_model(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the Bridge URL and the model used by Assist."""
        assert self._login_result is not None
        errors: dict[str, str] = {}
        suggested_base = DEFAULT_BRIDGE_BASE_URL
        if user_input is not None:
            suggested_base = user_input.get(CONF_BRIDGE_BASE_URL, suggested_base)
        if self._models is None:
            await self._async_try_list_models(suggested_base)

        if user_input is not None:
            base_url, model, prompt, llm_api, form_errors = _parse_settings(
                user_input, require_acknowledgement=True
            )
            errors.update(form_errors)
            if (
                not errors
                and base_url is not None
                and base_url != self._listed_base
            ):
                await self._async_try_list_models(base_url)
            if (
                not errors
                and base_url is not None
                and base_url == self._listed_base
                and self._model_error == "invalid_auth"
            ):
                errors["base"] = "invalid_auth"
            if not errors and base_url is not None and model is not None:
                return await self._async_create(base_url, model, prompt, llm_api)
            suggested = {
                key: value
                for key, value in user_input.items()
                if value is not None
            }
        else:
            suggested = {
                CONF_BRIDGE_BASE_URL: suggested_base,
                CONF_MODEL: DEFAULT_MODEL,
                CONF_ACKNOWLEDGE_BRIDGE: False,
            }
            if self._model_error:
                errors["base"] = self._model_error

        result = self._login_result
        return self.async_show_form(
            step_id="cursor_model",
            data_schema=self.add_suggested_values_to_schema(
                _settings_schema(
                    self.hass,
                    models=self._models or [],
                    include_acknowledgement=True,
                ),
                suggested,
            ),
            errors=errors,
            description_placeholders={
                "bridge_base_url": str(
                    suggested.get(CONF_BRIDGE_BASE_URL, suggested_base)
                ),
                "masked_key": mask_secret(result.api_key),
                "account": display_account(result.email),
            },
        )

    async def _async_try_list_models(self, base_url: str) -> None:
        assert self._login_result is not None
        self._listed_base = base_url
        self._model_error = None
        try:
            client = CursorBridgeClient(
                async_get_clientsession(self.hass),
                api_key=self._login_result.api_key,
                base_url=base_url,
            )
            self._models = _ensure_default_model(await client.async_list_models())
        except CursorAuthError:
            self._models = []
            self._model_error = "invalid_auth"
        except (ProviderAPIError, ValueError):
            self._models = []
            self._model_error = "no_models"

    async def _async_create(
        self,
        base_url: str,
        model: str,
        prompt: str,
        llm_api: list[str] | None,
    ) -> ConfigFlowResult:
        assert self._login_result is not None
        result = self._login_result
        unique_id = account_unique_id(result.email, result.api_key)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        data = await _credential_data(self.hass, result)
        options: dict[str, Any] = {
            CONF_BRIDGE_BASE_URL: base_url,
            CONF_MODEL: model,
            CONF_AVAILABLE_MODELS: self._models or _ensure_default_model([model]),
        }
        if prompt:
            options[CONF_PROMPT] = prompt
        if llm_api:
            options[CONF_LLM_HASS_API] = llm_api
        return self.async_create_entry(title=AGENT_NAME, data=data, options=options)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SmartLLMOptionsFlow:
        """Return the options flow."""
        return SmartLLMOptionsFlow()


class SmartLLMOptionsFlow(OptionsFlow, _CursorBrowserLogin, _ApiKeySetup):
    """Change the model, refresh models, re-authorize, switch, or log out."""

    _refresh_task: asyncio.Task[None] | None = None
    _refreshed_models: list[str] | None = None
    _refresh_error: str | None = None
    _switching_account: bool = False

    def _display_account(self) -> str:
        """Masked account pinned before credentials are cleared."""
        if self._pinned_account:
            return self._pinned_account
        result = self._login_result
        if result is not None and result.email:
            return display_account(result.email)
        return display_account(self.config_entry.data.get(CONF_EMAIL))

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show what is stored, without revealing the API key or full email."""
        masked, account = await _identity(self.hass, self.config_entry)
        provider = self.config_entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR)
        if provider == PROVIDER_CURSOR:
            menu = [
                "settings",
                "refresh_models",
                "reauth",
                "switch_account",
                "logout",
            ]
        else:
            menu = ["api_settings", "refresh_models", "update_key", "remove_key"]
        return self.async_show_menu(
            step_id="init",
            menu_options=menu,
            description_placeholders={"masked_key": masked, "account": account},
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update the Bridge URL, model, prompt, and Assist tools."""
        errors: dict[str, str] = {}
        current = dict(self.config_entry.options)
        models = self._refreshed_models or list(current.get(CONF_AVAILABLE_MODELS) or [])
        if user_input is not None:
            base_url, model, prompt, llm_api, form_errors = _parse_settings(
                user_input, require_acknowledgement=False
            )
            errors.update(form_errors)
            if not errors and base_url is not None and model is not None:
                updated = dict(current)
                updated[CONF_BRIDGE_BASE_URL] = base_url
                updated[CONF_MODEL] = model
                if models:
                    updated[CONF_AVAILABLE_MODELS] = _ensure_default_model(models)
                if prompt:
                    updated[CONF_PROMPT] = prompt
                else:
                    updated.pop(CONF_PROMPT, None)
                if llm_api:
                    updated[CONF_LLM_HASS_API] = llm_api
                else:
                    updated.pop(CONF_LLM_HASS_API, None)
                return self.async_create_entry(title="", data=updated)
            suggested = {
                key: value
                for key, value in user_input.items()
                if value is not None
            }
        else:
            suggested = {
                CONF_BRIDGE_BASE_URL: current.get(
                    CONF_BRIDGE_BASE_URL, DEFAULT_BRIDGE_BASE_URL
                ),
                CONF_MODEL: current.get(CONF_MODEL, DEFAULT_MODEL),
                CONF_PROMPT: current.get(CONF_PROMPT, ""),
            }
            if current.get(CONF_LLM_HASS_API):
                suggested[CONF_LLM_HASS_API] = current[CONF_LLM_HASS_API]
            if self._refresh_error:
                errors["base"] = self._refresh_error

        masked, account = await _identity(self.hass, self.config_entry)
        return self.async_show_form(
            step_id="settings",
            data_schema=self.add_suggested_values_to_schema(
                _settings_schema(
                    self.hass,
                    models=models,
                    include_acknowledgement=False,
                ),
                suggested,
            ),
            errors=errors,
            description_placeholders={
                "bridge_base_url": suggested.get(
                    CONF_BRIDGE_BASE_URL, DEFAULT_BRIDGE_BASE_URL
                ),
                "masked_key": masked,
                "account": account,
            },
        )

    async def async_step_refresh_models(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fetch the model list and then return to the settings form."""
        if not _stored_key_or_local_openai(self.config_entry):
            return self.async_abort(reason="logged_out")
        provider = self.config_entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR)
        if self._refresh_task is None:
            self._refresh_task = self.hass.async_create_task(self._async_refresh_models())
        if not self._refresh_task.done():
            action = (
                "refresh_models" if provider == PROVIDER_CURSOR else "refresh_api_models"
            )
            return self.async_show_progress(
                step_id="refresh_models",
                progress_action=action,
                progress_task=self._refresh_task,
            )
        next_step = "settings" if provider == PROVIDER_CURSOR else "api_settings"
        return self.async_show_progress_done(next_step_id=next_step)

    async def _async_refresh_models(self) -> None:
        provider = self.config_entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR)
        try:
            api_key = await _async_entry_api_key(self.hass, self.config_entry)
            base_url = resolve_base_url(provider, self.config_entry.options)
            client = create_chat_provider(
                provider,
                session=async_get_clientsession(self.hass),
                api_key=api_key,
                base_url=base_url,
            )
            models = await client.async_list_models()
            if provider == PROVIDER_CURSOR:
                models = _ensure_default_model(models)
            self._refreshed_models = models
            self._refresh_error = None
        except (ProviderAuthError, DecryptionError):
            self._refresh_error = (
                "invalid_auth" if provider == PROVIDER_CURSOR else "provider_auth"
            )
        except (ProviderAPIError, ValueError):
            self._refresh_error = (
                "cannot_connect" if provider == PROVIDER_CURSOR else "provider_connect"
            )
        except Exception:
            self._refresh_error = "unknown"
            _LOGGER.exception("Refreshing models failed (provider=%s)", provider)

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Mint a new Cursor key, or replace an OpenAI/Anthropic key."""
        provider = self.config_entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR)
        if provider != PROVIDER_CURSOR:
            self._api_provider = provider
            return await self.async_step_update_key()
        self._switching_account = False
        self._link_step_id = "cursor_link"
        return await self.async_step_cursor_link()

    async def async_step_switch_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sign out, then link a different Cursor account."""
        if user_input is None:
            masked, account = await _identity(self.hass, self.config_entry)
            return self.async_show_form(
                step_id="switch_account",
                data_schema=vol.Schema({}),
                description_placeholders={"masked_key": masked, "account": account},
            )
        await self._async_begin_account_switch()
        return await self.async_step_switch_link()

    async def async_step_switch_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Browser login used to link the replacement Cursor account."""
        self._link_step_id = "switch_link"
        return await self.async_step_cursor_link(user_input)

    async def async_step_logout(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Forget the stored API key. The dashboard key stays valid until revoked."""
        if user_input is None:
            masked, account = await _identity(self.hass, self.config_entry)
            return self.async_show_form(
                step_id="logout",
                data_schema=vol.Schema({}),
                description_placeholders={"masked_key": masked, "account": account},
            )
        return await _async_forget_key(self, self.config_entry)

    async def _async_begin_account_switch(self) -> None:
        """Drop the stored key before the replacement login starts."""
        self._pinned_account = display_account(self.config_entry.data.get(CONF_EMAIL))
        self._switching_account = True
        self._link_step_id = "switch_link"
        self._handshake = None
        self._poll_task = None
        self._login_result = None
        self._login_error = None
        mark_account_switch(self.hass.data, self.config_entry.entry_id)
        _forget_credentials(self.hass, self.config_entry)

    async def _async_login_succeeded(self) -> ConfigFlowResult:
        if not self._switching_account:
            return await _async_save_credentials(self, self.config_entry)
        listed: list[str] | None = None
        if self._login_result is not None:
            listed = await self._async_list_models_for_key(self._login_result.api_key)
        options = options_with_refreshed_models(self.config_entry.options, listed)
        return await _async_save_credentials(
            self,
            self.config_entry,
            allow_different_account=True,
            options=options,
            abort_reason="switch_successful",
        )

    async def _async_list_models_for_key(self, api_key: str) -> list[str] | None:
        """Load Bridge models with a key that is not logged."""
        base_url = self.config_entry.options.get(
            CONF_BRIDGE_BASE_URL, DEFAULT_BRIDGE_BASE_URL
        )
        try:
            client = CursorBridgeClient(
                async_get_clientsession(self.hass),
                api_key=api_key,
                base_url=base_url,
            )
            return _ensure_default_model(await client.async_list_models())
        except (CursorAuthError, CursorAPIError, ValueError):
            _LOGGER.warning("Could not refresh Cursor Bridge models after account switch")
            return None
        except Exception:
            _LOGGER.exception("Refreshing Cursor Bridge models failed")
            return None

    async def async_remove(self) -> None:
        """If switch-account is abandoned, leave the entry needing reauth."""
        if self._switching_account:
            self._switching_account = False
            entry_id = self.config_entry.entry_id
            clear_account_switch(self.hass.data, entry_id)
            if not self.config_entry.data.get(CONF_API_KEY_ENCRYPTED):
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(entry_id)
                )
        await super().async_remove()


def _forget_credentials(hass: Any, entry: ConfigEntry) -> None:
    """Remove the stored Cursor credential and any email in the entry title."""
    hass.config_entries.async_update_entry(
        entry,
        data=without_stored_credentials(entry.data),
        title=public_title(entry.title),
    )


async def _async_save_credentials(
    flow: Any,
    entry: ConfigEntry,
    *,
    allow_different_account: bool = False,
    options: dict[str, Any] | None = None,
    abort_reason: str = "reauth_successful",
) -> ConfigFlowResult:
    """Write a new encrypted API key onto an existing entry."""
    result: LoginResult | None = flow._login_result
    if result is None:
        return flow.async_abort(reason="unknown")
    block = credential_update_block(
        entry.unique_id,
        result.email,
        allow_different_account=allow_different_account,
    )
    if block:
        return flow.async_abort(reason=block)
    new_unique_id = unique_id_for_login(
        entry.unique_id,
        result.email,
        result.api_key,
        allow_different_account=allow_different_account,
    )
    if new_unique_id:
        for other in flow.hass.config_entries.async_entries(DOMAIN):
            if other.entry_id != entry.entry_id and other.unique_id == new_unique_id:
                return flow.async_abort(reason="already_configured")
    data = without_stored_credentials(
        entry.data,
        keep_email=not result.email and not allow_different_account,
    )
    data.update(await _credential_data(flow.hass, result))
    if allow_different_account:
        clear_account_switch(flow.hass.data, entry.entry_id)
        flow._switching_account = False
    was_loaded = entry.state is ConfigEntryState.LOADED
    update_kwargs: dict[str, Any] = {
        "data": data,
        "title": public_title(entry.title),
    }
    if new_unique_id is not None:
        update_kwargs["unique_id"] = new_unique_id
    if options is not None:
        update_kwargs["options"] = options
    flow.hass.config_entries.async_update_entry(entry, **update_kwargs)
    if allow_different_account or not was_loaded:
        await flow.hass.config_entries.async_reload(entry.entry_id)
    return flow.async_abort(reason=abort_reason)


async def _credential_data(hass: Any, result: LoginResult) -> dict[str, Any]:
    data: dict[str, Any] = {
        CONF_PROVIDER: PROVIDER_CURSOR,
        CONF_API_KEY_ENCRYPTED: await async_encrypt(hass, result.api_key),
        CONF_API_KEY_EXPIRES_AT: result.expires_at_ms,
    }
    if result.email:
        data[CONF_EMAIL] = result.email
    return data


def _flow_entry(flow: Any) -> ConfigEntry:
    """Return the entry being edited. Reauth flows do not set ``config_entry``."""
    entry = getattr(flow, "config_entry", None)
    if entry is not None:
        return entry
    return flow._get_reauth_entry()


def _stored_key_or_local_openai(entry: ConfigEntry) -> bool:
    """True when a key is stored, or this is a local OpenAI-compatible entry."""
    if entry.data.get(CONF_API_KEY_ENCRYPTED):
        return True
    provider = entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR)
    mode = str(entry.options.get(CONF_CONNECTION_MODE) or "")
    return api_key_is_optional(provider, mode)


async def _async_entry_api_key(hass: Any, entry: ConfigEntry) -> str:
    """Return the stored key, or ``""`` for a local OpenAI-compatible entry."""
    encrypted = entry.data.get(CONF_API_KEY_ENCRYPTED)
    if not encrypted:
        if _stored_key_or_local_openai(entry):
            return ""
        raise ValueError("API key is empty")
    return await async_decrypt(hass, encrypted)


def _display_base_url(provider: str, options: Mapping[str, Any]) -> str:
    try:
        return resolve_base_url(provider, options)
    except ValueError:
        return ""


async def _async_forget_key(flow: Any, entry: ConfigEntry) -> ConfigFlowResult:
    """Drop the encrypted key and any stored email. The provider key stays valid."""
    if getattr(flow, "_switching_account", False):
        flow._switching_account = False
    clear_account_switch(flow.hass.data, entry.entry_id)
    _forget_credentials(flow.hass, entry)
    if entry.state is not ConfigEntryState.LOADED:
        await flow.hass.config_entries.async_reload(entry.entry_id)
    return flow.async_abort(reason="logged_out")


async def _async_replace_api_key(
    flow: Any, entry: ConfigEntry, api_key: str
) -> ConfigFlowResult:
    """Store a new encrypted API key. The plaintext is not written to the entry."""
    provider = entry.data.get(CONF_PROVIDER, PROVIDER_OPENAI)
    new_unique_id = api_provider_unique_id(provider, api_key)
    for other in flow.hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry.entry_id and other.unique_id == new_unique_id:
            return flow.async_abort(reason="provider_already_configured")
    data = dict(entry.data)
    data[CONF_PROVIDER] = provider
    data[CONF_API_KEY_ENCRYPTED] = await async_encrypt(flow.hass, api_key)
    data.pop(CONF_API_KEY_EXPIRES_AT, None)
    was_loaded = entry.state is ConfigEntryState.LOADED
    flow.hass.config_entries.async_update_entry(
        entry,
        data=data,
        unique_id=new_unique_id,
        title=masked_provider_title(provider, api_key),
    )
    if not was_loaded:
        await flow.hass.config_entries.async_reload(entry.entry_id)
    if getattr(flow, "source", None) == SOURCE_REAUTH:
        return flow.async_abort(reason="reauth_successful")
    return flow.async_abort(reason="api_key_updated")


async def _identity(hass: Any, entry: ConfigEntry) -> tuple[str, str]:
    encrypted = entry.data.get(CONF_API_KEY_ENCRYPTED)
    provider = entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR)
    if provider == PROVIDER_CURSOR:
        account = display_account(entry.data.get(CONF_EMAIL))
    else:
        account = PROVIDER_LABELS.get(provider, provider)
    if not encrypted:
        return "—", account
    try:
        api_key = await async_decrypt(hass, encrypted)
    except DecryptionError:
        return "—", account
    return mask_secret(api_key), account


def _parse_settings(
    user_input: dict[str, Any], *, require_acknowledgement: bool
) -> tuple[str | None, str | None, str, list[str] | None, dict[str, str]]:
    errors: dict[str, str] = {}
    base_url: str | None = None
    model: str | None = None
    try:
        base_url = normalize_bridge_base_url(
            str(user_input.get(CONF_BRIDGE_BASE_URL, ""))
        )
    except ValueError:
        errors[CONF_BRIDGE_BASE_URL] = "invalid_url"
    model = parse_model_id(user_input.get(CONF_MODEL))
    if model is None:
        errors[CONF_MODEL] = "invalid_model"
    if require_acknowledgement and not user_input.get(CONF_ACKNOWLEDGE_BRIDGE):
        errors[CONF_ACKNOWLEDGE_BRIDGE] = "bridge_not_acknowledged"
    prompt = str(user_input.get(CONF_PROMPT) or "").strip()
    llm_api = _clean_llm_api(user_input.get(CONF_LLM_HASS_API))
    return base_url, model, prompt, llm_api, errors


def _clean_llm_api(value: Any) -> list[str] | None:
    if not value:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        cleaned = [item for item in value if isinstance(item, str) and item]
        return cleaned or None
    return None


def _settings_schema(
    hass: Any, *, models: list[str], include_acknowledgement: bool
) -> vol.Schema:
    model_options = _ensure_default_model(models) if models else []
    if model_options:
        model_selector: Any = SelectSelector(
            SelectSelectorConfig(
                options=model_options,
                custom_value=True,
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
    else:
        model_selector = str

    fields: dict[Any, Any] = {
        vol.Required(CONF_BRIDGE_BASE_URL, default=DEFAULT_BRIDGE_BASE_URL): str,
        vol.Required(CONF_MODEL, default=DEFAULT_MODEL): model_selector,
    }
    apis = _llm_api_options(hass)
    if apis:
        fields[vol.Optional(CONF_LLM_HASS_API)] = SelectSelector(
            SelectSelectorConfig(
                options=apis,
                multiple=True,
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
    fields[vol.Optional(CONF_PROMPT)] = TextSelector(
        TextSelectorConfig(type=TextSelectorType.TEXT, multiline=True)
    )
    if include_acknowledgement:
        fields[vol.Required(CONF_ACKNOWLEDGE_BRIDGE, default=False)] = bool
    return vol.Schema(fields)


def _connection_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[CONNECTION_OFFICIAL, CONNECTION_COMPATIBLE],
            translation_key="connection_mode",
            mode=SelectSelectorMode.LIST,
        )
    )


def _model_selector(models: list[str]) -> Any:
    if not models:
        return str
    return SelectSelector(
        SelectSelectorConfig(
            options=models,
            custom_value=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _api_key_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_API_KEY): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_CONNECTION_MODE, default=CONNECTION_OFFICIAL
            ): _connection_selector(),
            vol.Optional(CONF_BASE_URL): str,
        }
    )


def _provider_model_schema(hass: Any, models: list[str]) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_CONNECTION_MODE, default=CONNECTION_OFFICIAL
        ): _connection_selector(),
        vol.Optional(CONF_BASE_URL): str,
        vol.Required(CONF_MODEL): _model_selector(models),
    }
    apis = _llm_api_options(hass)
    if apis:
        fields[vol.Optional(CONF_LLM_HASS_API)] = SelectSelector(
            SelectSelectorConfig(
                options=apis,
                multiple=True,
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
    fields[vol.Optional(CONF_PROMPT)] = TextSelector(
        TextSelectorConfig(type=TextSelectorType.TEXT, multiline=True)
    )
    return vol.Schema(fields)


def _llm_api_options(hass: Any) -> list[dict[str, str]]:
    try:
        apis = llm.async_get_apis(hass)
    except Exception:
        _LOGGER.debug("LLM APIs are not available yet")
        return []
    return [{"label": api.name, "value": api.id} for api in apis]
