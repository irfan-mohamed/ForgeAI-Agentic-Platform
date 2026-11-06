.PHONY: up down build logs ps restart worker-logs kafka-ui qdrant-ui

## ── Start all services ───────────────────────────────────────────────────────
up:
	docker compose up -d

## ── Stop all services ────────────────────────────────────────────────────────
down:
	docker compose down

## ── Rebuild all images and start ─────────────────────────────────────────────
build:
	docker compose up -d --build

## ── Rebuild only the worker (fast iteration) ─────────────────────────────────
worker-rebuild:
	docker compose up -d --build worker

## ── View all logs ────────────────────────────────────────────────────────────
logs:
	docker compose logs -f

## ── View worker logs only ────────────────────────────────────────────────────
worker-logs:
	docker compose logs -f worker

## ── View repository service logs ─────────────────────────────────────────────
repo-logs:
	docker compose logs -f repository

## ── Show running containers ──────────────────────────────────────────────────
ps:
	docker compose ps

## ── Restart a specific service (usage: make restart s=worker) ────────────────
restart:
	docker compose restart $(s)

## ── Open Kafka UI in browser ─────────────────────────────────────────────────
kafka-ui:
	@echo "Kafka UI: http://localhost:8080"

## ── Open Qdrant dashboard in browser ────────────────────────────────────────
qdrant-ui:
	@echo "Qdrant UI: http://localhost:6333/dashboard"

## ── Stop and remove ALL volumes (full reset — WARNING: deletes all data) ─────
nuke:
	docker compose down -v --remove-orphans

## ── View AI service logs ─────────────────────────────────────────────────────
ai-logs:
	docker compose logs -f ai

## ── View frontend logs ───────────────────────────────────────────────────────
frontend-logs:
	docker compose logs -f frontend

## ── Run AI service tests ─────────────────────────────────────────────────────
test-ai:
	docker compose run --rm ai pytest tests/ -v

## ── Run API service tests ────────────────────────────────────────────────────
test-api:
	docker compose run --rm api pytest tests/ -v

## ── Run worker tests (inside Docker) ────────────────────────────────────────
test-worker:
	docker compose run --rm worker pytest tests/ -v

## ── Run repository service tests ─────────────────────────────────────────────
test-repo:
	docker compose run --rm repository pytest tests/ -v

## ── Connect to PostgreSQL shell ──────────────────────────────────────────────
psql:
	docker compose exec db psql -U forgeai -d forgeai

## ── Reset Qdrant knowledge collection (REST) ─────────────────────────────────
reset-qdrant:
	curl -X DELETE "http://localhost:6333/collections/repository_knowledge"

## ── List Kafka topics ─────────────────────────────────────────────────────────
kafka-topics:
	docker compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list
