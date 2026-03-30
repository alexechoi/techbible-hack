.PHONY: dev frontend backend

dev:
	@echo "Starting frontend and backend..."
	$(MAKE) frontend & $(MAKE) backend & wait

frontend:
	cd next-app && npm run dev

backend:
	uv run --project backend python -m uvicorn backend.main:app --reload
