---
name: create-plugin
description: 创建 Code Agent 插件（工具或 LLM 适配器）。用户要扩展工具、接入新模型厂商、编写 plugin.py、或询问插件发现路径时使用。
license: Apache-2.0
metadata:
  author: code-agent
  version: "1.0"
---

# 创建插件

## 先确定类型

| kind | 用途 |
| --- | --- |
| `tools` | 注册 Agent 工具（`@tool`） |
| `llm.provider` | 接入新模型厂商 / 网关 |

参考：`plugins/README.md`、`plugins/hello_world.py`。

## 发现路径（优先级从低到高）

1. 仓库 `plugins/`
2. 用户 `~/.code-agent/plugins/`
3. 工作区 `.code-agent/plugins/`

同 id 后者覆盖前者。内置 LLM 适配器在 `apps/api/code_agent/llm/adapters/`，一般不在此扩展。

## 两种形态

### 单文件（适合简单工具插件）

```
plugins/my_plugin.py
```

```python
PLUGIN_TITLE = "My Plugin"
PLUGIN_DESCRIPTION = "简短说明"
PLUGIN_KIND = "tools"  # 或 llm.provider
PLUGIN_VERSION = "1.0.0"
PLUGIN_AUTHOR = "Your Name"
PLUGIN_KEYWORDS = ("tag1", "tag2")

def register(registry) -> None:
    from langchain_core.tools import tool

    @tool
    def my_tool(arg: str) -> str:
        """工具 docstring，模型可见。"""
        return f"result: {arg}"

    registry.register_tool(
        my_tool,
        source="plugin:my_plugin",
        modes=("ask", "agent", "plan"),
    )
```

### 目录（推荐，可含图标与元数据）

```
my_plugin/
├── plugin.json
├── plugin.py
└── icon.png          # 可选
```

`plugin.json` 最小示例：

```json
{
  "id": "acme.my-plugin",
  "name": "My Plugin",
  "description": "做了什么",
  "version": "1.0.0",
  "api": 1,
  "kind": "tools",
  "contributes": ["tools"],
  "author": "Acme Inc.",
  "license": "MIT"
}
```

`plugin.py` 导出 `register(registry)`，逻辑同单文件。

## LLM 适配器

实现 `LlmAdapter` 协议（见 `apps/api/code_agent/plugins/base.py`）：

- `create_chat_model(provider, model)`
- `list_models(provider)`
- `probe_model(provider, model_id)`
- `apply_thinking(chat, provider, model, level)`
- `normalize_base_url(url)`

并声明 `kind`、`title`、`description`、`config_schema`、`presets`。

注册：

```python
def register(registry) -> None:
    registry.register_llm_adapter(MyAdapter(), plugin_id="acme.my-llm")
```

参考：`apps/api/code_agent/llm/adapters/openai_compat.py`。

## 创建流程

1. 与用户确认插件类型、id、存放位置
2. 阅读 `plugins/README.md` 与最接近的现有示例
3. 创建文件并实现 `register(registry)`
4. 工具插件：确认 docstring 清晰、无副作用、错误信息可读
5. LLM 插件：确认 `config_schema` 与 preset 完整
6. 告知用户在 **插件** 面板启用/禁用；停用后对应工具或模型不再注入

## 约束

- `api` 不得大于宿主支持的主版本
- 工具 docstring 是模型选择工具的依据，必须准确
- 不在插件中硬编码密钥；从 provider 配置读取
- 单文件插件 id 默认为文件名（不含 `.py`）；目录插件用 `plugin.json` 的 `id`

## 校验清单

- [ ] `register(registry)` 可导入且无语法错误
- [ ] `PLUGIN_KIND` / `plugin.json.kind` 正确
- [ ] 工具已指定 `modes`；LLM 适配器实现了全部必需方法
- [ ] 重启或刷新插件列表后能在 UI 看到
