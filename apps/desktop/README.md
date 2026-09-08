# Code Agent Desktop (Electron)

Windows 包内嵌 **embeddable CPython + 依赖 wheels**，目标机无需安装 Python。

启动时会改写 `python*._pth`，把 `apps/api` 写入 sys.path（embeddable 会忽略 `PYTHONPATH`）。
桌面默认 **split**：同时拉起 `api` / `worker` / `terminal` / `preview`，并强制
`CODE_AGENT_RUNTIME_PROFILE=split`、`AGENT_WORKER=external`、terminal/preview `standalone`。
Windows 终端依赖打包进 runtime 的 `pywinpty`（ConPTY）。
工作空间浏览支持磁盘根列表；桌面端可用系统「选择文件夹」对话框。

## 打包

```bash
make desktop-win
# 产物：apps/desktop/release/CodeAgent-*-win-x64.zip
```

解压后直接运行 `Code Agent.exe`。若启动失败，弹窗会附带后端日志尾部。

## 开发

```bash
make build
cd apps/desktop && npm start   # 开发态仍可用系统 python3.11
```

## 说明

- 运行时目录：`apps/desktop/runtime/python-win/`（打包脚本生成，不进 git）
- Electron 启动时优先使用 `resources/python-win/python.exe`
- 通过 `PYTHONPATH=apps/api` 加载 `code_agent` 源码
