.PHONY: build run dev clean install help docker-build docker-up docker-down docker-logs docker-restart docker-shell docker-clean docker-test

SHELL := /bin/bash

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

# Docker commands
docker-build:  ## Build Docker image
	docker build -t textractor:latest .

docker-up:  ## Start application with docker-compose
	docker compose up -d

docker-down:  ## Stop docker-compose containers
	docker compose down

docker-logs:  ## View container logs
	docker compose logs -f

docker-restart:  ## Restart containers
	docker compose restart

docker-shell:  ## Open shell in running container
	docker compose exec textractor /bin/bash

docker-clean:  ## Remove containers and volumes (WARNING: deletes data)
	@echo "WARNING: This will delete all container data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker compose down -v; \
		docker volume rm textractor-data 2>/dev/null || true; \
	fi

docker-test:  ## Test Docker build
	docker build -t textractor:test .
	@echo "Docker build successful"
