.PHONY: api web install

install:
	cd apps/api && python3.11 -m pip install -e .
	cd apps/web && npm install

api:
	cd apps/api && python3.11 -m uvicorn code_agent.main:app --reload --host 127.0.0.1 --port 8000

web:
	cd apps/web && npm run dev

dev:
	@echo "Run make api and make web in two terminals."
