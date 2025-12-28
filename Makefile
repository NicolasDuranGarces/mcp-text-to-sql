# =============================================================================
# MCP Text-to-SQL Makefile
# =============================================================================
# Development commands for building, testing, and running the MCP server

.PHONY: help build up down restart logs shell test test-unit test-integration lint format clean

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[34m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
RESET := \033[0m

# -----------------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------------
help: ## Show this help message
	@echo "$(BLUE)MCP Text-to-SQL Development Commands$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'

# -----------------------------------------------------------------------------
# Docker Commands
# -----------------------------------------------------------------------------
build: ## Build Docker images
	@echo "$(BLUE)Building Docker images...$(RESET)"
	docker compose build

up: ## Start all services
	@echo "$(BLUE)Starting services...$(RESET)"
	docker compose up -d
	@echo "$(GREEN)Services started! Server running at http://localhost:8000$(RESET)"

up-logs: ## Start all services with logs
	@echo "$(BLUE)Starting services with logs...$(RESET)"
	docker compose up

down: ## Stop all services
	@echo "$(YELLOW)Stopping services...$(RESET)"
	docker compose down

restart: down up ## Restart all services

logs: ## View logs from all services
	docker compose logs -f

logs-server: ## View logs from MCP server only
	docker compose logs -f mcp-server

shell: ## Open a shell in the MCP server container
	docker compose exec mcp-server /bin/bash

# -----------------------------------------------------------------------------
# Development Commands
# -----------------------------------------------------------------------------
install: ## Install dependencies locally (for IDE support)
	@echo "$(BLUE)Creating virtual environment...$(RESET)"
	python -m venv .venv
	@echo "$(BLUE)Installing dependencies...$(RESET)"
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	@echo "$(GREEN)Done! Activate with: source .venv/bin/activate$(RESET)"

dev: ## Run server in development mode (locally)
	@echo "$(BLUE)Starting development server...$(RESET)"
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# -----------------------------------------------------------------------------
# Testing Commands
# -----------------------------------------------------------------------------
test: ## Run all tests
	@echo "$(BLUE)Running all tests...$(RESET)"
	docker compose exec mcp-server pytest tests/ -v --cov=src --cov-report=term-missing

test-unit: ## Run unit tests only
	@echo "$(BLUE)Running unit tests...$(RESET)"
	docker compose exec mcp-server pytest tests/unit -v --cov=src

test-integration: ## Run integration tests only
	@echo "$(BLUE)Running integration tests...$(RESET)"
	docker compose exec mcp-server pytest tests/integration -v

test-local: ## Run tests locally (without Docker)
	@echo "$(BLUE)Running tests locally...$(RESET)"
	pytest tests/ -v --cov=src --cov-report=term-missing

# -----------------------------------------------------------------------------
# Code Quality Commands
# -----------------------------------------------------------------------------
lint: ## Run linter (ruff)
	@echo "$(BLUE)Running linter...$(RESET)"
	ruff check src/ tests/

lint-fix: ## Run linter with auto-fix
	@echo "$(BLUE)Running linter with auto-fix...$(RESET)"
	ruff check src/ tests/ --fix

format: ## Format code with black
	@echo "$(BLUE)Formatting code...$(RESET)"
	black src/ tests/

format-check: ## Check code formatting
	@echo "$(BLUE)Checking code format...$(RESET)"
	black src/ tests/ --check

typecheck: ## Run type checker (mypy)
	@echo "$(BLUE)Running type checker...$(RESET)"
	mypy src/

quality: lint format-check typecheck ## Run all quality checks

# -----------------------------------------------------------------------------
# Database Commands
# -----------------------------------------------------------------------------
db-shell-pg: ## Open PostgreSQL shell
	docker compose exec postgres-test psql -U mcp_user -d mcp_test

db-shell-mongo: ## Open MongoDB shell
	docker compose exec mongo-test mongosh -u mcp_user -p mcp_password --authenticationDatabase admin mcp_test

# -----------------------------------------------------------------------------
# Cleanup Commands
# -----------------------------------------------------------------------------
clean: ## Remove build artifacts and caches
	@echo "$(YELLOW)Cleaning up...$(RESET)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .coverage htmlcov/ 2>/dev/null || true
	@echo "$(GREEN)Cleanup complete!$(RESET)"

clean-docker: ## Remove Docker volumes and images
	@echo "$(RED)Removing Docker volumes and images...$(RESET)"
	docker compose down -v --rmi local
	@echo "$(GREEN)Docker cleanup complete!$(RESET)"

clean-all: clean clean-docker ## Remove everything (artifacts + Docker)
