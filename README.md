# Smart LLM

Home Assistant Assist 的可插拔多提供方对话代理。当前版本只接入 **Cursor**，结构上可以再加 OpenAI、Claude 等提供方。

集成域名是 `smart_llm`，显示名称是 **Smart LLM**。它在「设置 → 语音助手」里注册一个对话代理。

## 重要说明：Cursor Bridge 是非官方服务

对话请求**不会**直接发给 Cursor 官方的 Assist 接口。授权完成后，集成用签出来的 Cursor 用户 API 密钥，去调用你配置的 **Cursor Bridge**（默认 `https://cursorbridge.dev/v1`）。

[Cursor Bridge](https://cursorbridge.dev) 是社区做的 OpenAI 兼容转发，不是 Cursor 或 Home Assistant 的官方产品。

- 提示词和 API 密钥会送到你填写的 Bridge 基础 URL。该地址的运营者可以看到这些内容。
- 请使用你自己的 Cursor 账号，并遵守该账号的套餐限制。
- 默认地址或接口以后可能变化。可以在选项里改基础 URL。

浏览器登录本身走的是 Cursor 官方门户和 `api2.cursor.sh`，步骤与 Cursor TypeScript SDK / CLI 的 `agent login` 相同。

## 功能

- 提供方可插拔。v1 只有 Cursor。
- 浏览器授权：PKCE 式握手 → 打开 `https://cursor.com/loginDeepControl` → `POST /auth/poll`（校验码在 JSON 正文里，不在 URL 里）→ 用一次性会话令牌调用 Dashboard `CreateUserApiKey`。
- 会话令牌用完即丢。Home Assistant 只保存签出的用户 API 密钥，并用本机实例 ID 做 Fernet 加密。界面只显示掩码，例如 `crsr_••••••••wxyz`。
- 用这把密钥调用 Bridge 的 `GET /v1/models` 和 `POST /v1/chat/completions`。
- 选项里可以刷新模型、选择当前模型、修改 Bridge 基础 URL、重新授权或退出登录。
- 可选接入 Home Assistant 的 LLM 工具，让 Assist 控制设备。

## 用 HACS 安装

1. 安装 [HACS](https://hacs.xyz/)。
2. 打开 HACS → 集成 → 右上角菜单 → 自定义存储库。
3. 添加 `https://github.com/YyyQq-C/hass-smart-llm`，类型选 **Integration**。
4. 下载 **Smart LLM**。
5. 重启 Home Assistant。

要求 Home Assistant **2025.1.0** 或更新版本。

## 手动安装

把 `custom_components/smart_llm` 复制到 Home Assistant 配置目录的 `custom_components/smart_llm`，然后重启。

## 授权 Cursor

1. 设置 → 设备与服务 → 添加集成 → **Smart LLM**。
2. 选择 **Cursor**。
3. 打开页面上的登录网址，在 Cursor 门户里批准。校验码不会出现在这个网址里。
4. 回到 Home Assistant 提交，集成会轮询直到登录完成，然后签发一把名为 `Home Assistant Smart LLM` 的用户 API 密钥（默认 90 天）。
5. 确认你了解 Cursor Bridge 是非官方服务，再选择模型。`default` 表示交给 Cursor 选择。

密钥加密后写入配置项。诊断信息和实体属性里也只有掩码。

如果团队策略禁止用户 API 密钥，登录会成功但签发失败。需要团队管理员放开，或等以后的提供方直接填写已有密钥。

## 接到 Assist

1. 设置 → 语音助手 → 添加助手（或编辑现有助手）。
2. 对话代理选这个集成创建的 **Cursor** 实体（名称里带账号邮箱）。
3. 保存后，用 Assist 面板或语音卫星说话即可。

选项里的「控制 Home Assistant」会把所选的 Assist 工具交给模型。不选的话，代理只回答文字，不调用设备。

## 选项

配置项的选项菜单：

| 操作 | 作用 |
| --- | --- |
| 模型与 Bridge URL | 修改基础 URL、当前模型、Assist 工具和补充说明 |
| 刷新模型列表 | 手动请求 `GET /v1/models` |
| 重新授权 | 再走一次浏览器登录，替换已保存的密钥 |
| 退出登录 | 从 Home Assistant 删除密钥。Cursor 控制台里的密钥在过期或被你撤销之前仍然有效 |

退出之后需要重新授权，Assist 才能继续用这个代理。

## 密钥怎么保存

加密密钥来自这套 Home Assistant 的实例 ID（`.storage/core.uuid`）。只拷走配置项文件看不到明文密钥。整份配置目录备份里包含实例 ID，因此可以解密，这和 Home Assistant 其他本地数据的边界一致。

请不要把 `.storage` 提交到 git，也不要在 issue 里粘贴诊断原文以外的密钥。

## 开发

```bash
pip install pytest aiohttp cryptography
pytest
```

测试不访问 Cursor 或 Cursor Bridge，只用本地 mock。

新增提供方时：实现 `custom_components/smart_llm/provider/base.py` 里的 `ChatProvider`，在 `provider/registry.py` 注册，并在配置流向导里加上该提供方自己的认证步骤。Cursor 的浏览器登录不要复用到需要用户粘贴密钥的提供方上。

## 许可

MIT。见 [LICENSE](LICENSE)。

---

# Smart LLM (English)

Pluggable multi-provider conversation agent for Home Assistant Assist. Version 1 ships **Cursor** only. The layout can take OpenAI, Claude, and other providers later.

Domain: `smart_llm`. Display name: **Smart LLM**. It registers a conversation agent under Settings → Voice assistants.

## Cursor Bridge is unofficial

Chat requests are **not** sent to an official Cursor Assist API. After authorization, the integration calls the **Cursor Bridge** base URL you configure (default `https://cursorbridge.dev/v1`) with a Cursor user API key.

[Cursor Bridge](https://cursorbridge.dev) is a community OpenAI-compatible proxy. It is not a Cursor or Home Assistant product.

- Prompts and the API key are sent to whatever Bridge base URL you set. Whoever operates that URL can see them.
- Use your own Cursor account and stay within its plan limits.
- The default host or paths may change. The base URL is editable in options.

The browser login itself uses Cursor's portal and `api2.cursor.sh`, the same PKCE-style handshake as the Cursor TypeScript SDK and the CLI `agent login`.

## What it does

- Pluggable providers. v1 registers Cursor.
- Browser auth: PKCE-style handshake → open `https://cursor.com/loginDeepControl` → `POST /auth/poll` with the verifier in the JSON body, not the URL → one-time session token calls Dashboard `CreateUserApiKey`.
- The session token is discarded. Home Assistant stores only the minted user API key, encrypted with Fernet using this install's instance id. The UI shows a masked key such as `crsr_••••••••wxyz`.
- That key calls Bridge `GET /v1/models` and `POST /v1/chat/completions`.
- Options: refresh models, pick the current model, change the Bridge base URL, re-authorize, or log out.
- Optionally expose Home Assistant LLM tools so Assist can control devices.

## Install with HACS

1. Install [HACS](https://hacs.xyz/).
2. HACS → Integrations → menu → Custom repositories.
3. Add `https://github.com/YyyQq-C/hass-smart-llm` as an **Integration**.
4. Download **Smart LLM**.
5. Restart Home Assistant.

Requires Home Assistant **2025.1.0** or newer.

## Manual install

Copy `custom_components/smart_llm` to `config/custom_components/smart_llm`, then restart.

## Authorize Cursor

1. Settings → Devices & services → Add integration → **Smart LLM**.
2. Choose **Cursor**.
3. Open the login URL and approve it on the Cursor portal. The verifier is not in that URL.
4. Submit. The integration polls until login completes, then mints a user API key named `Home Assistant Smart LLM` (90 days by default).
5. Confirm that you understand Cursor Bridge is unofficial, then pick a model. `default` lets Cursor choose.

The key is stored encrypted. Diagnostics and the entity attribute only show the mask.

If team policy forbids user API keys, login can succeed while minting fails. A team admin has to allow user keys, or a later provider can accept an existing key directly.

## Use it with Assist

1. Settings → Voice assistants → Add assistant (or edit one).
2. Set the conversation agent to the **Cursor** entity this integration created (the name includes the account email when Cursor returned one).
3. Talk to Assist from the panel or a voice satellite.

“Control Home Assistant” in options exposes the selected Assist tools to the model. Leave it empty for text-only replies.

## Options

| Action | What it does |
| --- | --- |
| Model and Bridge URL | Base URL, current model, Assist tools, extra instructions |
| Refresh models | Manual `GET /v1/models` |
| Re-authorize | Browser login again and replace the stored key |
| Log out | Delete the key from Home Assistant. The dashboard key stays valid until it expires or you revoke it |

After logout, authorize again before Assist can use this agent.

## How the key is stored

The encryption key is derived from this Home Assistant install's instance id (`.storage/core.uuid`). A copied config-entry file does not reveal the Cursor key. A full configuration-directory backup includes the instance id and can decrypt it, which is the same boundary as the rest of Home Assistant's local data.

Do not commit `.storage`, and do not paste raw keys into issues.

## Development

```bash
pip install pytest aiohttp cryptography
pytest
```

Tests talk to local mocks, not to Cursor or Cursor Bridge.

To add a provider, implement `ChatProvider` in `custom_components/smart_llm/provider/base.py`, register it in `provider/registry.py`, and add a config-flow step for that provider's own authentication. Do not reuse the Cursor browser login for a provider that expects a pasted API key.

## License

MIT. See [LICENSE](LICENSE).
