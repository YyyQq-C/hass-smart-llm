"""Config and options flows for Smart LLM."""

from __future__ import annotations

import asyncio
import logging
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
    CONF_ACKNOWLEDGE_BRIDGE,
    CONF_API_KEY_ENCRYPTED,
    CONF_API_KEY_EXPIRES_AT,
    CONF_AVAILABLE_MODELS,
    CONF_BRIDGE_BASE_URL,
    CONF_EMAIL,
    CONF_MODEL,
    CONF_PROVIDER,
    DEFAULT_BRIDGE_BASE_URL,
    DEFAULT_MODEL,
    DOMAIN,
    PROVIDER_CURSOR,
)
from .crypto import DecryptionError, mask_secret
from .identity import account_unique_id, same_cursor_account
from .provider.cursor_auth import (
    LoginHandshake,
    LoginResult,
    async_login_and_mint,
    create_login_handshake,
)
from .provider.cursor_bridge import CursorBridgeClient, normalize_bridge_base_url
from .provider.errors import CursorAPIError, CursorAuthError, CursorLoginError
from .provider.registry import provider_menu_options
from .secrets import async_decrypt, async_encrypt

_LOGGER = logging.getLogger(__name__)


def _entry_title(email: str | None) -> str:
    if email:
        return f"Cursor ({email})"
    return "Cursor"


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
            step_id="cursor_link",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "login_url",
                        description={"suggested_value": login_url},
                    ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
                }
            ),
            description_placeholders={"login_url": login_url},
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


class SmartLLMConfigFlow(ConfigFlow, _CursorBrowserLogin, domain=DOMAIN):
    """Walk the user through provider choice, Cursor login, and model selection."""

    VERSION = 1

    _models: list[str] | None = None
    _listed_base: str | None = None
    _model_error: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a provider. Version 1 offers Cursor."""
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
        """Start a new browser login for an existing entry."""
        return await self.async_step_cursor_link()

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
                "account": result.email or "Cursor",
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
        except (CursorAPIError, ValueError):
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
        return self.async_create_entry(title=_entry_title(result.email), data=data, options=options)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SmartLLMOptionsFlow:
        """Return the options flow."""
        return SmartLLMOptionsFlow()


class SmartLLMOptionsFlow(OptionsFlow, _CursorBrowserLogin):
    """Change the model, refresh Bridge models, re-authorize, or log out."""

    _refresh_task: asyncio.Task[None] | None = None
    _refreshed_models: list[str] | None = None
    _refresh_error: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show what is stored, without revealing the API key."""
        masked, account = await _identity(self.hass, self.config_entry)
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "refresh_models", "reauth", "logout"],
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
        """Fetch ``GET /v1/models`` and then return to the settings form."""
        if not self.config_entry.data.get(CONF_API_KEY_ENCRYPTED):
            return self.async_abort(reason="logged_out")
        if self._refresh_task is None:
            self._refresh_task = self.hass.async_create_task(self._async_refresh_models())
        if not self._refresh_task.done():
            return self.async_show_progress(
                step_id="refresh_models",
                progress_action="refresh_models",
                progress_task=self._refresh_task,
            )
        return self.async_show_progress_done(next_step_id="settings")

    async def _async_refresh_models(self) -> None:
        try:
            api_key = await async_decrypt(
                self.hass, self.config_entry.data[CONF_API_KEY_ENCRYPTED]
            )
            base_url = self.config_entry.options.get(
                CONF_BRIDGE_BASE_URL, DEFAULT_BRIDGE_BASE_URL
            )
            client = CursorBridgeClient(
                async_get_clientsession(self.hass),
                api_key=api_key,
                base_url=base_url,
            )
            self._refreshed_models = _ensure_default_model(await client.async_list_models())
            self._refresh_error = None
        except (CursorAuthError, DecryptionError):
            self._refresh_error = "invalid_auth"
        except (CursorAPIError, ValueError):
            self._refresh_error = "cannot_connect"
        except Exception:
            self._refresh_error = "unknown"
            _LOGGER.exception("Refreshing Cursor Bridge models failed")

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Mint a new API key with the browser login."""
        return await self.async_step_cursor_link()

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
        data = dict(self.config_entry.data)
        data.pop(CONF_API_KEY_ENCRYPTED, None)
        data.pop(CONF_API_KEY_EXPIRES_AT, None)
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)
        return self.async_abort(reason="logged_out")

    async def _async_login_succeeded(self) -> ConfigFlowResult:
        return await _async_save_credentials(self, self.config_entry)


async def _async_save_credentials(flow: Any, entry: ConfigEntry) -> ConfigFlowResult:
    """Write a new encrypted API key onto an existing entry."""
    result: LoginResult | None = flow._login_result
    if result is None:
        return flow.async_abort(reason="unknown")
    if not same_cursor_account(entry.unique_id, result.email):
        return flow.async_abort(reason="wrong_account")
    new_unique_id = (
        account_unique_id(result.email, result.api_key)
        if result.email
        else entry.unique_id
    )
    if new_unique_id:
        for other in flow.hass.config_entries.async_entries(DOMAIN):
            if other.entry_id != entry.entry_id and other.unique_id == new_unique_id:
                return flow.async_abort(reason="already_configured")
    data = dict(entry.data)
    data.update(await _credential_data(flow.hass, result))
    was_loaded = entry.state is ConfigEntryState.LOADED
    flow.hass.config_entries.async_update_entry(
        entry,
        data=data,
        unique_id=new_unique_id,
        title=_entry_title(result.email or entry.data.get(CONF_EMAIL)),
    )
    if not was_loaded:
        await flow.hass.config_entries.async_reload(entry.entry_id)
    return flow.async_abort(reason="reauth_successful")


async def _credential_data(hass: Any, result: LoginResult) -> dict[str, Any]:
    data: dict[str, Any] = {
        CONF_PROVIDER: PROVIDER_CURSOR,
        CONF_API_KEY_ENCRYPTED: await async_encrypt(hass, result.api_key),
        CONF_API_KEY_EXPIRES_AT: result.expires_at_ms,
    }
    if result.email:
        data[CONF_EMAIL] = result.email
    return data


async def _identity(hass: Any, entry: ConfigEntry) -> tuple[str, str]:
    encrypted = entry.data.get(CONF_API_KEY_ENCRYPTED)
    email = entry.data.get(CONF_EMAIL)
    account = email or "Cursor"
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
    raw_model = str(user_input.get(CONF_MODEL, "")).strip()
    if not raw_model or any(char.isspace() for char in raw_model):
        errors[CONF_MODEL] = "invalid_model"
    else:
        model = raw_model
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


def _llm_api_options(hass: Any) -> list[dict[str, str]]:
    try:
        apis = llm.async_get_apis(hass)
    except Exception:
        _LOGGER.debug("LLM APIs are not available yet")
        return []
    return [{"label": api.name, "value": api.id} for api in apis]
