.PHONY: api web install build prod start dev worker terminal-svc preview-svc split up down restart status desktop desktop-win desktop-linux desktop-mac

API_PORT ?= 4060
DEV_UI_PORT ?= 4061
TERM_PORT ?= 4062
PREVIEW_PORT ?= 4063
RUNTIME_PROFILE ?=

install:
	cd apps/api && python3.11 -m pip install -e .
	cd apps/web && npm install

install-split:
	cd apps/api && python3.11 -m pip install -e ".[split]"

init:
	cd apps/api && python3.11 -m code_agent init-config $(if $(FORCE),--force,)

api:
	cd apps/api && python3.11 -m code_agent monolith

api-gateway:
	cd apps/api && python3.11 -m code_agent api

worker:
	cd apps/api && python3.11 -m code_agent worker

terminal-svc:
	cd apps/api && CODE_AGENT_RUNTIME_PROFILE=split python3.11 -m code_agent terminal

preview-svc:
	cd apps/api && CODE_AGENT_RUNTIME_PROFILE=split python3.11 -m code_agent preview

split:
	@echo "Split mode: start api, worker, terminal-svc, preview-svc in separate terminals"
	@echo "  make api-gateway  # API gateway :$(API_PORT)"
	@echo "  make worker       # Agent worker"
	@echo "  make terminal-svc # Terminal :$(TERM_PORT)"
	@echo "  make preview-svc  # Preview :$(PREVIEW_PORT)"
	@echo "  make web-split    # Vite :$(DEV_UI_PORT) proxies /api/* to the ports above"
	@echo "Set runtime.profile=split and terminal/preview mode=standalone in ~/.code-agent/config.yaml"

web:
	cd apps/web && CODE_AGENT_PORT=$(API_PORT) CODE_AGENT_DEV_UI_PORT=$(DEV_UI_PORT) \
	  CODE_AGENT_RUNTIME_PROFILE=$(RUNTIME_PROFILE) \
	  CODE_AGENT_TERMINAL_PORT=$(TERM_PORT) CODE_AGENT_PREVIEW_PORT=$(PREVIEW_PORT) \
	  npm run dev

web-split:
	$(MAKE) web RUNTIME_PROFILE=split

build:
	cd apps/web && npm run build

prod: build
	@echo "Code Agent: http://127.0.0.1:$(API_PORT)"
	cd apps/api && python3.11 -m code_agent start --prod

# 一键：安装依赖 → 编译前端 → 启动（生产模式）
start: install
	cd apps/api && python3.11 -m code_agent start --prod --build

dev:
	@echo "Development: code-agent start | stop | restart"
	@echo "Production:  code-agent start --prod | stop | restart"
	@echo "API:  http://127.0.0.1:$(API_PORT)"
	@echo "Web:  http://127.0.0.1:$(DEV_UI_PORT)"

# 开发：后台启动（自动识别 split / monolith）
up:
	cd apps/api && python3.11 -m code_agent start

down:
	cd apps/api && python3.11 -m code_agent stop

restart:
	cd apps/api && python3.11 -m code_agent restart

status:
	cd apps/api && python3.11 -m code_agent status

# Electron 桌面预览（需先 build 前端）
desktop: build
	cd apps/desktop && npm install && npm start

# 交叉打包 Windows：NSIS 安装向导（自定义路径/快捷方式）+ zip 便携包
# Linux 上构建 NSIS 需 wine/wine32；无显示器时可用 xvfb-run
desktop-win: build
	cd apps/desktop && npm install && \
	  if command -v xvfb-run >/dev/null 2>&1 && [ "$$(uname -s)" = Linux ]; then \
	    xvfb-run -a npm run pack:win; \
	  else \
	    npm run pack:win; \
	  fi
	@echo "Windows installer + zip: apps/desktop/release/"
	@ls -lah apps/desktop/release/ | sed -n '1,30p'

# Linux AppImage + deb（开始菜单快捷方式）+ tar.gz（需在 Linux 主机打包）
desktop-linux: build
	cd apps/desktop && npm install && npm run pack:linux
	@echo "Linux artifacts: apps/desktop/release/"
	@ls -lah apps/desktop/release/ | sed -n '1,40p'

# macOS dmg（拖到 Applications）+ zip（须在 macOS 主机打包）
desktop-mac: build
	cd apps/desktop && npm install && npm run pack:mac
	@echo "macOS artifacts: apps/desktop/release/"
	@ls -lah apps/desktop/release/ | sed -n '1,40p'
