[English](README.md) | [中文](README.zh-CN.md)

# Smart LLM

![Smart LLM](images/icon.png)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Pluggable conversation agent for Home Assistant Assist. It connects **Cursor**, **OpenAI**, and **Anthropic** through one provider interface.

The domain is `smart_llm`. After setup, the agent is available under Settings → Voice assistants.

## Features

- Cursor sign-in in the browser, using the same PKCE handshake as the Cursor TypeScript SDK and `agent login`.
- A minted user API key, stored encrypted on this Home Assistant install. Screens show a mask such as `crsr_••••••••wxyz`.
- Account addresses are masked in the UI (`yongqc@gmail.com` is shown as `y**@g**.com`). The Assist agent is named **Cursor**, with no email in the name.
- OpenAI and Anthropic API keys. Each one can call the official API, or the same key header against a custom base URL. Screens show a mask such as `sk••••••••wxyz`.
- Model list and Assist replies. Cursor uses an OpenAI-compatible Bridge URL.
- A conversation entity, with optional Home Assistant tools.
- Log out, or switch to another Cursor account, from the integration options.

## Install

Home Assistant **2025.1** or newer. The files in `custom_components/smart_llm/brand/` are the integration icon from Home Assistant **2026.3** onward.

### HACS

This is a HACS **custom** repository. It is not in the default HACS list.

1. Install [HACS](https://hacs.xyz/) if you have not already.
2. Open HACS → Integrations → menu → **Custom repositories**.
3. Add this URL and choose **Integration**:

```text
https://github.com/YyyQq-C/hass-smart-llm
```

4. Download **Smart LLM**, then restart Home Assistant.

You can also add the repository from My Home Assistant when HACS is already installed:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=YyyQq-C&repository=hass-smart-llm&category=integration)

That link only opens this custom repository. It does not mean Smart LLM is in the default HACS store.

### Manual

Copy the integration into your configuration directory, then restart Home Assistant. The manifest should land here:

```text
config/custom_components/smart_llm/manifest.json
```

## Authorize Cursor

1. Go to Settings → Devices & services → Add integration → **Smart LLM**.
2. Choose **Cursor**.
3. Open the login URL and approve it on the Cursor portal. The verifier stays on Home Assistant and is not in that URL.
4. Submit. Home Assistant polls until login finishes, then mints a user API key named `Home Assistant Smart LLM` (90 days).
5. Confirm that Cursor Bridge is unofficial, then pick a model. `default` lets Cursor choose.

The browser session token is discarded after minting. Home Assistant stores only the API key, encrypted with a key derived from this install's instance id (`.storage/core.uuid`). Diagnostics and the entity attribute show the mask.

If team policy blocks user API keys, login can succeed and minting can still fail. A team admin has to allow user keys.

### Options

Open the integration options to change how Assist calls Cursor.

| Action | What it does |
| --- | --- |
| Model and Bridge URL | Base URL, model, Assist tools, and extra instructions |
| Refresh models | Request `GET /v1/models` |
| Re-authorize | Run browser login again and replace the stored key for the same account |
| Switch account | Remove the stored key, run browser login, and link a different Cursor account. The model list is refreshed after the new key is saved |
| Log out | Remove the key and the stored account address from Home Assistant |

The options screens show the account as a mask such as `y**@g**.com`, never the full address. The voice assistant card and the integration title stay **Cursor**.

Logging out does not revoke the key in the Cursor dashboard. Revoke it there if it should stop working immediately. The entry then needs authorization again before Assist can use this agent. Switching accounts signs out first, then uses the same browser login as the first setup. Re-authorize still expects the same Cursor account.

## Add OpenAI

1. Add the Smart LLM integration and choose **OpenAI**.
2. Paste an API key. It is encrypted with the same install-bound Fernet key as a Cursor key. The form shows a mask after setup.
3. Choose a request style:
   - **Official API (key in header).** Requests go to `https://api.openai.com/v1` with `Authorization: Bearer`.
   - **Custom base URL.** The same `Authorization: Bearer` header is sent to a base URL you enter. Use this for Azure OpenAI, OpenRouter, or a local OpenAI-compatible proxy. Include the `/v1` prefix when the host path is not empty, for example `https://openrouter.ai/api/v1`.
4. Pick a model. If the model list cannot be loaded, type a model id.

Options can change the request style, base URL, and model, replace the key, or remove it from Home Assistant. Removing the key does not revoke it at OpenAI.

## Add Anthropic

1. Add the integration and choose **Anthropic**.
2. Paste an API key. Storage and masking match OpenAI.
3. Choose a request style:
   - **Official API (key in header).** Requests go to `https://api.anthropic.com` with `x-api-key` and `anthropic-version`. Chat uses `POST /v1/messages`.
   - **Custom base URL.** The same headers are sent to an Anthropic-compatible gateway. Paste the host root; a trailing `/v1` is removed.
4. Pick a model.

An OpenAI-compatible Claude proxy belongs on the OpenAI provider with a custom base URL. The Anthropic provider speaks the Messages API.

Options can change the request style, base URL, and model, replace the key, or remove it. Removing the key does not revoke it in the Anthropic console.

## Assist setup

1. Go to Settings → Voice assistants → Add assistant, or edit an existing one.
2. Set the conversation agent to the entity this integration created. Cursor, OpenAI, and Anthropic each get their own entity.
3. Save, then talk to Assist from the panel or a voice satellite.

Leave **Control Home Assistant** empty for text-only replies. Choose an Assist API there when the model should control devices.

## Cursor Bridge

Assist does not call an official Cursor chat API. After login, completions go to the Bridge base URL you configure:

```text
https://cursorbridge.dev/v1
```

[Cursor Bridge](https://cursorbridge.dev) is unofficial community software. It is not a Cursor or Home Assistant product.

- Prompts and the API key are sent to that host. Whoever operates the URL can read them.
- Use your own Cursor account, and stay within its plan limits.
- Point the base URL at another OpenAI-compatible endpoint in the integration options if you do not want the default host.

Browser login still uses Cursor's own portal and `api2.cursor.sh`.

## Provider extensibility

Cursor, OpenAI, and Anthropic are registered in `provider/registry.py`. Another provider implements `ChatProvider` in `custom_components/smart_llm/provider/base.py`, registers there, and adds a config-flow step for its own sign-in. Do not reuse the Cursor browser login for a provider that expects a pasted API key.

## License

MIT. See [LICENSE](LICENSE).
