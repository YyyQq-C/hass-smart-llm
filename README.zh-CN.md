[English](README.md) | [中文](README.zh-CN.md)

# Smart LLM

![Smart LLM](images/icon.png)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Release](https://img.shields.io/github/v/release/YyyQq-C/hass-smart-llm?label=release)](https://github.com/YyyQq-C/hass-smart-llm/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Home Assistant Assist 的可插拔对话代理。1.2.0 有三条路径。每条路径各自有一个对话实体，在「设置 → 语音助手」里选用。

- **Cursor** 使用浏览器登录和 [Cursor Bridge](https://cursorbridge.dev)。Cursor 条目还会在 Cursor 返回当前计费周期时添加额度传感器。
- 菜单里的 **OpenAI** 是 OpenAI 兼容协议：chat completions，有密钥时发送 `Authorization: Bearer`。官方模式调用 OpenAI，并且必须有密钥。自定义基础 URL 把同一套请求发到任何实现了该 API 的主机，包括 Azure OpenAI、OpenRouter、Ollama、vLLM、LM Studio 和 LocalAI。自定义 URL 上的密钥可以不填。密钥为空时不发送 `Authorization`。
- 菜单里的 **Anthropic** 是 Anthropic 兼容协议：`x-api-key`、`anthropic-version` 和 Messages API。官方模式调用 Anthropic。自定义基础 URL 把同一套请求发到兼容网关。Anthropic 仍然必须有密钥。

菜单仍使用 OpenAI 和 Anthropic 这两个名字，因为它们表示的是协议。其他厂商只要接口符合其中一种风格，就可以选对应的菜单项。没有单独的 Ollama 协议。

集成域名是 `smart_llm`。集成清单里的版本是 `1.2.0`。v1.2.0 允许 OpenAI 兼容的自定义基础 URL 不填 API 密钥，并把 Cursor 的当前计费周期读成传感器。没有增加新的对话协议。

## 功能

- **Cursor。** 在浏览器里登录，握手方式与 Cursor TypeScript SDK 和 `agent login` 相同。签发的用户 API 密钥加密保存在这套 Home Assistant 上。账号界面显示掩码，例如 `y**@g**.com`。可以在集成选项里退出登录或切换账号。集成标题和 Assist 实体名称保持为 **Cursor**。
- **OpenAI 兼容（菜单：OpenAI）。** 粘贴 API 密钥；本地服务不校验密钥时可以留空。官方 API 向 `https://api.openai.com/v1` 发送 `Authorization: Bearer`，并且仍然必须有密钥。自定义基础 URL 把 chat completions 请求发到你指定的主机：Azure OpenAI、OpenRouter、Ollama、vLLM、LM Studio、LocalAI，或其他 OpenAI 兼容服务。有密钥时发送 `Authorization: Bearer`。密钥为空时不发送这个请求头。
- **Cursor 额度。** Cursor 条目上的传感器显示套餐剩余额度、Cursor 返回的已用比例，以及计费周期结束时间。见[Cursor 额度](#cursor-额度)。
- **Anthropic 兼容（菜单：Anthropic）。** 粘贴 API 密钥。官方 API 向 `https://api.anthropic.com` 发送 `x-api-key` 和 `anthropic-version: 2023-06-01`（`POST /v1/messages`）。自定义基础 URL 保留这些请求头，发到 Anthropic 兼容网关。
- **密钥加密。** Cursor 密钥和两种协议的 API 密钥都用本机派生的 Fernet 密钥加密（`.storage/core.uuid`）。界面和诊断信息只显示掩码。密钥不会写入日志。
- 每个配置项对应一个对话实体，可选把 Home Assistant 工具交给模型。Assist 名称跟随菜单标签（**Cursor**、**OpenAI** 或 **Anthropic**），自定义 URL 后面即使是其他厂商也一样。

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

已经装过的实例要换成已发布的版本时，在 HACS 里更新即可。自定义仓库和已有的 Smart LLM 配置项都保留。当前代码里的清单版本是 `1.2.0`。GitHub Release 另行发布。

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

## OpenAI 兼容与 Anthropic 兼容

再添加一次 **Smart LLM**，按协议选择。**OpenAI** 表示 OpenAI 兼容风格。**Anthropic** 表示 Anthropic 兼容风格。每次选择都是独立的配置项。Assist 实体使用该菜单名称，因此自定义主机仍显示为 **OpenAI** 或 **Anthropic**。集成条目标题包含该名称和密钥掩码。

1. 粘贴你要调用的服务的 API 密钥。密钥会加密保存。之后的界面只显示掩码：前两个字符、八个圆点，以及最后四个字符。
2. 选择官方 API 或自定义基础 URL（见下），再选模型。列表为空时，填写该主机要求的模型 ID。还没有拉到列表时，OpenAI 兼容表单会建议 `gpt-4o-mini`，Anthropic 兼容表单会建议 `claude-sonnet-4-5`。
3. 按需要设置 Assist 工具和补充说明。

同一把 API 密钥不能在同一个菜单项下添加两次。设备页跟随菜单标签，打开该协议对应的 [OpenAI API 密钥](https://platform.openai.com/api-keys) 页或 [Anthropic API 密钥](https://console.anthropic.com/settings/keys) 页。

### 请求方式

v1.1.0 用两种兼容风格发送 API 密钥。许多厂商实现了其中一种。每种风格里，官方模式调用该协议的公有云，并忽略自定义 URL。自定义基础 URL 保留同一套请求头，发到你填写的主机。

| 协议（菜单名称） | 官方 API | 自定义基础 URL |
| --- | --- | --- |
| OpenAI 兼容（**OpenAI**） | 向 `https://api.openai.com/v1` 发送 `Authorization: Bearer`（在该基础地址上 `GET /models`、`POST /chat/completions`）。必须有密钥 | 同样的 chat completions 请求，发到你的主机：Azure OpenAI、OpenRouter、Ollama、vLLM、LM Studio、LocalAI，或其他 OpenAI 兼容服务。密钥可以不填。为空时不发送 `Authorization` |
| Anthropic 兼容（**Anthropic**） | 向 `https://api.anthropic.com` 发送 `x-api-key` 和 `anthropic-version: 2023-06-01`（`GET /v1/models`、`POST /v1/messages`） | 同样的 `x-api-key`、`anthropic-version` 请求头和 Messages 请求，发到 Anthropic 兼容网关 |

自定义 URL 必须是 `http` 或 `https`，且不能带用户名或密码。OpenAI 兼容地址会被规范成以 `/v1` 结尾（`https://openrouter.ai/api/v1/chat/completions` 会变成 `https://openrouter.ai/api/v1`）。本地的 `http://…/v1` 会保留 `http`。Anthropic 兼容地址填写主机即可；末尾的 `/v1` 或 `/v1/messages` 可以保留，实际请求仍是 `POST /v1/messages`。

### 本地服务（Ollama、vLLM 以及其他）

Ollama、vLLM、LM Studio 和 LocalAI 说的是 OpenAI 对话 API。请用 **OpenAI** 菜单。Smart LLM 里没有单独的 Ollama 集成。

1. 再添加一次 **Smart LLM**，选择 **OpenAI**。
2. 服务不要求密钥时，API 密钥留空。Ollama 默认的 OpenAI 端点不需要密钥。如果服务要求一个占位密钥，就粘贴它；Smart LLM 会发送 `Authorization: Bearer`。
3. 选择 **自定义基础 URL**。
4. 填写该服务的 `/v1` 地址：

   | 服务 | 常见地址 |
   | --- | --- |
   | Ollama | `http://HOST:11434/v1` |
   | vLLM OpenAI 服务 | `http://HOST:8000/v1` |
   | LM Studio | `http://HOST:1234/v1` |
   | LocalAI | `http://HOST:8080/v1` |

   端口是常见默认值。请改成这台服务实际监听的端口。
5. 从列表里选模型，或填写该服务要求的名称（例如 `llama3.2`，或 vLLM 的模型 id）。

跑在 Docker 里的 Home Assistant 不能用 `localhost` 访问宿主机上的服务。容器里的 `localhost` 是容器自己。请用宿主机的局域网地址，例如 `http://192.168.1.20:11434/v1`；如果 `host.docker.internal` 能解析到宿主机（Docker Desktop 可以），也可以用 `http://host.docker.internal:11434/v1`。Linux 上的 Docker 只有在启动容器时做了这个主机映射，`host.docker.internal` 才存在。

官方 OpenAI 端点仍然拒绝空密钥。空密钥只在 OpenAI 兼容的自定义基础 URL 上可用。

### 选项

打开从 **OpenAI** 或 **Anthropic** 创建的配置项的选项。同一协议下的每台主机，操作都相同。

| 操作 | 作用 |
| --- | --- |
| 模型与基础 URL | 官方 API 或自定义基础 URL，以及模型、Assist 工具和补充说明 |
| 刷新模型列表 | 向当前端点请求模型列表 |
| 更新 API 密钥 | 替换已保存的密钥。新密钥通过校验后才会覆盖旧密钥 |
| 移除 API 密钥 | 从 Home Assistant 删除已保存的密钥 |

移除 API 密钥后，签发该密钥的服务上这把密钥仍然有效。若要立刻失效，请到该服务撤销。重新授权、切换账号和退出登录只出现在 Cursor 配置项上。

## 接到 Assist

1. 打开「设置 → 语音助手」，添加助手或编辑已有助手。
2. 对话代理选名为 **Cursor**、**OpenAI** 或 **Anthropic** 的实体。自定义基础 URL 仍使用该协议的菜单名称。
3. 保存后，用 Assist 面板或语音卫星说话。

「控制 Home Assistant」留空时，代理只回答文字。需要模型操作设备时，再选择一项 Assist API。

## Cursor Bridge

这一节是 Cursor 路径：浏览器登录加上 Bridge。OpenAI 兼容的官方 API 调用 `https://api.openai.com/v1`。Anthropic 兼容的官方 API 调用 `https://api.anthropic.com`。其他主机在对应的菜单项里填写自定义基础 URL。

Assist 不会调用 Cursor 官方的对话接口。登录之后，补全请求发到你配置的 Bridge 基础 URL：

```text
https://cursorbridge.dev/v1
```

[Cursor Bridge](https://cursorbridge.dev) 是非官方社区软件，不是 Cursor 或 Home Assistant 的产品。

- 提示词和 API 密钥会送到这个地址。该地址的运营者可以看到这些内容。
- 请使用你自己的 Cursor 账号，并遵守套餐限制。
- 如果不使用默认主机，在 Cursor 选项里把 Bridge 基础 URL 改成其他 OpenAI 兼容端点。Cursor 的这个字段与上面的 API 密钥协议是分开的。

浏览器登录本身仍然走 Cursor 门户和 `api2.cursor.sh`。

## Cursor 额度

Cursor Bridge 没有公开的配额接口。它文档里的路由是 chat completions、Responses API、Anthropic messages、token 计数和模型列表。本集成不会从这些调用里编造剩余额度。

`cursor.com/api/` 下的控制台页面需要浏览器会话 Cookie。Smart LLM 在签发用户 API 密钥之后就丢掉这个会话，所以不会调用这些 Cookie 接口。

对于 Cursor 条目，Smart LLM 用已保存的用户 API 密钥向 Cursor 查询当前计费周期：

1. `POST https://api2.cursor.sh/auth/exchange_user_api_key`，`Authorization: Bearer` 为用户 API 密钥。返回的 access token 只留在内存里，不会写入配置项、诊断信息或日志。
2. `POST https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage`，使用这个 access token，并带上 `Connect-Protocol-Version: 1`。

这和登录流程用来签发密钥的非官方 Connect API 是同一套（`CreateUserApiKey`、`GetMe`）。Cursor 可能会改掉它。传感器大约每 30 分钟刷新一次。某个字段缺失时，对应传感器保持未知。调用失败时，传感器不可用，Assist 对话不受影响。

| 传感器 | 来源 |
| --- | --- |
| 套餐剩余额度 | `planUsage.remaining`，单位是美分，除以 100 后显示为 USD。原始美分放在属性里 |
| 套餐已用比例 | `planUsage.totalPercentUsed`，按 Cursor 返回的数值原样显示 |
| 额度重置时间 | `billingCycleEnd`，Unix 毫秒时间戳 |

`planUsage.limit`、已用金额和 `displayMessage` 是剩余额度传感器上的属性，都从响应里原样复制。OpenAI、Anthropic 和本地服务没有这些传感器。那些 API 不会在这里返回订阅额度，本集成也不用本地请求计数来代替配额。

## 扩展提供方

1.2.0 注册了三个客户端：Cursor、OpenAI 兼容客户端（菜单名称 **OpenAI**）、Anthropic 兼容客户端（菜单名称 **Anthropic**）。接口符合其中一种协议的服务，使用对应的客户端。官方模式调用该协议的公有云。自定义基础 URL 保留同一套请求风格，调用你填写的主机。OpenAI 兼容的自定义基础 URL 可以不填 API 密钥。另一种协议需要实现 `custom_components/smart_llm/provider/base.py` 里的 `ChatProvider`，在 `provider/registry.py` 注册，并在配置流里加上自己的步骤。Cursor 继续使用浏览器登录。

## 许可

MIT。见 [LICENSE](LICENSE)。
