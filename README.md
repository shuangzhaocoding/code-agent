# Code Agent

开源、无登录、本地优先的 Web 编码 Agent 工作台。对标 Cursor 的工作流：工作区、可拖动停靠布局、交互式终端、可插拔 Skill / LLM，以及刷新浏览器后仍继续的流式输出。

> 默认只绑定 `127.0.0.1`。无登录 + Agent 能跑命令，**不要把实例裸暴露到公网**。

## 技术栈

- 后端：Python 3.11 · FastAPI · TortoiseORM · LangGraph
- 前端：Vue 3 · TypeScript · OpenTiny TinyVue / TinyRobot · Monaco · xterm.js · dockview

## 启动

两个终端：

```bash
# API
cd apps/api
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m uvicorn code_agent.main:app --reload --host 127.0.0.1 --port 8000

# Web
cd apps/web
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173 ，选择一个本地目录作为工作区。

可选环境变量（启动时若库中还没有模型，会自动写入一条 Provider）：

```bash
export CODE_AGENT_OPENAI_API_KEY=sk-...
export CODE_AGENT_OPENAI_BASE_URL=https://api.openai.com/v1
export CODE_AGENT_OPENAI_MODEL=gpt-4o-mini
```

DeepSeek：在 Models 面板点「添加 DeepSeek」并填 API Key；或启动前设置 `DEEPSEEK_API_KEY` / `CODE_AGENT_DEEPSEEK_API_KEY`。会写入 `deepseek-chat`（默认）和 `deepseek-reasoner`。

Ollama 示例：`CODE_AGENT_OPENAI_BASE_URL=http://127.0.0.1:11434/v1` 且 `CODE_AGENT_OPENAI_MODEL=llama3.1`。也可在 Models 面板点「添加 Ollama」。

## 可插拔

| 扩展 | 怎么加 |
| --- | --- |
| Skill | 目录 + `SKILL.md`，放到 `skills/`、`~/.code-agent/skills/`、工作区 `.agents/skills/` 或 `.cursor/skills/` |
| Python 插件 | `plugins/*.py` 或 `plugin.json` + `plugin.py`，导出 `register(registry)` |
| LLM 适配器 | 实现 `LlmAdapter` 并 `register_llm_adapter`；内置 OpenAI 兼容适配器 |
| 插件管理 | 侧栏「插件」页查看已安装/已注册的插件 |
| 布局 | 拖动标签分屏，自动保存；活动栏可重新打开窗口 |
| 配置 | `config/default.yaml` → `~/.code-agent/config.yaml` → `.code-agent/config.yaml` → 设置页 |

示例插件见 `plugins/hello_world.py`。

## 刷新续流

Agent Run 在服务端后台执行，SSE 只是订阅事件日志。刷新页面会加载已落库的消息块，再用 `last_event_id` 续订。交互式终端的 PTY 活在 API 进程里，刷新会重连同一会话。

需求全文见 [docs/需求规格说明书.md](docs/需求规格说明书.md)。
