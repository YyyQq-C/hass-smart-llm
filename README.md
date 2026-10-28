<div align="center">

[English](README.md) | [中文](README.zh-CN.md)

# Smart LLM

![Smart LLM](images/icon.png)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Release](https://img.shields.io/github/v/release/YyyQq-C/hass-smart-llm?label=release)](https://github.com/YyyQq-C/hass-smart-llm/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

Pluggable conversation agent for Home Assistant Assist. Three paths each become their own conversation entity under Settings → Voice assistants.

- **Cursor** uses browser login and [Cursor Bridge](https://cursorbridge.dev). A Cursor entry also adds allowance sensors when Cursor returns the current billing period.
- **OpenAI** in the menu is the OpenAI-compatible protocol: chat completions, and `Authorization: Bearer` when a key is set. Official mode calls OpenAI and requires a key. A custom base URL sends that same request to any host that speaks the API, including Azure OpenAI, OpenRouter, Ollama, vLLM, LM Studio, and LocalAI. The key is optional on that custom URL. An empty key omits `Authorization`.
- **Anthropic** in the menu is the Anthropic-compatible protocol: `x-api-key`, `anthropic-version`, and the Messages API. Official mode calls Anthropic. A custom base URL sends that same request to a compatible gateway. Anthropic still requires a key.

The menu keeps the names OpenAI and Anthropic because those names are the protocols. Another vendor works on that menu choice when its API speaks the same style. There is no separate Ollama protocol.

The domain is `smart_llm`.

## Features

- **Cursor.** Browser sign-in uses the same PKCE handshake as the Cursor TypeScript SDK and `agent login`. Home Assistant stores a minted user API key, encrypted on this install. The login step chooses 30, 90, 180, or 365 days, or a permanent key. Account screens show a mask such as `y**@g**.com`. Log out or switch account from the integration options. The entry title and the Assist entity stay **Cursor**.
- **OpenAI-compatible (menu: OpenAI).** Paste an API key, or leave it empty for a local server that does not check one. Official API sends `Authorization: Bearer` to `https://api.openai.com/v1` and still requires a key. Custom base URL sends the chat-completions request to a host you choose: Azure OpenAI, OpenRouter, Ollama, vLLM, LM Studio, LocalAI, or any other OpenAI-compatible service. A key, when present, is sent as `Authorization: Bearer`. An empty key omits that header.
- **Cursor allowance.** For a Cursor entry, sensors show included usage still left, the percent Cursor reports, and when the billing period ends. See [Cursor allowance](#cursor-allowance).
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

To install a published release on an existing setup, update inside HACS. Leave the custom repository and the Smart LLM config entries in place. The manifest version in this tree is `1.3.0`. A GitHub release is published separately.

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
4. Choose a key lifetime: 30, 90 (the default), 180, or 365 days, or permanent. Submit. Home Assistant polls until login finishes, then mints a user API key named `Home Assistant Smart LLM`. A finite choice sends `expiresAt` to Cursor. Permanent omits that field, which is how Cursor's API mints a key with no expiry.
5. Confirm that Cursor Bridge is unofficial, then pick a model. `default` lets Cursor choose.

The browser session token is discarded after minting. Home Assistant stores the API key, encrypted with a key derived from this install's instance id (`.storage/core.uuid`), and stores the expiry you chose (or never) on the config entry. Diagnostics and the entity attribute show the mask, such as `crsr_••••••••wxyz`. The expiry is not a secret.

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

Logging out removes the key from Home Assistant. The key remains valid in the Cursor dashboard until it expires or you revoke it there. The entry then needs authorization again before Assist can use this agent. Switching accounts signs out first, then uses the same browser login as the first setup, including the lifetime choice. Re-authorize still expects the same Cursor account and asks for a lifetime again.

### Key expiry

Finite keys are checked while the entry is loaded. About 7 days before the stored expiry, Home Assistant raises a repair and a persistent notification. When the key expires, that notice is updated, Assist replies that you need to re-authorize, and the allowance sensors become unavailable. Use the repair, or open the integration options and choose Re-authorize. The same notice is not repeated on every refresh. A permanent key has no expiry reminder. An older entry that never stored an expiry is left alone, so it is not marked expired.

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
| OpenAI-compatible (**OpenAI**) | `Authorization: Bearer` against `https://api.openai.com/v1` (`GET /models`, `POST /chat/completions` on that base). A key is required | The same chat-completions request, sent to your host: Azure OpenAI, OpenRouter, Ollama, vLLM, LM Studio, LocalAI, or any other OpenAI-compatible service. The key is optional. When it is empty, `Authorization` is omitted |
| Anthropic-compatible (**Anthropic**) | `x-api-key` and `anthropic-version: 2023-06-01` against `https://api.anthropic.com` (`GET /v1/models`, `POST /v1/messages`) | The same `x-api-key` and `anthropic-version` headers and Messages request, sent to an Anthropic-compatible gateway |

A custom URL must be `http` or `https` and must not include a username or password. An OpenAI-compatible paste drops a trailing `/chat/completions` or `/models`. A host with no path gets `/v1` (`https://openrouter.ai/api/v1/chat/completions` becomes `https://openrouter.ai/api/v1`; `https://api.deepseek.com` becomes `https://api.deepseek.com/v1`). A longer path is kept, including `https://open.bigmodel.cn/api/paas/v4` and `https://dashscope.aliyuncs.com/compatible-mode/v1`. A local `http://…/v1` base keeps `http`. An Anthropic-compatible paste is the host; a trailing `/v1` or `/v1/messages` is accepted and requests are still `POST /v1/messages`.

### Local servers (Ollama, vLLM, and others)

Ollama, vLLM, LM Studio, and LocalAI speak the OpenAI chat API. Use the **OpenAI** menu. Do not look for a separate Ollama integration inside Smart LLM.

1. Add **Smart LLM** and choose **OpenAI**.
2. Leave the API key empty when the server does not require one. Ollama's default OpenAI endpoint does not. If the server expects a dummy key, paste it; Smart LLM then sends `Authorization: Bearer`.
3. Choose **Custom base URL**.
4. Enter the server's `/v1` base:

   | Server | Usual base |
   | --- | --- |
   | Ollama | `http://HOST:11434/v1` |
   | vLLM OpenAI server | `http://HOST:8000/v1` |
   | LM Studio | `http://HOST:1234/v1` |
   | LocalAI | `http://HOST:8080/v1` |

   Ports are the usual defaults. Use the port that server is actually listening on.
5. Pick a model from the list, or type the name the server expects (`llama3.2`, the vLLM model id, and so on).

Home Assistant in Docker does not see a server on the host through `localhost`. Inside the container, `localhost` is the container. Use the host's LAN address, such as `http://192.168.1.20:11434/v1`, or `http://host.docker.internal:11434/v1` when that name resolves to the host (Docker Desktop does this). On Linux Docker, `host.docker.internal` exists only if the container is started with that host mapping.

The official OpenAI endpoint still rejects an empty key. An empty key is accepted only for an OpenAI-compatible custom base URL.

### Cloud vendors (OpenAI-compatible)

These hosts speak the OpenAI chat API. Choose **OpenAI** in the menu, paste that vendor's API key, choose **Custom base URL**, and enter the base. These cloud APIs require a key. Leave the key empty only for a local server that does not check one.

| Vendor | Base URL (OpenAI-compatible) | Example models |
| --- | --- | --- |
| Alibaba Cloud Model Studio / Qwen (Beijing) | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus`, `qwen-max` |
| Moonshot Kimi (China) | `https://api.moonshot.cn/v1` | `kimi-k3`, `kimi-k2.6` |
| Moonshot Kimi (International) | `https://api.moonshot.ai/v1` | `kimi-k3`, `kimi-k2.6` |
| Zhipu GLM | `https://open.bigmodel.cn/api/paas/v4/` | `glm-5.3`, `glm-4.7-flash` |
| DeepSeek | `https://api.deepseek.com` (`https://api.deepseek.com/v1` is also accepted) | `deepseek-flash`, `deepseek-v4-pro` |

- DashScope keys are regional and do not work across regions. The Beijing row is the shared domain and needs a Beijing key. Singapore uses `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`. US (Virginia) uses `https://dashscope-us.aliyuncs.com/compatible-mode/v1`.
- Moonshot China (`api.moonshot.cn`, keys from [platform.kimi.com](https://platform.kimi.com)) and Moonshot International (`api.moonshot.ai`, keys from [platform.kimi.ai](https://platform.kimi.ai)) use the same model family. Keys from the two platforms are not interchangeable.
- Zhipu's current OpenAI-compatible chat docs use `glm-5.3` and `glm-4.7-flash`. DeepSeek's current docs use `deepseek-flash` and `deepseek-v4-pro`. Both DeepSeek bases above work; a paste with no path is stored with `/v1` appended.
- Base URLs and model ids change. Check the vendor's docs before relying on a name in this table.
- A gateway that speaks the Anthropic Messages API stays on the **Anthropic** menu. That includes a vendor's Anthropic-compatible base, such as DashScope `/apps/anthropic`, Kimi `/anthropic`, or `https://api.deepseek.com/anthropic`.
- Home Assistant in Docker, and `localhost` for a server on the host, are covered under [Local servers](#local-servers-ollama-vllm-and-others). These cloud URLs are public HTTPS endpoints.

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

## Cursor allowance

Cursor Bridge does not publish a quota endpoint. Its documented routes are chat completions, the Responses API, Anthropic messages, token counting, and the model list. This integration does not invent a remaining balance from those calls.

The Cursor dashboard pages under `cursor.com/api/` need the browser session cookie. Smart LLM discards that session after it mints the user API key, so those cookie routes are not called.

For a Cursor entry, Smart LLM asks Cursor for the current billing period with the stored user API key:

1. `POST https://api2.cursor.sh/auth/exchange_user_api_key` with `Authorization: Bearer` set to the user API key. The response access token is kept in memory only. It is not written to the config entry, diagnostics, or logs.
2. `POST https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage` with that access token and `Connect-Protocol-Version: 1`.

That is the same unofficial Connect API the login flow already uses to mint a key (`CreateUserApiKey`, `GetMe`). Cursor can change it. Sensors refresh about every 30 minutes. If a field is missing, that sensor stays unknown. If the call fails, the sensors are unavailable and Assist chat is left alone.

| Sensor | Source |
| --- | --- |
| Included usage remaining | `planUsage.remaining`, US cents divided by 100, shown as USD. The raw cents value is an attribute |
| Included usage used | `planUsage.totalPercentUsed`, copied as Cursor returned it |
| Allowance resets | `billingCycleEnd`, Unix milliseconds, shown as a timestamp |

`planUsage.limit`, spend, and `displayMessage` are attributes on the remaining sensor. They are copied from the response. OpenAI, Anthropic, and local servers do not get these sensors. Those APIs do not return a subscription allowance here, and this integration does not count requests locally as a stand-in for quota.

## Provider interface

Smart LLM registers three clients: Cursor, an OpenAI-compatible client (menu label **OpenAI**), and an Anthropic-compatible client (menu label **Anthropic**). A service that speaks one of those APIs uses the matching client. Official mode calls that protocol's public cloud. Custom base URL keeps the same request style and calls the host you enter. An OpenAI-compatible custom base URL may omit the API key. Another protocol implements `ChatProvider` in `custom_components/smart_llm/provider/base.py`, registers in `provider/registry.py`, and adds its own config-flow step. Cursor keeps the browser login.

## License

MIT. See [LICENSE](LICENSE).
