# Nexus — Identity, Multi-Tenant y Platform Kernel

Nexus es una plataforma SaaS API-first. El repositorio contiene el Módulo 1 de identidad y multi-tenancy y el Módulo 2 Platform Kernel: Stores, Sites, Sales Channels, Environments, Markets, scopes, RLS, outbox/inbox, idempotencia, jobs, operations, cuotas y observabilidad.

## Estado de los módulos

- **Estado Módulo 1: CERRADO**
- **Estado Módulo 2: CERRADO**

| Campo | Evidencia de cierre |
|---|---|
| Repositorio | `ippiX1992/nexus` |
| Commit validado | `49bfea76ff2c940e2e56ee41d37dfbef1fc7b38d` |
| Workflow | `Nexus Modules 1-2 Quality Gate` |
| Run ID | `29365183544` |
| Resultado | `success` |
| Fecha de validación | `2026-07-14` |

Los jobs `backend-quality`, `frontend-quality`, `playwright-e2e` y `modules-1-2-gate` finalizaron correctamente en GitHub-hosted. La matriz local equivalente obtuvo 47 pruebas backend aprobadas, 81.00% de cobertura, Ruff y mypy aprobados, 13 pruebas frontend aprobadas y 1 omitida, E2E Chromium real aprobado, wheel/sdist backend y build Next.js correctos. El run conservó los artifacts `nexus-backend-evidence` y `nexus-playwright-evidence`.

El cierre no elimina la deuda residual: permanecen dos vulnerabilidades npm moderadas, la migración histórica `0001` dependiente de metadata dinámica, auditoría no criptográficamente inmutable, necesidad de supervisar dispatcher/workers en producción y tareas de limpieza programada todavía pendientes.

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
