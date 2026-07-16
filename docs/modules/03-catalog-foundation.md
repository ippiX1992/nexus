# Módulo 3 — Catalog Foundation

> Estado del módulo: **Módulo 3: EN PROGRESO**.
> Estado del incremento: **Incremento M3.0 Catalog Foundation: CERRADO**.
> Rama de origen: `feature/catalog-core` (integrada y cerrada).
> Fecha de evidencia local: `2026-07-14`. Fecha de cierre: `2026-07-16`.
> Pull Request: [#1](https://github.com/ippiX1992/nexus/pull/1), `feature/catalog-core` → `main`, merge commit `59859c3eda062fde38d4d75dc5b6fde565ada4f0`.
> GitHub-hosted: quality gate verde en las tres instancias del mismo contenido — push a la rama (run `29464039820`), evento del Pull Request (run `29464236414`) y push del commit integrado en `main` (run `29465055151`) — 4/4 jobs cada vez: backend quality/PostgreSQL/RLS/Catalog, frontend tests/lint/typecheck/build, Playwright E2E, gate final. Artifacts: `nexus-catalog-foundation-backend-evidence`, `nexus-catalog-foundation-playwright-evidence`.
> Tag RC (sin modificar): `module-3-catalog-foundation-v0.1.0-rc.1` → `47fad54`. Tag final: `module-3-catalog-foundation-v0.1.0`, sobre el commit de cierre documental.

## 1. Alcance entregado

M3.0 incorpora el primer vertical operativo de Catalog sobre Identity/Multi-Tenant y Platform Kernel, sin reescribirlos. El master Product pertenece al tenant y puede asociarse a varias Stores; `active` expresa estado editorial y nunca significa publicado.

Incluye:

- Product Types, Brands, Products y Variant default atómica;
- Variants explícitas con SKU tenant-wide no reutilizable;
- identificadores `ean`, `upc`, `isbn`, `mpn` y `external`;
- traducciones básicas y SEO por locale habilitado;
- Taxonomies, Categories y closure table transaccional;
- asignaciones Product–Category y Product–Store;
- listados por cursor, filtros y búsqueda administrativa básica;
- RBAC, FORCE RLS, idempotencia, optimistic concurrency, cuotas, auditoría y outbox;
- administración web mínima y E2E Chromium real.

Quedan fuera M3.0: Options, Attribute Definitions/Values, Metafields, Collections, Tags, asignaciones Channel/Market, media, imports, publicación, Search, Pricing e Inventory.

## 2. Boundary y dependencias

```text
app/modules/catalog/
├── api/
├── application/
├── domain/
├── infrastructure/
└── contracts/
```

La API compone dependencias y valida transporte; Application implementa casos de uso; Domain concentra normalización e invariantes; Infrastructure adapta repositorios SQLAlchemy/PostgreSQL; Contracts expone interfaces internas. Catalog consume contratos públicos de Platform para Store, locale, entitlements, idempotency, audit y outbox. Platform Kernel no importa Catalog.

## 3. Modelo persistente real

La migración inmutable `0003_catalog_foundation` crea 12 tablas:

1. `catalog_product_types`;
2. `catalog_brands`;
3. `catalog_products`;
4. `catalog_product_variants`;
5. `catalog_product_identifiers`;
6. `catalog_product_translations`;
7. `catalog_product_seo`;
8. `catalog_taxonomies`;
9. `catalog_categories`;
10. `catalog_category_closure`;
11. `catalog_product_categories`;
12. `catalog_product_stores`.

Todas las relaciones internas relevantes usan FKs compuestas con `tenant_id`. Los aggregates editables usan UUID, `version`, timestamps, actores y archive lógico. Estados Product: `draft`, `active`, `archived`. Las asignaciones Store usan `draft`, `active`, `suspended`, `archived` y un indicador de elegibilidad separado de publicación.

Invariantes reforzadas en PostgreSQL y dominio:

- una sola Variant default por Product mediante índice único parcial;
- SKU normalizado único por tenant, incluso tras archive;
- identificador normalizado único por tipo/tenant, incluso archivado;
- una identificación primaria por tipo y Variant;
- slug Product único por tenant/locale y Brand único por tenant;
- cierre de Category sin ciclos y dentro de una sola Taxonomy/tenant;
- máximo una Category primaria por Product y Taxonomy;
- Product–Store único y tenant-aware.

## 4. API real

El router `/api/v1/catalog` expone 27 paths y 40 operaciones:

| Recurso | Operaciones |
|---|---|
| Product Types | listar, crear, obtener, actualizar, archivar |
| Brands | listar, crear, obtener, actualizar, archivar |
| Products | listar, crear, obtener, actualizar, activar, archivar |
| Variants | listar por Product, crear, obtener, actualizar, archivar |
| Identifiers | listar por Variant, crear, archivar mediante DELETE |
| Translations/SEO | listar traducciones, upsert traducción, upsert SEO |
| Taxonomies/Categories | listar/crear Taxonomy; listar/crear/actualizar/mover/archivar Category |
| Product–Category | listar y reemplazar asignaciones |
| Product–Store | listar, upsert y archivar asignación |
| Usage | consultar uso de los dos entitlements Catalog |

Los listados maestros usan cursor opaco y límite acotado. Product admite filtros por status, Product Type, Brand y Store, más búsqueda simple por SKU o nombre.

## 5. RBAC

Se agregan exactamente 18 permisos:

```text
catalog.product.read
catalog.product.create
catalog.product.update
catalog.product.archive
catalog.variant.read
catalog.variant.create
catalog.variant.update
catalog.variant.archive
catalog.product_type.read
catalog.product_type.manage
catalog.brand.read
catalog.brand.manage
catalog.taxonomy.read
catalog.taxonomy.manage
catalog.category.read
catalog.category.manage
catalog.assignment.read
catalog.assignment.manage
```

Owner/Admin reciben todos. Manager recibe operaciones completas salvo `catalog.product_type.manage`. Editor recibe el subconjunto editorial definido en la migración. Analyst/Viewer reciben lectura. Los roles personalizados no reciben grants automáticos.

## 6. Multi-tenant y seguridad

Las 12 tablas ejecutan `ENABLE ROW LEVEL SECURITY` y `FORCE ROW LEVEL SECURITY`, con políticas explícitas de SELECT, INSERT, UPDATE y DELETE basadas en `app.current_tenant_id`. `catalog_product_stores` añade el contexto opcional `app.current_store_id`; si existe, limita filas a esa Store. El rol de aplicación conserva `NOSUPERUSER`, `NOBYPASSRLS` y no es propietario de tablas.

Los servicios convierten referencias cross-tenant en 404 indistinguible. Los tests ofensivos cubren contexto ausente, CRUD directo, Store ajena, UUID manipulado y reutilización del pool.

## 7. Consistencia transversal

- `Idempotency-Key` es obligatorio en los ocho comandos de creación definidos para M3.0. Mismo key/payload reproduce la respuesta; fingerprint distinto devuelve conflicto; reservas y efecto son tenant-scoped.
- Updates y transiciones usan `If-Match`; una versión obsoleta devuelve `409 Conflict`.
- `catalog.products.max` tiene default `50000`; `catalog.variants.max_per_product`, `100`.
- El consumo se valida dentro de la transacción. Un advisory lock transaccional por tenant serializa la cuota sin deadlock con FKs de idempotencia.
- Product y Variant default, audit y outbox confirman o revierten juntos.
- Category move bloquea y reconstruye closure en una transacción; la versión de Taxonomy avanza de forma monótona.
- Product–Store expresa elegibilidad administrativa, no publicación.

## 8. Eventos implementados

M3.0 emite 21 eventos v1 mediante el envelope del Platform Kernel:

```text
catalog.product_type.created.v1
catalog.product_type.updated.v1
catalog.product_type.archived.v1
catalog.product.created.v1
catalog.product.updated.v1
catalog.product.activated.v1
catalog.product.archived.v1
catalog.variant.created.v1
catalog.variant.updated.v1
catalog.variant.archived.v1
catalog.brand.created.v1
catalog.brand.updated.v1
catalog.brand.archived.v1
catalog.taxonomy.created.v1
catalog.category.created.v1
catalog.category.updated.v1
catalog.category.moved.v1
catalog.category.archived.v1
catalog.product.assigned_to_category.v1
catalog.product.assigned_to_store.v1
catalog.product.unassigned_from_store.v1
```

No se emite `published`. Los payloads son mínimos y no incluyen descripciones largas. Correlation, actor, tenant, aggregate y versión viajan en el envelope existente.

## 9. Frontend

La navegación administrativa incorpora Product Types, Brands, Products y Taxonomies/Categories. Permite crear Product simple, inspeccionar y editar Variants, gestionar clasificación y asignar Stores. La UI respeta permisos y presenta loading, estados vacíos, cursor, archive, conflictos, duplicados, cuotas y correlation ID en errores técnicos.

Rutas principales:

```text
/catalog/product-types
/catalog/brands
/catalog/products
/catalog/products/new
/catalog/products/[id]
/catalog/taxonomies
```

## 10. Evidencia local

- Pytest completo: `71 passed`.
- Cobertura total backend: `80.97%` (gate `>=80%`).
- Ruff: aprobado.
- mypy: aprobado.
- Pruebas enfocadas RLS/concurrencia/migraciones: `12 passed` sobre PostgreSQL real.
- Frontend: `20 passed`, `1 skipped`.
- E2E completo en Chromium real: `2 passed` (Catalog y baseline Identity/Platform).
- Migraciones: `0002 → 0003 → 0002 → 0003` y `base → head` verificadas.
- Backend wheel/sdist y Next.js production build: aprobados.

Workflow localmente validado por sintaxis y comandos: `Nexus Modules 1-2 and Catalog Foundation Quality Gate`, archivo `.github/workflows/modules-1-2-catalog-foundation-quality-gate.yml`. Jobs: `backend-quality`, `frontend-quality`, `playwright-e2e` y `modules-1-2-catalog-foundation-gate`. Artifacts configurados: `nexus-catalog-foundation-backend-evidence` y `nexus-catalog-foundation-playwright-evidence`.

## 11. Comandos de validación

```powershell
.\.venv\Scripts\python -m pytest -q --cov=app --cov-report=term-missing --cov-report=xml --cov-report=html --cov-fail-under=80
.\.venv\Scripts\python -m ruff check app tests scripts
.\.venv\Scripts\python -m mypy --no-incremental app
.\.venv\Scripts\python -m build
cd frontend
npm.cmd test
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
npm.cmd run test:e2e -- --project=chromium
```

## 12. Riesgos y límites conocidos

Permanecen abiertos:

- dos vulnerabilidades npm moderadas;
- migración histórica `0001` dependiente de metadata dinámica;
- auditoría append-only no criptográficamente inmutable;
- dispatcher y jobs requieren procesos supervisados en producción;
- limpieza programada de evidencias/idempotencia/jobs pendiente;
- listado administrativo Product realiza composición relacional adecuada para M3.0, pero necesitará proyección/Search para escala y filtros avanzados;
- el lock por tenant puede convertirse en hot spot con tasas de escritura extremas; debe medirse antes de particionar;
- locale governance se deriva de locales habilitados en Store y aún no tiene fallback avanzado;
- archive no incluye restore ni purge;
- `main` no tiene branch protection configurada — riesgo documentado, no bloquea este cierre, queda como tarea prioritaria: exigir Pull Request, checks obligatorios, prohibir force push y eliminación de `main`, exigir conversaciones resueltas antes de mergear, y al menos una aprobación cuando haya más colaboradores.

GitHub-hosted validó el commit de cierre de M3.0 (ver cabecera de este documento).

## 13. Trabajo pendiente

- M3.1: Product–Variant avanzado según replanificación, sin duplicar el vertical ya entregado.
- M3.2: Options y Attributes.
- M3.3: Collections, Tags y clasificación restante.
- M3.4: localización y SEO avanzados.
- M3.5: assignments Channel/Market y elegibilidad target-based.
- M3.6: Metafields y media, condicionado a Assets.
- M3.7: hardening, rendimiento a escala, runbooks y gate hosted de cierre.

Ninguno de esos incrementos está implementado ni autorizado por esta entrega. El Módulo 3 no está cerrado.
