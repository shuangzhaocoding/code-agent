# Code Agent 插件

第三方按同一套契约扩展 Code Agent。当前已落地的贡献点：

- `llm.provider`：大模型适配（配置、拉模型、探测、发起对话）
- `tools`：Agent 工具

## 发现路径

优先级从低到高（同 id 后者覆盖前者）：

1. 仓库 `plugins/`
2. 用户 `~/.code-agent/plugins/`
3. 工作区 `.code-agent/plugins/`

支持两种形态：

- 单文件 `my_plugin.py`，导出 `register(registry)`
- 目录 `my_plugin/plugin.json` + `plugin.py`

`plugin.json` 示例：

```json
{
  "id": "acme.anthropic",
  "name": "Anthropic",
  "description": "Native Anthropic Messages API adapter.",
  "version": "1.0.0",
  "api": 1,
  "kind": "llm.provider",
  "contributes": ["llm.provider"],
  "author": "Acme Inc.",
  "homepage": "https://example.com/plugins/anthropic",
  "repository": "https://github.com/acme/code-agent-anthropic",
  "license": "MIT",
  "icon": "chip",
  "accent": "#d97706",
  "keywords": ["anthropic", "claude", "llm"]
}
```

单文件插件也支持同名 Python 常量（`PLUGIN_AUTHOR`、`PLUGIN_HOMEPAGE` 等）。

### 元数据字段

| 字段 | 说明 |
| --- | --- |
| `author` | 作者或组织 |
| `homepage` | 插件主页 / 文档地址 |
| `repository` | 源码仓库地址 |
| `license` | 许可证（如 MIT） |
| `icon` | 内置图标名（如 `git`），或插件目录内的图片相对路径（如 `icon.png`） |
| `icon_url` | 远程图标地址（`https://...`）；与本地图片二选一 |
| `accent` | 主题色（十六进制，如 `#4f6bff`） |
| `keywords` | 标签数组，便于搜索 |

### 自定义图标图片

支持 **png / svg / jpg / webp / ico / gif**，放在插件目录内：

**目录插件**（推荐）：

```
my_plugin/
├── plugin.json
├── plugin.py
└── icon.png          # 或 icon.svg / icon.ico
```

`plugin.json`：

```json
{
  "id": "acme.my-plugin",
  "name": "My Plugin",
  "icon": "icon.png"
}
```

也可不写 `icon`，只要目录里有 `icon.png`、`icon.svg` 或 `icon.ico` 会自动识别。

**单文件插件**（图片与 `.py` 同级）：

```
plugins/
├── my_plugin.py
└── my_plugin_icon.png
```

```python
PLUGIN_ICON = "my_plugin_icon.png"
# 或远程地址
PLUGIN_ICON_URL = "https://example.com/icon.png"
```

前端通过 `GET /api/plugins/{id}/icon` 加载本地图片；远程图片直接使用 `icon_url`。

`api` 大于宿主支持的主版本时拒绝加载。

### 停用插件

停用 LLM 适配插件后：

- **模型页 / 对话栏**：已配置但该插件下的提供商与模型**不再显示**
- **Preset 快速添加卡片**：对应 preset **隐藏**
- **对话请求**：无法选用这些模型（`get_chat_model` 返回空，不再静默回退到其他适配器）
- **同步 / 探测 / 新建**：返回 `403 plugin.disabled`
- **插件页**：仍显示该插件，可重新启用；数据库中的配置**保留**，启用后恢复可见

工具插件停用后，对应 Agent 工具不再注入。

## 模型适配器接口

实现 `LlmAdapter`（见 `apps/api/code_agent/plugins/base.py`）：

| 方法 | 职责 |
| --- | --- |
| `create_chat_model(provider, model)` | 构造 LangChain Chat 客户端 |
| `list_models(provider)` | 拉取远端模型列表 |
| `probe_model(provider, model_id)` | 探测连通性 |
| `apply_thinking(chat, provider, model, level)` | 把思考档位写进请求 |
| `normalize_base_url(url)` | 规范化 Base URL |

并声明 `kind`、`title`、`description`、`config_schema`、`presets`。

注册：

```python
PLUGIN_TITLE = "Acme Anthropic"
PLUGIN_DESCRIPTION = "Native Anthropic Messages API adapter."
PLUGIN_KIND = "llm.provider"

def register(registry) -> None:
    registry.register_llm_adapter(AnthropicAdapter(), plugin_id="acme.anthropic")
```

内置 LLM 适配器按厂商拆分为独立插件（见 `apps/api/code_agent/llm/adapters/`）：

| 插件 id | 厂商 | 思考强度 |
| --- | --- | --- |
| `builtin.llm.openai` | OpenAI 官方 | Responses API `reasoning.effort` |
| `builtin.llm.deepseek` | DeepSeek | `extra_body.thinking.budget_tokens` |
| `builtin.llm.qwen` | 通义千问（DashScope） | `extra_body.enable_thinking` / `thinking_budget` |
| `builtin.llm.gateway` | 中转（含 AIValux Codex） | Codex 用 `reasoning.effort`；通用中转按模型名推断 |
| `builtin.llm.ccx` | [CCX](https://github.com/BenedictKing/ccx) 网关 | GPT-5/o 系列走 Responses；DeepSeek/Qwen 等走 Chat 并按模型适配 |
| `builtin.llm.ollama` | Ollama 本地 | 不支持 |
| `builtin.llm.openai_compat` | 自定义 OpenAI 兼容 | 保守推断，避免 GPT 网关 502 |

通用参考实现：`apps/api/code_agent/llm/adapters/openai_compat.py`。

### CCX 网关接入

1. 模型页选择 **CCX** preset 卡片（或自定义接入，类型选 `ccx`）
2. Base URL：`http://127.0.0.1:3688/v1`（CCX 默认端口 3688；填 `http://127.0.0.1:3688` 也会自动补全）
3. API Key：CCX 的 `PROXY_ACCESS_KEY`
4. 在 CCX 管理面板配置上游渠道后，点「同步模型」

GPT-5 / o 系列会自动走 `/v1/responses`；DeepSeek、Qwen 等走 Chat Completions 并按模型名适配思考参数。
