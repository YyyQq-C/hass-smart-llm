"""Conversation agent that serves Home Assistant Assist."""

from __future__ import annotations

import logging
from typing import Any, Literal

from homeassistant.components import conversation
from homeassistant.components.conversation import ConversationEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import intent, llm
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    AGENT_NAME,
    CONF_CONNECTION_MODE,
    CONF_MODEL,
    CONF_PROVIDER,
    CONNECTION_OFFICIAL,
    DOMAIN,
    MAX_TOOL_ITERATIONS,
    PROVIDER_CONFIG_URL,
    PROVIDER_CURSOR,
    PROVIDER_LABELS,
    default_model_for,
)
from .provider.base import ChatResponse
from .provider.errors import ProviderAPIError, ProviderAuthError
from .provider.messages import function_tool, openai_messages_from_contents

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

_MESSAGES = {
    "en": {
        "auth": "Smart LLM needs you to authorize Cursor again.",
        "auth_api": "Smart LLM rejected the API key. Enter a new key in the integration options.",
        "api": "The model request failed: {detail}",
        "empty": "The model returned an empty response.",
        "tools": "The model could not finish the Home Assistant actions.",
        "setup": "Smart LLM is not ready.",
    },
    "zh": {
        "auth": "Smart LLM 需要你重新授权 Cursor。",
        "auth_api": "Smart LLM 拒绝了这把 API 密钥。请在集成选项里填写新密钥。",
        "api": "模型请求失败：{detail}",
        "empty": "模型返回了空回复。",
        "tools": "模型没能完成 Home Assistant 操作。",
        "setup": "Smart LLM 还没有准备好。",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Smart LLM conversation entity."""
    async_add_entities([SmartLLMConversationEntity(entry)])


class SmartLLMConversationEntity(conversation.ConversationEntity):
    """Assist agent backed by the configured provider."""

    _attr_has_entity_name = False
    _attr_supported_features = ConversationEntityFeature(0)

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the agent from a config entry."""
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        provider = entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR)
        # Older Cursor titles embedded the email, so that agent stays generic.
        if provider == PROVIDER_CURSOR:
            self._attr_name = AGENT_NAME
        else:
            self._attr_name = PROVIDER_LABELS.get(provider, provider)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=self._attr_name,
            manufacturer="Smart LLM",
            model=PROVIDER_LABELS.get(provider, provider),
            configuration_url=PROVIDER_CONFIG_URL.get(provider),
        )
        if entry.options.get(CONF_LLM_HASS_API):
            self._attr_supported_features = ConversationEntityFeature.CONTROL

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """LLMs are not limited to one language."""
        return MATCH_ALL

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose non-secret settings. The API key is masked."""
        runtime = self._entry.runtime_data
        provider = self._entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR)
        attributes: dict[str, Any] = {
            "provider": provider,
            "model": self._entry.options.get(CONF_MODEL, default_model_for(provider)),
            "base_url": runtime.base_url,
            "api_key_masked": runtime.masked_key,
        }
        if provider == PROVIDER_CURSOR:
            attributes["bridge_base_url"] = runtime.base_url
        else:
            attributes["connection_mode"] = self._entry.options.get(
                CONF_CONNECTION_MODE, CONNECTION_OFFICIAL
            )
        return attributes

    async def async_added_to_hass(self) -> None:
        """Register this entity as an Assist agent."""
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self._entry, self)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the Assist agent."""
        conversation.async_unset_agent(self.hass, self._entry)
        await super().async_will_remove_from_hass()

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Send the chat log to the provider and speak the reply."""
        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                self._entry.options.get(CONF_LLM_HASS_API),
                self._entry.options.get(CONF_PROMPT),
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()
        except HomeAssistantError as err:
            _LOGGER.debug("Unable to prepare Assist context: %s", err)
            return _failure(user_input, "setup")

        runtime = getattr(self._entry, "runtime_data", None)
        if runtime is None:
            return _failure(user_input, "setup")

        provider = self._entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR)
        model = self._entry.options.get(CONF_MODEL, default_model_for(provider))
        try:
            for _iteration in range(MAX_TOOL_ITERATIONS):
                messages = openai_messages_from_contents(chat_log.content)
                tools = _tools_payload(chat_log.llm_api)
                response = await runtime.provider.async_chat(
                    model=model,
                    messages=messages,
                    tools=tools,
                )
                if not await _async_record_response(
                    chat_log, user_input.agent_id or self.entity_id, response
                ):
                    if response.tool_calls and chat_log.llm_api is None:
                        return _failure(user_input, "tools")
                    return _failure(user_input, "empty")
                if not response.tool_calls or not chat_log.unresponded_tool_results:
                    break
            else:
                if chat_log.unresponded_tool_results:
                    return _failure(user_input, "tools")
        except ProviderAuthError:
            provider = self._entry.data.get(CONF_PROVIDER, PROVIDER_CURSOR)
            if provider == PROVIDER_CURSOR:
                _LOGGER.warning("Cursor rejected the stored API key")
                auth_key = "auth"
            else:
                _LOGGER.warning(
                    "The provider rejected the stored API key (provider=%s)",
                    provider,
                )
                auth_key = "auth_api"
            _start_reauth_once(self.hass, self._entry)
            return _failure(user_input, auth_key)
        except ProviderAPIError as err:
            _LOGGER.warning("Model request failed (HTTP %s)", err.status)
            return _failure(user_input, "api", detail=str(err))

        return conversation.async_get_result_from_chat_log(user_input, chat_log)


async def _async_record_response(
    chat_log: conversation.ChatLog,
    agent_id: str,
    response: ChatResponse,
) -> bool:
    """Append the model turn. Return False when there is nothing to record."""
    content = response.content.strip() if isinstance(response.content, str) else None
    if content == "":
        content = None
    tool_calls = None
    if response.tool_calls and chat_log.llm_api is not None:
        tool_calls = [
            llm.ToolInput(id=call.id, tool_name=call.name, tool_args=call.arguments)
            for call in response.tool_calls
        ]
    if content is None and not tool_calls:
        return False
    assistant = conversation.AssistantContent(
        agent_id=agent_id,
        content=content,
        tool_calls=tool_calls,
    )
    async for _item in chat_log.async_add_assistant_content(assistant):
        pass
    return True


def _tools_payload(llm_api: llm.APIInstance | None) -> list[dict[str, Any]] | None:
    if llm_api is None or not llm_api.tools:
        return None
    payload: list[dict[str, Any]] = []
    for tool in llm_api.tools:
        try:
            parameters = _parameters(tool.parameters, llm_api.custom_serializer)
        except Exception:
            _LOGGER.warning("Skipping tool %s because its schema did not convert", tool.name)
            continue
        payload.append(function_tool(tool.name, tool.description, parameters))
    return payload or None


def _parameters(schema: Any, custom_serializer: Any) -> dict[str, Any]:
    if isinstance(schema, dict):
        return schema
    try:
        import probatio

        to_openapi = getattr(probatio, "to_openapi", None)
        if to_openapi is not None:
            kwargs: dict[str, Any] = {}
            if custom_serializer is not None:
                kwargs["custom_serializer"] = custom_serializer
            try:
                converted = to_openapi(schema, openapi_version="3.0.3", **kwargs)
            except TypeError:
                converted = to_openapi(schema, **kwargs)
            if isinstance(converted, dict):
                return converted
    except ImportError:
        pass
    try:
        from voluptuous_openapi import convert

        converted = convert(schema, custom_serializer=custom_serializer)
        if isinstance(converted, dict):
            return converted
    except ImportError:
        pass
    raise RuntimeError("No schema converter is available")


def _failure(
    user_input: conversation.ConversationInput,
    key: str,
    *,
    detail: str | None = None,
) -> conversation.ConversationResult:
    language = _language(user_input.language)
    template = _MESSAGES[language][key]
    message = template.format(detail=(detail or "")[:200])
    response = intent.IntentResponse(language=user_input.language)
    response.async_set_error(intent.IntentResponseErrorCode.FAILED_TO_HANDLE, message)
    return conversation.ConversationResult(
        response=response,
        conversation_id=user_input.conversation_id,
    )


def _language(language: str | None) -> str:
    if language and language.lower().startswith("zh"):
        return "zh"
    return "en"


def _start_reauth_once(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Start a reauth flow unless one is already in progress for this entry."""
    from homeassistant.config_entries import SOURCE_REAUTH

    for flow in hass.config_entries.flow.async_progress():
        context = flow.get("context") or {}
        if (
            context.get("source") == SOURCE_REAUTH
            and context.get("entry_id") == entry.entry_id
        ):
            return
    entry.async_start_reauth(hass)
