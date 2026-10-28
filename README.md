[English](README.md) | [中文](README.zh-CN.md)

# Smart LLM

![Smart LLM](images/icon.png)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Release](https://img.shields.io/github/v/release/YyyQq-C/hass-smart-llm?label=release)](https://github.com/YyyQq-C/hass-smart-llm/releases/tag/v1.1.0)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Pluggable conversation agent for Home Assistant Assist. The current release, [v1.1.0](https://github.com/YyyQq-C/hass-smart-llm/releases/tag/v1.1.0), has three paths. Each path is its own conversation entity under Settings → Voice assistants.

- **Cursor** uses browser login and [Cursor Bridge](https://cursorbridge.dev).
- **OpenAI** in the menu is the OpenAI-compatible protocol: `Authorization: Bearer` and chat completions. Official mode calls OpenAI. A custom base URL sends that same request to any host that speaks the API, including Azure OpenAI, OpenRouter, and a local proxy.
- **Anthropic** in the menu is the Anthropic-compatible protocol: `x-api-key`, `anthropic-version`, and the Messages API. Official mode calls Anthropic. A custom base URL sends that same request to a compatible gateway.

The menu keeps the names OpenAI and Anthropic because those names are the protocols. Another vendor works on that menu choice when its API speaks the same style.

The domain is `smart_llm`. The integration manifest version is `1.1.0`.

## Features

- **Cursor.** Browser sign-in uses the same PKCE handshake as the Cursor TypeScript SDK and `agent login`. Home Assistant stores a minted user API key, encrypted on this install. Account screens show a mask such as `y**@g**.com`. Log out or switch account from the integration options. The entry title and the Assist entity stay **Cursor**.
- **OpenAI-compatible (menu: OpenAI).** Paste an API key. Official API sends `Authorization: Bearer` to `https://api.openai.com/v1`. Custom base URL keeps that header and the chat-completions request, and sends them to a host you choose: Azure OpenAI, OpenRouter, a local proxy, or any other OpenAI-compatible service.
- **Anthropic-compatible (menu: Anthropic).** Paste an API key. Official API sends `x-api-key` and `anthropic-version: 2023-06-01` to `https://api.anthropic.com` (`POST /v1/messages`). Custom base URL keeps those headers and sends them to an Anthropic-compatible gateway.
- **Encrypted keys.** Cursor keys and API keys for both protocols are Fernet-encrypted with a key derived from this install (`.storage/core.uuid`). Screens and diagnostics show a mask. Keys are not written to logs.
- One conversation entity per config entry, with optional Home Assistant tools. The Assist name follows the menu label (**Cursor**, **OpenAI**, or **Anthropic**), including when the host behind a custom URL is another vendor.

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

### Update

To install [v1.1.0](https://github.com/YyyQq-C/hass-smart-llm/releases/tag/v1.1.0) or a later release on an existing setup, update inside HACS. Leave the custom repository and the Smart LLM config entries in place.

1. Open HACS → Integrations → **Smart LLM**.
2. When HACS offers a newer version, choose **Update**. To fetch the current release again, open the menu and choose **Redownload**.
3. Restart Home Assistant.

The restart loads the new files. Cursor logins, API keys, and model settings already stored in Home Assistant stay on their config entries.

### Manual

Copy the integration into your configuration directory, then restart Home Assistant. The manifest should land here:

```text
config/custom_components/smart_llm/manifest.json
```

Replace that directory with the new release, then restart, when you update without HACS.

## Authorize Cursor

1. Go to Settings → Devices & services → Add integration → **Smart LLM**.
2. Choose **Cursor**.
3. Open the login URL and approve it on the Cursor portal. The verifier stays on Home Assistant and is not in that URL.
4. Submit. Home Assistant polls until login finishes, then mints a user API key named `Home Assistant Smart LLM` (90 days).
5. Confirm that Cursor Bridge is unofficial, then pick a model. `default` lets Cursor choose.

The browser session token is discarded after minting. Home Assistant stores only the API key, encrypted with a key derived from this install's instance id (`.storage/core.uuid`). Diagnostics and the entity attribute show the mask, such as `crsr_••••••••wxyz`.

If team policy blocks user API keys, login can succeed and minting can still fail. A team admin has to allow user keys.

The same Cursor account cannot be added twice. The device page links to the [Cursor dashboard](https://cursor.com/dashboard).

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

Logging out removes the key from Home Assistant. The key remains valid in the Cursor dashboard until it expires or you revoke it there. The entry then needs authorization again before Assist can use this agent. Switching accounts signs out first, then uses the same browser login as the first setup. Re-authorize still expects the same Cursor account.

## OpenAI-compatible and Anthropic-compatible

Add **Smart LLM** again and choose the protocol. **OpenAI** means the OpenAI-compatible style. **Anthropic** means the Anthropic-compatible style. Each choice is its own config entry. The Assist entity uses that menu label, so a custom host still appears as **OpenAI** or **Anthropic**. The integration entry title includes that label and a key mask.

1. Paste the API key from the service you are calling. It is stored encrypted. Later screens show a mask: the first two characters, eight dots, and the last four characters.
2. Choose official API or a custom base URL (below), then pick a model. If the list is empty, type the model id that host expects. When no list has been loaded, the OpenAI-compatible form suggests `gpt-4o-mini` and the Anthropic-compatible form suggests `claude-sonnet-4-5`.
3. Optionally set Assist tools and extra instructions.

The same API key cannot be added twice for the same menu choice. The device page follows the menu label and opens the [OpenAI API keys](https://platform.openai.com/api-keys) page or the [Anthropic API keys](https://console.anthropic.com/settings/keys) page for that protocol.

### Request styles

v1.1.0 sends API keys with one of two compatible styles. Many vendors speak one of them. Inside each style, official mode calls that protocol's public cloud and ignores a custom URL. Custom base URL keeps the same headers and sends them to your host.

| Protocol (menu label) | Official API | Custom base URL |
| --- | --- | --- |
| OpenAI-compatible (**OpenAI**) | `Authorization: Bearer` against `https://api.openai.com/v1` (`GET /models`, `POST /chat/completions` on that base) | The same Bearer header and chat-completions request, sent to your host: Azure OpenAI, OpenRouter, a local proxy, or any other OpenAI-compatible service |
| Anthropic-compatible (**Anthropic**) | `x-api-key` and `anthropic-version: 2023-06-01` against `https://api.anthropic.com` (`GET /v1/models`, `POST /v1/messages`) | The same `x-api-key` and `anthropic-version` headers and Messages request, sent to an Anthropic-compatible gateway |

A custom URL must be `http` or `https` and must not include a username or password. An OpenAI-compatible paste is normalized so the base ends at `/v1` (`https://openrouter.ai/api/v1/chat/completions` becomes `https://openrouter.ai/api/v1`). An Anthropic-compatible paste is the host; a trailing `/v1` or `/v1/messages` is accepted and requests are still `POST /v1/messages`.

### Options

Open the options on an entry created from **OpenAI** or **Anthropic**. The actions are the same for every host on that protocol.

| Action | What it does |
| --- | --- |
| Model and base URL | Official API or custom base URL, then the model, Assist tools, and extra instructions |
| Refresh models | Request the model list from the configured endpoint |
| Update API key | Replace the stored key. The previous key is overwritten only after the new key is accepted |
| Remove API key | Remove the stored key from Home Assistant |

Remove API key leaves the key valid at the service that issued it. Revoke it there if it should stop working immediately. Cursor actions (re-authorize, switch account, log out) appear only on a Cursor entry.

## Assist setup

1. Go to Settings → Voice assistants → Add assistant, or edit an existing one.
2. Set the conversation agent to the entity named **Cursor**, **OpenAI**, or **Anthropic**. A custom base URL still uses that protocol's menu name.
3. Save, then talk to Assist from the panel or a voice satellite.

Leave **Control Home Assistant** empty for text-only replies. Choose an Assist API there when the model should control devices.

## Cursor Bridge

This section is the Cursor path: browser login plus Bridge. The OpenAI-compatible official API calls `https://api.openai.com/v1`. The Anthropic-compatible official API calls `https://api.anthropic.com`. Other hosts use a custom base URL on the matching menu choice.

Assist does not call an official Cursor chat API. After login, completions go to the Bridge base URL you configure:

```text
https://cursorbridge.dev/v1
```

[Cursor Bridge](https://cursorbridge.dev) is unofficial community software. It is not a Cursor or Home Assistant product.

- Prompts and the API key are sent to that host. Whoever operates the URL can read them.
- Use your own Cursor account, and stay within its plan limits.
- Point the Bridge base URL at another OpenAI-compatible endpoint in the Cursor options if you do not want the default host. That Cursor field is separate from the API-key protocols above.

Browser login still uses Cursor's own portal and `api2.cursor.sh`.

## Provider interface

[v1.1.0](https://github.com/YyyQq-C/hass-smart-llm/releases/tag/v1.1.0) registers three clients: Cursor, an OpenAI-compatible client (menu label **OpenAI**), and an Anthropic-compatible client (menu label **Anthropic**). A service that speaks one of those APIs uses the matching client. Official mode calls that protocol's public cloud. Custom base URL keeps the same headers and calls the host you enter. Another protocol implements `ChatProvider` in `custom_components/smart_llm/provider/base.py`, registers in `provider/registry.py`, and adds its own config-flow step. Cursor keeps the browser login.

## License

MIT. See [LICENSE](LICENSE).
