# Code Agent Desktop (Electron)

各平台包内嵌 **独立 CPython + 依赖 wheels**，目标机无需安装 Python。

- **Windows**：官方 embeddable CPython；启动时改写 `python*._pth`，把 `apps/api` 写入 sys.path（embeddable 会忽略 `PYTHONPATH`）。终端依赖打包进 runtime 的 `pywinpty`（ConPTY）。
- **Linux / macOS**：[python-build-standalone](https://github.com/astral-sh/python-build-standalone) `install_only_stripped`；通过 `PYTHONPATH=apps/api` 加载源码。

桌面默认 **split**：同时拉起 `api` / `worker` / `terminal` / `preview`，并强制
`CODE_AGENT_RUNTIME_PROFILE=split`、`AGENT_WORKER=external`、terminal/preview `standalone`。
工作空间浏览支持磁盘根列表；桌面端可用系统「选择文件夹」对话框。

## 打包

```bash
make desktop-win      # 可在 Linux 交叉构建：NSIS 安装包 + zip
make desktop-linux    # 须在 Linux 主机：AppImage + deb + tar.gz
make desktop-mac      # 须在 macOS 主机：dmg + zip
```

产物目录：`apps/desktop/release/`

| 命令 | 典型产物 | 安装体验 |
|------|----------|----------|
| `desktop-win` | `.exe`（NSIS）+ `.zip` | **引导安装**：语言选择、自定义目录、桌面/开始菜单快捷方式、卸载项；zip 为免安装便携包 |
| `desktop-linux` | `.AppImage` / `.deb` / `.tar.gz` | AppImage 直接运行；**deb** 写入系统并注册开始菜单；tar.gz 解压即用（无自定义路径向导） |
| `desktop-mac` | `.dmg` / `.zip` | **dmg** 拖到 Applications；系统不提供 Windows 式自定义路径安装向导 |

### Windows 安装向导（NSIS）

`oneClick: false`，支持：

- 中/英语言选择
- 自定义安装路径
- 创建桌面快捷方式、开始菜单快捷方式
- 安装完成后可立即启动
- 「添加或删除程序」中卸载（默认保留用户数据）

仅装安装包：`cd apps/desktop && npm run pack:win:installer`  
仅便携 zip：`npm run pack:win:portable`

在 **Linux 上交叉打 NSIS** 需要：`wine` + `wine32`（提取卸载器），无图形环境时建议加 `xvfb`。在 **Windows 本机** 打包无需 Wine。

可选环境变量：

- `CODE_AGENT_PBS_TAG` / `CODE_AGENT_PBS_PYTHON`：覆盖 standalone 发布 tag / 版本
- `CODE_AGENT_PBS_URL`：强制指定完整下载 URL（跳过镜像）
- `CODE_AGENT_PBS_MIRROR`：自定义镜像前缀（默认 `ghfast.top` 代理）
- macOS 指定架构：`npm run pack:mac:arm64` / `npm run pack:mac:x64`

## 开发

```bash
make build
cd apps/desktop && npm start   # 开发态可用系统 python3.11，或已生成的 runtime/python-*
```

## 说明

- 运行时目录（打包脚本生成，不进 git）：
  - `apps/desktop/runtime/python-win/`
  - `apps/desktop/runtime/python-linux/`
  - `apps/desktop/runtime/python-macos/`
- 打包后统一落在 `resources/python/`（Windows 为 `python.exe`，Unix 为 `bin/python3`）
- 通过 `PYTHONPATH=apps/api`（及 Windows `._pth`）加载 `code_agent` 源码
