---
title: CampusX
emoji: 🎓
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: mit
---

# CampusX — Smart Campus Learning Platform

**Tagline:** *"Learn Smarter. Search Faster. Powered by AI."*  
**Version:** 1.0 (Production-Ready Architecture)

---

## 🚀 Architectural Overview

CampusX is an enterprise AI-powered academic intelligence platform engineered for higher education institutions.

### Tech Stack
- **Database**: PostgreSQL 16 (50 ORM tables, UUID PKs, Soft Delete, BCNF)
- **Primary LLM**: Anthropic Claude (`claude-sonnet-4-6`)
- **Fallback LLM**: OpenAI `gpt-4o-mini`
- **Embeddings**: `text-embedding-3-large` (3072-dim)
- **Vector DB**: Qdrant Vector Store (payload filtering by institution/subject)
- **Backend Core**: Flask 3.x + SQLAlchemy 2.x + Celery + Redis
- **Auth**: JWT (15-min access) + Refresh Tokens (14 days) + Argon2id
- **UI/UX**: Lumina Design System (Dark/Light mode, Glassmorphism, 40+ screens)

---

## 📁 Directory Structure

```
campusx/
├── app/
│   ├── blueprints/    # Web routes & REST API v1 endpoints
│   ├── exceptions/    # Custom exception hierarchy
│   ├── middleware/    # Auth, Audit, Security headers, Rate limiter
│   ├── models/        # 50+ SQLAlchemy 2.x ORM models
│   ├── permissions/   # RBAC with 6 roles
│   ├── repositories/  # Repository pattern (select() API)
│   ├── schemas/       # Marshmallow request/response validation
│   ├── services/      # Domain logic & AI/RAG pipeline
│   ├── static/        # Lumina CSS & Alpine.js frontend assets
│   ├── tasks/         # Celery async background jobs
│   ├── templates/     # 40+ Jinja2 HTML views
│   └── utils/         # Response envelopes, hashing, crypto
├── docker/            # Dockerfiles & Nginx proxy configs
├── docs/              # OpenAPI specs & Onboarding docs
├── migrations/        # Alembic schema migrations
├── scripts/           # Synthetic development seed data
├── tests/             # pytest suite
├── docker-compose.yml # 7 microservices orchestration
└── Makefile           # Development workflow automation
```

---

## ⚡ Quick Start

```bash
# Copy configuration
cp .env.example .env

# Launch infrastructure
make up

# Seed synthetic test data
make seed
```

Access the app at `http://localhost:5000`.
