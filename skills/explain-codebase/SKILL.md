---
name: explain-codebase
description: 解释当前工作区如何组织、如何启动与关键模块。在用户问「这项目怎么跑 / 架构是什么」时使用。
license: Apache-2.0
metadata:
  author: code-agent
  version: "1.0"
---

# 指令

1. 先读 README、pyproject.toml / package.json、Makefile。
2. 用 glob / grep 定位入口（main.py、App.vue）。
3. 用不超过 12 条要点说明：如何启动、目录职责、改代码该从哪下手。
4. 不要修改文件。
