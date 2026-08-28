# Code Agent 优化策略

> 版本：v1.0 · 2026-08-28  
> 目标：LangGraph 自定义图 + Checkpointer + 滑动窗口 + 跨会话结构化记忆 + 性能止血

## 1. 总体原则

| 原则 | 说明 |
|------|------|
| 双轨持久化 | LangGraph Checkpointer 管图执行状态；TortoiseORM 管 UI 事件与展示历史 |
| UI 协议不变 | 前端仍消费 `RunEvent` SSE；LangGraph 事件经 adapter 转为 `block.*` |
| 记忆分层 | 热记忆（滑动窗口）→ 温记忆（会话摘要）→ 冷记忆（工作区结构化事实） |
| 本地零依赖 | v1 继续 SQLite；结构化记忆用 JSON + 关键词检索 |

## 2. 目标架构

```
UI (SSE) ← EventBroker ← stream_adapter ← LangGraph graph
                ↓
         messages / run_events (SQLite)
                ↑
         Checkpointer (langgraph_checkpoints.sqlite3)

prepare_context → [compress?] → agent ↔ tools → extract_memory → END
                      ↑
        sliding window + conversation.summary + workspace_memories
```

## 3. LangGraph 图

### State

- `messages` — LangChain 消息栈（ReAct 循环）
- `workspace_id`, `conversation_id`, `run_id`, `mode`, `thinking_level`
- `system_prompt`, `memory_facts`, `conversation_summary`, `needs_compress`

### 节点

| 节点 | 职责 |
|------|------|
| `prepare_context` | 加载 skill、工作区记忆、滑动窗口、组装 messages |
| `compress` | 窗口外历史 LLM 摘要 → `Conversation.summary` |
| `agent` | 调用 LLM（bind tools） |
| `tools` | ToolNode 执行工具 |
| `extract_memory` | Run 结束抽取结构化事实 → `workspace_memories` |

### Checkpointer

- 文件：`~/.code-agent/data/langgraph_checkpoints.sqlite3`（与业务库分离）
- `thread_id`：`{workspace_id}:{conversation_id}`
- `Run.graph_thread_id` 记录线程 id

## 4. 滑动窗口

- 配置：`agent.sliding_window_size`（默认 12）
- 执行：`context_builder.py` 统一供 `prepare_context` 与 `context_usage` 使用
- 全量 Message 仍存 DB 供 UI；仅送入 LLM 的为窗口 + 摘要

## 5. 跨会话结构化记忆

### WorkspaceMemory

- 范围：Workspace 级，跨 Conversation 共享
- kind：`preference | decision | architecture | convention | bug_fix | dependency | todo`
- 读取：`prepare_context` 注入 Top-K（关键词 + 常驻 preference/convention）
- 写入：`extract_memory` 节点 Run 结束后抽取

## 6. 分阶段实施

| Phase | 内容 | 状态 |
|-------|------|------|
| 0 | broker delta 批量落库、to_thread、端口 TTL 缓存 | 已实施 |
| 1 | LangGraph 自定义图 + Checkpointer + stream_adapter | 已实施 |
| 2 | sliding window + compress + Conversation.summary | 已实施 |
| 3 | WorkspaceMemory + API + extract/retrieve | 已实施 |
| 4 | HITL 桥接、前端 lazy panels、applyEvent 优化、索引 | 已实施 |

## 7. 配置

```yaml
agent:
  sliding_window_size: 12
  compress_threshold_tokens: 90000
  use_legacy_react: false
  memory:
    enabled: true
    max_inject: 8
    extract_per_run: 3
```

## 8. 新增 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workspaces/{id}/memories` | 工作区记忆列表 |
| POST | `/api/workspaces/{id}/memories` | 手动添加记忆 |
| PATCH | `/api/workspaces/{id}/memories/{mid}` | 更新 |
| DELETE | `/api/workspaces/{id}/memories/{mid}` | 删除 |
