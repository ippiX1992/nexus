# Nexus — Identity, Multi-Tenant y Platform Kernel

Nexus es una plataforma SaaS API-first. El repositorio contiene el Módulo 1 de identidad y multi-tenancy y el Módulo 2 Platform Kernel: Stores, Sites, Sales Channels, Environments, Markets, scopes, RLS, outbox/inbox, idempotencia, jobs, operations, cuotas y observabilidad.

## PostgreSQL de pruebas sin Docker

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python scripts/setup_test_db.py
.\.venv\Scripts\python scripts/run_integration_tests.py
```

## Validación

```powershell
.\.venv\Scripts\python -m pytest -q --cov=app --cov-report=term-missing --cov-report=xml --cov-report=html --cov-fail-under=80
.\.venv\Scripts\python -m ruff check app tests scripts --select F,I,UP,B
.\.venv\Scripts\python -m mypy --no-incremental app
cd frontend
npm.cmd ci
npm.cmd test
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
npm.cmd run test:e2e
```

El E2E requiere backend y frontend activos y las variables descritas en `docs/modules/02-platform-kernel.md`. El workflow de GitHub Actions prepara PostgreSQL, inicia ambos servicios y ejecuta Chromium automáticamente.

## Docker

```powershell
Copy-Item .env.example .env
docker compose up --build
```

API: `http://localhost:8000` · OpenAPI: `http://localhost:8000/docs` · frontend: `http://localhost:3000`.

Arquitectura y módulos:

- [Arquitectura maestra](docs/architecture/MASTER_ARCHITECTURE.md)
- [Módulo 1 — Identidad y Multi-Tenant](docs/modules/01-identity-tenancy.md)
- [Módulo 2 — Platform Kernel](docs/modules/02-platform-kernel.md)
