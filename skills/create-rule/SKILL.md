---
name: create-rule
description: 创建工作区级 Agent 规则（AGENTS.md 或 .code-agent/rules/*.md）。用户要添加编码规范、项目约定、持久化 AI 指引、或询问规则文件格式时使用。
license: Apache-2.0
metadata:
  author: code-agent
  version: "1.0"
---

# 创建规则

Code Agent 工作区规则用于持久注入系统上下文（FR-WS-09），让 agent 在每个会话中遵循项目约定。

## 规则文件位置

| 文件 | 作用域 |
| --- | --- |
| `{workspace}/AGENTS.md` | 工作区根，全局 agent 指引 |
| `{workspace}/.code-agent/rules/*.md` | 可按主题拆分的规则片段 |

规则会在组装上下文时注入（有长度上限），因此应**简洁、可执行**。

## 先收集需求

1. **目的**：要 enforce 什么行为或约定？
2. **范围**：全局 always-on，还是特定模块/文件类型？
3. **示例**：能否给出 ✅/❌ 代码示例？

若用户未说明范围，默认写入 `AGENTS.md`；规则较多或需分主题时拆到 `.code-agent/rules/`。

## AGENTS.md 格式

工作区根的单文件，Markdown 正文，无 frontmatter 要求：

```markdown
# Project Agent Rules

## Code style
- Use functional components in React
- Prefer explicit error handling over bare catch

## Testing
- Every bug fix needs a regression test
- Run `npm test` before finishing

## Git
- Do not commit unless explicitly asked
```

适合：项目级总则、启动方式、目录约定、团队 workflow。

## .code-agent/rules/*.md 格式

按主题拆分，文件名用 kebab-case：

```
.code-agent/rules/
├── typescript-standards.md
├── api-conventions.md
└── security.md
```

可选 YAML frontmatter（便于将来按 glob 过滤）：

```markdown
---
title: TypeScript Standards
globs: "**/*.{ts,tsx}"
---

# Error Handling

\`\`\`typescript
// ❌ BAD
try { await fetchData(); } catch (e) {}

// ✅ GOOD
try { await fetchData(); } catch (e) {
  logger.error('Failed to fetch', { error: e });
  throw new DataFetchError('Unable to retrieve data', { cause: e });
}
\`\`\`
```

| 字段 | 说明 |
| --- | --- |
| `title` | 规则标题（展示用） |
| `globs` | 可选，关联文件模式，供将来按上下文加载 |

## 与 Cursor Rules 的区别

| | Code Agent | Cursor |
| --- | --- | --- |
| 路径 | `AGENTS.md`、`.code-agent/rules/` | `.cursor/rules/*.mdc` |
| 格式 | Markdown | `.mdc` + `alwaysApply` / `globs` |

若用户从 Cursor 迁移，把 `.mdc` 正文迁到 `.code-agent/rules/`，去掉 Cursor 专有 frontmatter 或保留为注释。

## 写作原则

- **一条规则一个关注点**；过长则拆分
- **≤50 行** 为佳；总长受上下文上限约束
- **可执行**：写 agent 应做的，不写空话
- **带示例**：尤其是风格与错误处理类规则
- 不要重复 skill 里的流程性内容；规则是持久约束，skill 是任务 playbook

## 创建流程

1. 确认写入 `AGENTS.md` 还是 `.code-agent/rules/<name>.md`
2. 若文件已存在，**追加或整合**，不盲目覆盖
3. 写完后让用户知道规则会在下次会话生效
4. 规则过多时建议拆分并删除重复段落

## 校验清单

- [ ] 路径在工作区根内
- [ ] 内容简洁、无自相矛盾
- [ ] 含具体示例（如适用）
- [ ] 未包含密钥、令牌等敏感信息
