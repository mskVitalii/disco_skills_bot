.PHONY: help install env up down logs db-init db-migrate db-reset dev lint

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  install      Install dependencies via uv"
	@echo "  env          Copy .env.example → .env"
	@echo ""
	@echo "  up           Start postgres + redis in background"
	@echo "  down         Stop and remove containers"
	@echo "  logs         Tail docker-compose logs"
	@echo ""
	@echo "  db-init      Init aerich + create tables (first time only)"
	@echo "  db-migrate   Generate a new migration (MSG=description)"
	@echo "  db-upgrade   Apply pending migrations"
	@echo "  db-reset     Drop containers+volumes, recreate DB from scratch"
	@echo ""
	@echo "  dev          Start bot locally in polling mode"
	@echo "  lint         Run ruff check + format"

install:
	uv sync

env:
	cp .env.example .env

up:
	docker compose up -d postgres redis

down:
	docker compose down

logs:
	docker compose logs -f

db-init: up
	uv run aerich init -t app.core.database.TORTOISE_ORM
	uv run aerich init-db

db-migrate:
	uv run aerich migrate --name "$(MSG)"

db-upgrade:
	uv run aerich upgrade

db-reset:
	docker compose down -v
	docker compose up -d postgres redis
	@echo "Waiting for postgres..."
	@sleep 3
	uv run aerich upgrade

dev: up
	uv run python main.py

lint:
	uv run ruff check . --fix
	uv run ruff format .
