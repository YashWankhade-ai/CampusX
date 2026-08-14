# CampusX Developer Onboarding & Local Setup

Welcome to CampusX — *"Learn Smarter. Search Faster. Powered by AI."*

## Prerequisites
- **Python**: 3.12+
- **Docker**: Docker Desktop (Engine 24+, Compose v2+)
- **API Keys** (in `.env`): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`

## Quickstart

```bash
# 1. Clone/Navigate to workspace
cd campusx

# 2. Setup environment file
cp .env.example .env

# 3. Start local microservices (Postgres 16, Redis 7, MinIO, Qdrant, App, Worker)
make up

# 4. Initialize Database & Seed Synthetic Data
make seed

# 5. Access Application
# Web Interface: http://localhost:5000
# API Endpoint:  http://localhost:5000/api/v1
# MinIO Console: http://localhost:9001
# Qdrant Dashboard: http://localhost:6333/dashboard
```

## Architecture Summary
- **Backend Framework**: Flask 3.x + SQLAlchemy 2.x + Alembic
- **Primary LLM**: Anthropic Claude (`claude-sonnet-4-6`) via `anthropic` SDK
- **Fallback LLM**: OpenAI `gpt-4o-mini`
- **Embedding Model**: OpenAI `text-embedding-3-large` (3072-dimensional)
- **Vector DB**: Qdrant Cloud / Self-hosted
- **Task Queue**: Celery 5.x + Redis 7
- **UI System**: Lumina Design System (Vanilla CSS + Alpine.js + Jinja2)
