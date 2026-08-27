---
name: create-skill
description: 创建 Code Agent Skill。用户要新建 skill、编写 SKILL.md、或询问 skill 目录结构、发现路径、校验规则时使用。
license: Apache-2.0
metadata:
  author: code-agent
  version: "1.0"
---

# 创建 Skill

## 先收集需求

1. **用途**：这个 skill 解决什么任务？
2. **存放位置**：内置 / 用户级 / 工作区级？
3. **触发场景**：用户说什么话时应加载此 skill？
4. **约束**：是否只读、是否允许改代码、输出格式？

能从对话推断时直接推断，只问缺失项。

## 目录与命名

```
skill-name/
├── SKILL.md          # 必需
├── references/       # 可选，详细文档
└── scripts/          # 可选，经 run_command 执行
```

- 目录名 = frontmatter 的 `name`（kebab-case，≤64 字符）
- `name` 只允许小写字母、数字、连字符

## 存放路径（优先级从低到高，同名后者覆盖）

| 来源 | 路径 | UI 标签 |
| --- | --- | --- |
| 内置 | `{repo}/skills/` | 内置 |
| 用户 | `~/.code-agent/skills/` | 用户 |
| Cursor | `{workspace}/.cursor/skills/` | Cursor |
| 工作区 | `{workspace}/.code-agent/skills/` | 工作区 |
| Agents | `{workspace}/.agents/skills/` | Agents |

**推荐**：团队共享放工作区 `.code-agent/skills/` 或 `.agents/skills/`；个人通用放 `~/.code-agent/skills/`。

## SKILL.md 格式

```markdown
---
name: my-skill
description: 做什么、何时用。第三人称，含触发词，≤1024 字符。
license: Apache-2.0
metadata:
  author: code-agent
  version: "1.0"
---

# 指令

1. 步骤一
2. 步骤二
```

### 必填字段

| 字段 | 要求 |
| --- | --- |
| `name` | 与目录名一致，kebab-case |
| `description` | 非空；写清 **做什么** 和 **何时用**；第三人称 |

### 正文原则

- 简洁：只写 agent 不知道的信息
- SKILL.md 建议 ≤500 行；细节放 `references/`
- 复杂流程用 checklist；质量关键任务加验证步骤
- 用户提供的原文若要求 verbatim，原样写入，不 paraphrase

## 创建流程

1. 确定 `name` 与存放路径
2. 创建 `{name}/SKILL.md`
3. 校验：frontmatter 完整、目录名匹配、description 含触发词
4. 告知用户如何在 Skills 面板查看，以及如何用 `load_skill` 激活

## 反模式

- 不要把 skill 写到 `~/.cursor/skills-cursor/`（Cursor 内置目录）
- 不要省略 YAML frontmatter（否则不会被发现）
- 不要在 description 里写「我可以帮你…」

## 示例 description

```yaml
# 好
description: 根据 git diff 生成规范 commit message。用户要求写提交说明、commit message、或准备 git commit 时使用。

# 差
description: 帮助写 commit
```
