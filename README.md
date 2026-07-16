# Nexus — Identity, Platform Kernel y Catalog Foundation

Nexus es una plataforma SaaS API-first. Sobre los Módulos 1 y 2 cerrados, `main` incorpora M3.0 Catalog Foundation: Products/Variants, clasificación, localización básica y asignación multi-Store con los servicios transversales del Platform Kernel.

## Estado de los módulos

- **Estado Módulo 1: CERRADO**
- **Estado Módulo 2: CERRADO**
- **Módulo 3: EN PROGRESO**
- **Incremento M3.0 Catalog Foundation: CERRADO**

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

## Estado de Catalog Foundation

M3.0 implementa 12 tablas con FORCE RLS, 27 paths/40 operaciones API, 18 permisos, 21 eventos outbox, idempotencia, `If-Match`, entitlements, auditoría, administración web y E2E real. Product y su Variant default se crean atómicamente; SKU e identificadores permanecen reservados tras archive; Category usa closure table y Product–Store no equivale a publicación.

**M3.0 Catalog Foundation: CERRADO.** [Pull Request #1](https://github.com/ippiX1992/nexus/pull/1) (`feature/catalog-core` → `main`) fue integrado mediante merge commit `59859c3eda062fde38d4d75dc5b6fde565ada4f0`. El quality gate GitHub-hosted corrió en verde tres veces sobre el mismo contenido — push a la rama, evento del Pull Request y push del commit integrado en `main` (run `29465055151`, 4/4 jobs: backend quality/PostgreSQL/RLS/Catalog, frontend tests/lint/typecheck/build, Playwright E2E, gate final) — con artifacts `nexus-catalog-foundation-backend-evidence` y `nexus-catalog-foundation-playwright-evidence`. Evidencia local: 71 pruebas backend aprobadas, cobertura de 80.97%, Ruff y mypy aprobados, 20 pruebas frontend aprobadas y 1 omitida, pruebas PostgreSQL/RLS/concurrencia/migraciones y 2 flujos E2E en Chromium real. El tag `module-3-catalog-foundation-v0.1.0-rc.1` se conserva sin modificar; el tag final `module-3-catalog-foundation-v0.1.0` se corta sobre el commit de cierre documental.

Riesgos residuales sin resolver por este cierre: dos vulnerabilidades npm moderadas, migración histórica `0001` dependiente de metadata dinámica, auditoría no criptográficamente inmutable, dispatcher/jobs sin supervisión en producción, limpieza programada pendiente, y `main` sin branch protection configurada (recomendado como tarea prioritaria: PR obligatorio, checks obligatorios, prohibición de force push y de eliminar `main`, conversaciones resueltas antes de mergear, al menos una aprobación cuando haya más colaboradores).

Los incrementos M3.1–M3.7 continúan pendientes. No están implementados Options, Attributes, Metafields, Collections, Tags, media, imports, Search, publicación, Pricing ni Inventory.

Detalle y evidencia: [M3.0 — Catalog Foundation](docs/modules/03-catalog-foundation.md).

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
.\.venv\Scripts\python -m ruff check app tests scripts
.\.venv\Scripts\python -m mypy --no-incremental app
cd frontend
npm.cmd ci
npm.cmd test
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
npm.cmd run test:e2e
```

El E2E requiere backend y frontend activos y las variables descritas en los documentos de los Módulos 2 y 3. El workflow de GitHub Actions prepara PostgreSQL, inicia ambos servicios y ejecuta Chromium automáticamente.

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
- [Módulo 3 — plan de Catalog Core](docs/modules/03-catalog-core-plan.md)
- [M3.0 — Catalog Foundation](docs/modules/03-catalog-foundation.md)
