.PHONY: build run dev clean install help

# Default document root
DOC_ROOT ?= ./data/documents

help:  ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install:  ## Install backend and frontend dependencies
	uv sync
	cd frontend && npm install

build:  ## Build frontend for production
	cd frontend && npm run build

run: build  ## Build and run production server (single command)
	TEXTRACTOR_DOC_ROOT=$(DOC_ROOT) uv run textractor

dev-backend:  ## Run backend in development mode
	TEXTRACTOR_DOC_ROOT=$(DOC_ROOT) uv run textractor

dev-frontend:  ## Run frontend in development mode
	cd frontend && npm run dev

clean:  ## Remove build artifacts
	rm -rf frontend/dist

test:  ## Run backend tests
	uv run pytest

test-verbose:  ## Run backend tests with verbose output
	uv run pytest -v
