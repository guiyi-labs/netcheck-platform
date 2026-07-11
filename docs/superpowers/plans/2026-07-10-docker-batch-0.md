# Docker Batch 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Docker-first project foundation for the network inspection platform.

**Architecture:** Use Docker Compose to run a FastAPI backend, static frontend, SQLite persistence volume, and demo target services. Keep business logic in a modular backend for this batch, while using container boundaries to present a microservice-style deployment.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, pytest, Nginx static frontend, Docker Compose.

---

## File Structure

- Create `backend/app/main.py`: FastAPI application factory and health endpoints.
- Create `backend/app/core/config.py`: environment-backed settings.
- Create `backend/app/core/database.py`: SQLite database engine/session bootstrap.
- Create `backend/app/models/base.py`: SQLAlchemy declarative base.
- Create `backend/app/api/routes.py`: API router registration.
- Create `backend/tests/test_health.py`: backend health endpoint tests.
- Create `backend/requirements.txt`: runtime and test dependencies.
- Create `backend/Dockerfile`: backend container image.
- Create `frontend/index.html`: initial Vue-powered dashboard shell.
- Create `frontend/nginx.conf`: frontend reverse proxy configuration.
- Create `frontend/Dockerfile`: frontend static image.
- Create `demo-services/web-ok/index.html`: normal HTTP target.
- Create `demo-services/web-error/default.conf`: HTTP 500 target.
- Create `demo-services/web-slow/app.py`: slow response target.
- Create `demo-services/web-slow/requirements.txt`: slow service dependency.
- Create `demo-services/web-slow/Dockerfile`: slow service image.
- Create `docker-compose.yml`: full batch 0 service orchestration.
- Create `.dockerignore`: Docker build exclusions.
- Create `README.md`: local startup and verification instructions.

## Task 1: Backend Health Foundation

**Files:**
- Create: `backend/tests/test_health.py`
- Create: `backend/app/main.py`
- Create: `backend/app/api/routes.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/database.py`
- Create: `backend/app/models/base.py`
- Create: `backend/requirements.txt`

- [ ] **Step 1: Write failing health tests**

```python
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint_reports_service_status():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "netcheck-backend",
        "version": "0.1.0",
    }


def test_api_health_endpoint_reports_database_url():
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"].startswith("sqlite:///")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest backend/tests/test_health.py -q`

Expected: FAIL because `app.main` does not exist yet.

- [ ] **Step 3: Implement minimal backend application**

Create the backend app, settings, API router, and database bootstrap with the exact service/version values tested above.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest backend/tests/test_health.py -q`

Expected: 2 passed.

## Task 2: Docker Compose Foundation

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/index.html`
- Create: `frontend/nginx.conf`
- Create: `frontend/Dockerfile`
- Create: `demo-services/web-ok/index.html`
- Create: `demo-services/web-error/default.conf`
- Create: `demo-services/web-slow/app.py`
- Create: `demo-services/web-slow/requirements.txt`
- Create: `demo-services/web-slow/Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Add Compose and Docker files**

Create services `netcheck-backend`, `netcheck-frontend`, `demo-web-ok`, `demo-web-error`, and `demo-web-slow` on network `netcheck-lab`, with named volumes for `db_data`, `report_data`, and `backend_logs`.

- [ ] **Step 2: Validate Compose syntax**

Run: `docker compose config`

Expected when Docker is installed: exit 0 and rendered Compose config.

If Docker is not installed, record the blocker and continue with non-Docker verification.

## Task 3: Documentation

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write startup instructions**

Document `docker compose up -d --build`, service URLs, fallback local backend test command, and the known Windows Docker network boundary for real LAN scanning.

- [ ] **Step 2: Verify documentation references existing files**

Run: `Test-Path README.md; Test-Path docker-compose.yml; Test-Path backend/app/main.py`

Expected: all values are `True`.

## Self-Review

- Spec coverage: covers Docker Compose infrastructure, backend health, frontend entry, demo target services, volumes, and startup docs.
- Placeholder scan: no unfinished placeholder markers are allowed.
- Type consistency: service names use `netcheck-backend`, `netcheck-frontend`, `demo-web-ok`, `demo-web-error`, and `demo-web-slow` consistently.
