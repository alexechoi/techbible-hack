.PHONY: dev frontend backend

dev:
	@echo "Starting frontend and backend..."
	$(MAKE) frontend & $(MAKE) backend & wait

frontend:
	cd next-app && npm run dev

backend:
	cd backend && uv run uvicorn main:app --reload
