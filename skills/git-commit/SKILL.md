---
name: git-commit
description: 根据 staged/unstaged 改动生成规范 git commit message。用户要求写提交说明、commit message、或准备 git commit 时使用；不执行 commit 除非用户明确要求。
license: Apache-2.0
metadata:
  author: code-agent
  version: "1.0"
---

# 生成 Commit Message

## 指令

1. 运行 `git status` 与 `git diff`（必要时 `git diff --staged`）。
2. 理解改动意图，而非逐文件罗列。
3. 生成 commit message，格式：

```
<type>(<scope>): <subject>

<body — 可选，说明动机与关键改动>

<footer — 可选，Breaking changes / issue refs>
```

4. **不要执行 `git commit`**，除非用户明确要求提交。

## type 参考

| type | 用途 |
| --- | --- |
| feat | 新功能 |
| fix | 缺陷修复 |
| refactor | 重构，不改行为 |
| test | 测试 |
| docs | 文档 |
| chore | 构建、依赖、杂项 |
| perf | 性能 |

## 原则

- subject ≤72 字符，祈使语气（「add」而非「added」）
- 一个 commit 一个逻辑变更；若 diff 混杂多主题，建议用户拆分
- 遵循仓库已有 commit 风格（先 `git log -5`）
