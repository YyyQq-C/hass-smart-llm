[English](README.md) | [中文](README.zh-CN.md)

# Smart LLM

![Smart LLM](images/icon.png)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Release](https://img.shields.io/github/v/release/YyyQq-C/hass-smart-llm?label=release)](https://github.com/YyyQq-C/hass-smart-llm/releases/tag/v1.1.0)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Home Assistant Assist 的可插拔对话代理。当前版本 [v1.1.0](https://github.com/YyyQq-C/hass-smart-llm/releases/tag/v1.1.0) 接入 **Cursor**、**OpenAI** 和 **Anthropic**。每个提供方各自有一个对话实体，在「设置 → 语音助手」里选用。

集成域名是 `smart_llm`。集成清单里的版本是 `1.1.0`。

## 功能

- **Cursor。** 在浏览器里登录，握手方式与 Cursor TypeScript SDK 和 `agent login` 相同。签发的用户 API 密钥加密保存在这套 Home Assistant 上。账号界面显示掩码，例如 `y**@g**.com`。可以在集成选项里退出登录或切换账号。集成标题和 Assist 实体名称保持为 **Cursor**。
- **OpenAI 与 Anthropic。** 粘贴 API 密钥，并选择请求方式：官方 API，或自定义基础 URL。自定义主机包括 Azure OpenAI、OpenRouter、本地 OpenAI 兼容代理，以及 Anthropic 兼容网关。密钥仍放在该提供方常用的请求头里。
- **密钥加密。** Cursor、OpenAI、Anthropic 的密钥都用本机派生的 Fernet 密钥加密（`.storage/core.uuid`）。界面和诊断信息只显示掩码。密钥不会写入日志。
- 每个配置项对应一个对话实体，可选把 Home Assistant 工具交给模型。

## 安装

需要 Home Assistant **2025.1** 或更新版本。`custom_components/smart_llm/brand/` 里的图标从 Home Assistant **2026.3** 起显示在界面上。

### HACS

这是 HACS **自定义仓库**，不在 HACS 默认列表里。

1. 如果还没有 [HACS](https://hacs.xyz/)，先安装它。
2. 打开 HACS → 集成 → 菜单 → **自定义存储库**。
3. 添加下面的地址，类别选择 **集成**：

```text
https://github.com/YyyQq-C/hass-smart-llm
```

4. 下载 **Smart LLM**，然后重启 Home Assistant。

也可使用 My Home Assistant 快捷链接（需已安装 HACS）：

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=YyyQq-C&repository=hass-smart-llm&category=integration)

这个链接只会打开本自定义仓库，不表示 Smart LLM 已经进入 HACS 默认列表。

### 更新

已经装过的实例要换成 [v1.1.0](https://github.com/YyyQq-C/hass-smart-llm/releases/tag/v1.1.0) 或之后的版本时，在 HACS 里更新即可。自定义仓库和已有的 Smart LLM 配置项都保留。

1. 打开 HACS → 集成 → **Smart LLM**。
2. HACS 提示有新版本时，选择 **Update**（更新）。若要重新拉取当前版本，打开菜单并选择 **Redownload**（重新下载）。
3. 重启 Home Assistant。

重启后会加载新文件。已经保存在 Home Assistant 里的 Cursor 登录、API 密钥和模型设置仍留在各自的配置项上。

### 手动安装

把集成复制到配置目录后重启。清单文件应在：

```text
config/custom_components/smart_llm/manifest.json
```

不用 HACS 时，用新版本替换该目录，然后重启。

## 授权 Cursor

1. 打开「设置 → 设备与服务 → 添加集成 → **Smart LLM**」。
2. 选择 **Cursor**。
3. 打开登录网址，并在 Cursor 门户里批准。校验码留在 Home Assistant 上，不会出现在网址里。
4. 提交。Home Assistant 会轮询到登录完成，然后签发名为 `Home Assistant Smart LLM` 的用户 API 密钥（90 天）。
5. 确认你了解 Cursor Bridge 是非官方服务，再选择模型。`default` 表示交给 Cursor 选择。

浏览器会话令牌在签发后即丢弃。Home Assistant 只保存 API 密钥，并用本机实例 ID（`.storage/core.uuid`）派生的密钥加密。诊断信息和实体属性里只有掩码，例如 `crsr_••••••••wxyz`。

如果团队策略禁止用户 API 密钥，登录可能成功，但签发仍会失败。需要团队管理员放开该权限。

同一个 Cursor 账号不能添加两次。设备页会链到 [Cursor 控制台](https://cursor.com/dashboard)。

### 选项

在集成选项里调整 Assist 如何调用 Cursor。

| 操作 | 作用 |
| --- | --- |
| 模型与 Bridge URL | 基础 URL、模型、Assist 工具和补充说明 |
| 刷新模型列表 | 请求 `GET /v1/models` |
| 重新授权 | 再走一次浏览器登录，并为同一个账号替换已保存的密钥 |
| 切换账号 | 移除已保存的密钥，再走浏览器登录，绑定另一个 Cursor 账号。新密钥保存后会刷新模型列表 |
| 退出登录 | 从 Home Assistant 删除密钥和已保存的账号地址 |

选项界面里的账号显示为 `y**@g**.com` 这种掩码，不会出现完整邮箱。语音助手卡片和集成标题保持为 **Cursor**。

退出登录会从 Home Assistant 删除密钥。这把密钥在 Cursor 控制台里仍然有效，直到过期或你在那里撤销。之后需要重新授权，Assist 才能继续使用这个代理。切换账号会先退出，再使用与首次安装相同的浏览器登录。重新授权仍然要求是同一个 Cursor 账号。

## OpenAI 与 Anthropic

再添加一次 **Smart LLM**，选择 **OpenAI** 或 **Anthropic**。每次选择都是独立的配置项。Assist 实体名称是 **OpenAI** 或 **Anthropic**。集成条目标题包含提供方名称和密钥掩码。

1. 粘贴 API 密钥。密钥会加密保存。之后的界面只显示掩码：前两个字符、八个圆点，以及最后四个字符。
2. 选择下面的请求方式，再选模型。列表为空时可以手动填写模型 ID。还没有拉到列表时，表单会建议 OpenAI 使用 `gpt-4o-mini`，Anthropic 使用 `claude-sonnet-4-5`。
3. 按需要设置 Assist 工具和补充说明。

同一把 API 密钥不能再添加到另一个配置项。设备页会链到 [OpenAI API 密钥](https://platform.openai.com/api-keys) 和 [Anthropic API 密钥](https://console.anthropic.com/settings/keys)。

### 请求方式

两个提供方都有这两种方式。官方 API 会忽略填写的自定义 URL，改用提供方默认地址。自定义基础 URL 仍使用该提供方的请求头，只是发到你填写的主机。

| 方式 | OpenAI | Anthropic |
| --- | --- | --- |
| 官方 API | 向 `https://api.openai.com/v1` 发送 `Authorization: Bearer`（在该基础地址上 `GET /models`、`POST /chat/completions`） | 向 `https://api.anthropic.com` 发送 `x-api-key` 和 `anthropic-version: 2023-06-01`（`GET /v1/models`、`POST /v1/messages`） |
| 自定义基础 URL | 同样的 `Authorization: Bearer`，发到你的主机：Azure OpenAI、OpenRouter，或本地 OpenAI 兼容代理 | 同样的 `x-api-key` 和 `anthropic-version`，发到 Anthropic 兼容网关 |

自定义 URL 必须是 `http` 或 `https`，且不能带用户名或密码。OpenAI 兼容地址会被规范成以 `/v1` 结尾（`https://openrouter.ai/api/v1/chat/completions` 会变成 `https://openrouter.ai/api/v1`）。Anthropic 兼容地址填写主机即可；末尾的 `/v1` 或 `/v1/messages` 可以保留，实际请求仍是 `POST /v1/messages`。

### 选项

打开 OpenAI 或 Anthropic 配置项的选项。

| 操作 | 作用 |
| --- | --- |
| 模型与基础 URL | 官方 API 或自定义基础 URL，以及模型、Assist 工具和补充说明 |
| 刷新模型列表 | 向当前端点请求模型列表 |
| 更新 API 密钥 | 替换已保存的密钥。新密钥通过校验后才会覆盖旧密钥 |
| 移除 API 密钥 | 从 Home Assistant 删除已保存的密钥 |

移除 API 密钥不会在提供方那里撤销这把密钥。若要立刻失效，请到提供方控制台撤销。重新授权、切换账号和退出登录只出现在 Cursor 配置项上。

## 接到 Assist

1. 打开「设置 → 语音助手」，添加助手或编辑已有助手。
2. 对话代理选这个集成创建的 **Cursor**、**OpenAI** 或 **Anthropic** 实体。
3. 保存后，用 Assist 面板或语音卫星说话。

「控制 Home Assistant」留空时，代理只回答文字。需要模型操作设备时，再选择一项 Assist API。

## Cursor Bridge

这一节只针对 Cursor 提供方。OpenAI 官方模式调用 `https://api.openai.com/v1`。Anthropic 官方模式调用 `https://api.anthropic.com`。

Assist 不会调用 Cursor 官方的对话接口。登录之后，补全请求发到你配置的 Bridge 基础 URL：

```text
https://cursorbridge.dev/v1
```

[Cursor Bridge](https://cursorbridge.dev) 是非官方社区软件，不是 Cursor 或 Home Assistant 的产品。

- 提示词和 API 密钥会送到这个地址。该地址的运营者可以看到这些内容。
- 请使用你自己的 Cursor 账号，并遵守套餐限制。
- 如果不使用默认主机，在集成选项里把基础 URL 改成其他 OpenAI 兼容端点。Cursor 的这个字段与上面 OpenAI、Anthropic 的请求方式是分开的。

浏览器登录本身仍然走 Cursor 门户和 `api2.cursor.sh`。

## 扩展提供方

[v1.1.0](https://github.com/YyyQq-C/hass-smart-llm/releases/tag/v1.1.0) 已注册 Cursor、OpenAI 和 Anthropic。新的提供方需要实现 `custom_components/smart_llm/provider/base.py` 里的 `ChatProvider`，在 `provider/registry.py` 注册，并在配置流里加上自己的步骤。Cursor 继续使用浏览器登录。需要用户粘贴密钥的提供方，用自己的请求头发送这把密钥。

## 许可

MIT。见 [LICENSE](LICENSE)。
