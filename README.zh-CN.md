[English](README.md) | [中文](README.zh-CN.md)

# Smart LLM

![Smart LLM](images/icon.png)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Home Assistant Assist 的可插拔对话代理。当前接入 **Cursor**、**OpenAI** 和 **Anthropic**，共用同一套提供方接口。

集成域名是 `smart_llm`。添加之后，可以在「设置 → 语音助手」里选这个代理。

## 功能

- 在浏览器里登录 Cursor，握手方式与 Cursor TypeScript SDK 和 `agent login` 相同。
- 签发用户 API 密钥，并加密保存在这套 Home Assistant 上。界面只显示掩码，例如 `crsr_••••••••wxyz`。
- 界面里的账号地址会打码（`yongqc@gmail.com` 显示为 `y**@g**.com`）。Assist 代理名称是 **Cursor**，名称里不包含邮箱。
- 填写 OpenAI 或 Anthropic 的 API 密钥。每家都可以走官方 API，也可以用同一套密钥请求头指向自定义基础 URL。界面掩码类似 `sk••••••••wxyz`。
- 拉取模型列表并回答 Assist。Cursor 仍通过 OpenAI 兼容的 Bridge 地址。
- 注册对话实体，可选把 Home Assistant 工具交给模型。
- 在集成选项里退出登录，或切换到另一个 Cursor 账号。

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

### 手动安装

把集成复制到配置目录后重启。清单文件应在：

```text
config/custom_components/smart_llm/manifest.json
```

## 授权 Cursor

1. 打开「设置 → 设备与服务 → 添加集成 → **Smart LLM**」。
2. 选择 **Cursor**。
3. 打开登录网址，并在 Cursor 门户里批准。校验码留在 Home Assistant 上，不会出现在网址里。
4. 提交。Home Assistant 会轮询到登录完成，然后签发名为 `Home Assistant Smart LLM` 的用户 API 密钥（90 天）。
5. 确认你了解 Cursor Bridge 是非官方服务，再选择模型。`default` 表示交给 Cursor 选择。

浏览器会话令牌在签发后即丢弃。Home Assistant 只保存 API 密钥，并用本机实例 ID（`.storage/core.uuid`）派生的密钥加密。诊断信息和实体属性里只有掩码。

如果团队策略禁止用户 API 密钥，登录可能成功，但签发仍会失败。需要团队管理员放开该权限。

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

退出登录不会在 Cursor 控制台里撤销这把密钥。若要立刻失效，请到控制台撤销。之后需要重新授权，Assist 才能继续使用这个代理。切换账号会先退出，再使用与首次安装相同的浏览器登录。重新授权仍然要求是同一个 Cursor 账号。

## 添加 OpenAI

1. 添加 Smart LLM，选择 **OpenAI**。
2. 粘贴 API 密钥。加密方式与 Cursor 密钥相同，使用本机 Fernet 密钥。保存后界面只显示掩码。
3. 选择请求方式：
   - **官方 API（密钥放在请求头）。** 请求发到 `https://api.openai.com/v1`，请求头为 `Authorization: Bearer`。
   - **自定义基础 URL。** 同一个 `Authorization: Bearer` 发到你填写的地址。可用于 Azure OpenAI、OpenRouter 或本地的 OpenAI 兼容代理。路径不为空时请带上 `/v1`，例如 `https://openrouter.ai/api/v1`。
4. 选择模型。如果拉不到模型列表，可以手动填写模型 id。

在选项里可以改请求方式、基础 URL 和模型，也可以替换或移除密钥。从 Home Assistant 移除密钥不会在 OpenAI 那边撤销它。

## 添加 Anthropic

1. 添加集成，选择 **Anthropic**。
2. 粘贴 API 密钥。保存和掩码方式与 OpenAI 相同。
3. 选择请求方式：
   - **官方 API（密钥放在请求头）。** 请求发到 `https://api.anthropic.com`，请求头为 `x-api-key` 和 `anthropic-version`。对话使用 `POST /v1/messages`。
   - **自定义基础 URL。** 同样的请求头发到 Anthropic 兼容网关。填写主机根地址；末尾的 `/v1` 会被去掉。
4. 选择模型。

如果 Claude 走的是 OpenAI 兼容代理，请用 OpenAI 提供方并填写自定义基础 URL。Anthropic 提供方使用 Messages API。

在选项里可以改请求方式、基础 URL 和模型，也可以替换或移除密钥。移除密钥不会在 Anthropic 控制台里撤销它。

## 接到 Assist

1. 打开「设置 → 语音助手」，添加助手或编辑已有助手。
2. 对话代理选这个集成创建的实体。Cursor、OpenAI、Anthropic 会各自创建一个实体。
3. 保存后，用 Assist 面板或语音卫星说话。

「控制 Home Assistant」留空时，代理只回答文字。需要模型操作设备时，再选择一项 Assist API。

## Cursor Bridge

Assist 不会调用 Cursor 官方的对话接口。登录之后，补全请求发到你配置的 Bridge 基础 URL：

```text
https://cursorbridge.dev/v1
```

[Cursor Bridge](https://cursorbridge.dev) 是非官方社区软件，不是 Cursor 或 Home Assistant 的产品。

- 提示词和 API 密钥会送到这个地址。该地址的运营者可以看到这些内容。
- 请使用你自己的 Cursor 账号，并遵守套餐限制。
- 如果不使用默认主机，在集成选项里把基础 URL 改成其他 OpenAI 兼容端点。

浏览器登录本身仍然走 Cursor 门户和 `api2.cursor.sh`。

## 扩展提供方

Cursor、OpenAI 和 Anthropic 已在 `provider/registry.py` 注册。新的提供方需要实现 `custom_components/smart_llm/provider/base.py` 里的 `ChatProvider`，在该注册表登记，并在配置流里加上自己的登录步骤。需要用户粘贴密钥的提供方，不要复用 Cursor 的浏览器登录。

## 许可

MIT。见 [LICENSE](LICENSE)。
