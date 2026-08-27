.PHONY: api web install build prod start dev

API_PORT ?= 4060
DEV_UI_PORT ?= 4061

install:
	cd apps/api && python3.11 -m pip install -e .
	cd apps/web && npm install

api:
	cd apps/api && python3.11 -m uvicorn code_agent.main:app --reload --host 127.0.0.1 --port $(API_PORT)

web:
	cd apps/web && CODE_AGENT_PORT=$(API_PORT) CODE_AGENT_DEV_UI_PORT=$(DEV_UI_PORT) npm run dev

build:
	cd apps/web && npm run build

prod: build
	@echo "Code Agent: http://127.0.0.1:$(API_PORT)"
	cd apps/api && python3.11 -m uvicorn code_agent.main:app --host 127.0.0.1 --port $(API_PORT)

# 一键：安装依赖 → 编译前端 → 启动（单进程生产模式）
start: install prod

dev:
	@echo "Run make api and make web in two terminals."
	@echo "API:  http://127.0.0.1:$(API_PORT)"
	@echo "Web:  http://127.0.0.1:$(DEV_UI_PORT)"
