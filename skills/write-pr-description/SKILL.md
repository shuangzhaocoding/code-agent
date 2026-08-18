---
name: write-pr-description
description: 根据 git diff 写 PR 说明。用户要求提交说明、changelog、PR 正文时使用。
license: Apache-2.0
metadata:
  author: code-agent
  version: "1.0"
---

# 指令

1. 运行 git status 与 git diff。
2. 用中文写：摘要、动机、改动点、测试计划。
3. 不要执行 git commit，除非用户明确要求。
