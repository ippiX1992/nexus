# Módulo 2 — Platform Kernel

## Estado

**Estado Módulo 2: CERRADO.** Cierre formal validado localmente y mediante GitHub-hosted el 2026-07-14.

| Campo | Evidencia de cierre |
|---|---|
| Repositorio | `ippiX1992/nexus` |
| Commit validado | `49bfea76ff2c940e2e56ee41d37dfbef1fc7b38d` |
| Workflow | `Nexus Modules 1-2 Quality Gate` |
| Run ID | `29365183544` |
| Resultado | `success` |
| Jobs | `backend-quality`, `frontend-quality`, `playwright-e2e`, `modules-1-2-gate` |
| Artifacts | `nexus-backend-evidence`, `nexus-playwright-evidence` |

Platform Kernel implementa la jerarquía y los mecanismos transversales mínimos sobre Identidad y Multi-Tenant. No incluye catálogo, CMS, Builder ni flujos ecommerce.

El boundary está en `app/modules/platform`:

```text
api/             adaptador HTTP y schemas
application/     use cases, idempotencia, dispatcher y jobs
contracts/       event envelope y puertos
domain/          invariantes y value objects
infrastructure/  modelos y adaptador SQLAlchemy
```

Identity continúa siendo autoridad de usuarios, membresías, roles y sesiones. Platform recibe un `TenantContext` revalidado, establece contexto PostgreSQL transaccional y resuelve recursos por tenant/scope.

## Modelo de datos

### Recursos

- `platform_stores`
- `platform_sites`
- `platform_channels`
- `platform_environments`
- `platform_markets`
- `platform_store_locales`
- `platform_store_currencies`
- `platform_market_locales`
- `platform_market_currencies`
- `platform_channel_sites`
- `platform_channel_markets`
- `platform_channel_environments`
- `platform_resource_scopes`

Stores son aggregate raíz. Todos los hijos usan FK compuesta `(tenant_id, store_id)`. Stores y recursos hijos se archivan lógicamente. Los índices únicos de código/slug incluyen tenant y store según el boundary.

Solo puede existir un environment de producción no archivado por store; PostgreSQL lo garantiza con índice parcial único.

### Infraestructura durable

- `platform_outbox_events`
- `platform_inbox_events`
- `platform_idempotency_records`
- `platform_operations`
- `platform_jobs`
- `platform_entitlement_definitions`
- `platform_entitlement_overrides`

## Estándares geográficos y monetarios

- Babel valida locales registrados y normaliza tags BCP 47.
- Babel valida monedas ISO 4217 y determina minor units.
- Territorios se validan como ISO 3166-1 alpha-2.
- `zoneinfo` valida identificadores IANA.
- `MoneyConfiguration` usa `Decimal`; nunca `float`.
- El rounding inicial es `ROUND_HALF_EVEN` y queda persistido para evolución futura.

## Invariantes

- Código y slug de Store son únicos por tenant.
- Código de recursos hijos es único por store y tenant.
- Un recurso nunca referencia un Store de otro tenant.
- Un Store archivado no acepta configuraciones nuevas.
- No existe eliminación física en la API.
- Transiciones Store permitidas: draft→active/archive, active→suspended/archive, suspended→active/archive.
- Environment `production` debe tener `is_production=true`; los demás false.
- Cuotas se verifican antes de crear.
- Cambio de aggregate, auditoría, scope, outbox y respuesta idempotente comparten transacción.

## Endpoints

### Stores

```text
GET    /api/v1/stores
POST   /api/v1/stores
GET    /api/v1/stores/{store_id}
PATCH  /api/v1/stores/{store_id}
POST   /api/v1/stores/{store_id}/activate
POST   /api/v1/stores/{store_id}/suspend
POST   /api/v1/stores/{store_id}/archive
```

### Sites

```text
GET    /api/v1/stores/{store_id}/sites
POST   /api/v1/stores/{store_id}/sites
GET    /api/v1/sites/{site_id}
PATCH  /api/v1/sites/{site_id}
POST   /api/v1/sites/{site_id}/archive
```

`primary_domain_placeholder` es deliberadamente no operativo. DNS, ownership y TLS quedan fuera de Módulo 2.

### Channels

```text
GET    /api/v1/stores/{store_id}/channels
POST   /api/v1/stores/{store_id}/channels
GET    /api/v1/channels/{channel_id}
PATCH  /api/v1/channels/{channel_id}
POST   /api/v1/channels/{channel_id}/archive
```

Las tablas de relación permiten asociar Channels con Sites, Markets y Environments sin introducir catálogo o checkout.

### Environments

```text
GET    /api/v1/stores/{store_id}/environments
POST   /api/v1/stores/{store_id}/environments
PATCH  /api/v1/environments/{environment_id}
POST   /api/v1/environments/{environment_id}/archive
```

### Markets

```text
GET    /api/v1/stores/{store_id}/markets
POST   /api/v1/stores/{store_id}/markets
GET    /api/v1/markets/{market_id}
PATCH  /api/v1/markets/{market_id}
POST   /api/v1/markets/{market_id}/archive
```

### Operations y capacidad

```text
GET /api/v1/operations
GET /api/v1/operations/{operation_id}
GET /api/v1/platform/entitlements
PUT /api/v1/platform/entitlements/{key}
GET /api/v1/platform/usage
```

## Permisos

```text
store.read/create/update/archive
site.read/create/update/archive
channel.read/create/update/archive
environment.read/create/update/archive
market.read/create/update/archive
operation.read
entitlement.read/manage
```

La migración agrega permisos a roles de sistema existentes sin tocar roles personalizados. Nuevos tenants los reciben mediante el seed idempotente de Identity.

## Resource scopes

Jerarquía:

```text
tenant
└── store
    ├── site
    ├── channel
    ├── environment
    └── market
```

Cada creación registra un scope. La API revalida membresía/permiso mediante Módulo 1, establece tenant y store en la transacción y consulta por IDs tenant-aware. IDs arbitrarios de otro tenant producen 404 y un intento de scope denegado puede auditarse sin filtrar existencia externa.

## RLS

Las 19 tablas tenant-aware nuevas tienen:

- `ENABLE ROW LEVEL SECURITY`
- `FORCE ROW LEVEL SECURITY`
- policy SELECT con `USING`
- policy INSERT con `WITH CHECK`
- policy UPDATE con `USING` y `WITH CHECK`
- policy DELETE con `USING`

El usuario `nexus_app` no posee `BYPASSRLS`. `get_current_context` establece `app.current_tenant_id` con `set_config(..., true)`; endpoints store-scoped establecen también `app.current_store_id`.

Las FKs compuestas impiden que una fila use `tenant_id` correcto con un `store_id` perteneciente a otro tenant.

## Event envelope y outbox

Eventos iniciales:

```text
platform.store.created/updated/activated/suspended/archived.v1
platform.site.created/updated/archived.v1
platform.channel.created/updated/archived.v1
platform.environment.created/updated/archived.v1
platform.market.created/updated/archived.v1
```

El envelope incluye event ID/type/version, tiempo UTC, tenant/store, aggregate, correlation/causation, actor y datos seguros. Se persiste completo como JSONB.

`OutboxDispatcher` reclama eventos con `FOR UPDATE SKIP LOCKED`. La interfaz `EventPublisher` permite incorporar un broker sin cambiar productores. La entrega es at-least-once.

## Inbox

Inbox tiene `UNIQUE (consumer_name, event_id)`. `DurableOperationConsumer` es el consumidor inicial: registra una Operation exitosa por evento. Reentregar el mismo evento no duplica el efecto.

## Idempotencia

POST de creación requiere `Idempotency-Key`.

- La clave se scopea por tenant, actor, método y endpoint.
- El fingerprint usa JSON canónico SHA-256.
- Misma petición devuelve status/body originales y header `Idempotency-Replayed`.
- Mismo key con payload distinto devuelve 409.
- Requests concurrentes se serializan por constraint y bloqueo.
- Los registros expiran en 24 horas; un job futuro puede limpiarlos.

## Jobs y Operations

Jobs implementa claim atómico, `SKIP LOCKED`, lease, retries exponenciales, recuperación de lock vencido, max attempts y dead letter. Los fallos y dead letters se auditan.

Operations separa progreso visible de la ejecución. El usuario solo consulta operaciones de su tenant con `operation.read`.

No se incorporó Celery, Temporal, Kafka o RabbitMQ.

## Entitlements y cuotas

Defaults:

| Key | Default |
|---|---:|
| `stores.max` | 10 |
| `sites.max_per_store` | 10 |
| `channels.max_per_store` | 10 |
| `markets.max_per_store` | 20 |
| `environments.max_per_store` | 4 |
| `users.max` | 100 |

Overrides se guardan por tenant. Solo `entitlement.manage` puede cambiarlos. Excesos devuelven 409 y se auditan. `users.max` se verifica al aceptar invitaciones, preservando el flujo de Identity.

## Observabilidad

El middleware:

- acepta o genera UUID `X-Correlation-ID`;
- lo devuelve en cada respuesta;
- lo propaga a auditoría, outbox, jobs y operations;
- registra JSON con servicio, entorno, método, ruta, status y duración;
- rechaza IDs inválidos;
- nunca registra headers, cookies o payloads sensibles.

```text
GET /health  liveness del proceso
GET /ready   SELECT 1 contra PostgreSQL
```

## Frontend

La sección Platform contiene:

- lista, creación y detalle de Stores;
- selección de Store activo;
- Sites, Channels, Environments y Markets;
- formularios, loading, vacíos, errores, cuotas y archivado;
- Usage/quotas;
- Operations;
- correlation ID visible en errores técnicos.

No contiene storefront ni editor visual.

## Migración

`0002_platform_kernel.py` usa operaciones Alembic explícitas. No importa metadata del Platform Kernel en `alembic/env.py`: esto es necesario porque `0001` usa metadata viva y registrar modelos nuevos alteraría su significado efectivo al migrar desde base vacía.

Validación requerida:

```powershell
alembic upgrade head
alembic downgrade 0001
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

## Comandos de validación

```powershell
.\.venv\Scripts\python -m pytest -q --cov=app --cov-report=term-missing --cov-fail-under=80
.\.venv\Scripts\python -m ruff check app tests scripts --select F,I,UP,B
.\.venv\Scripts\python -m mypy app --no-incremental
.\.venv\Scripts\python -m build --no-isolation
cd frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
npm.cmd run test:e2e
```

## Resultado de validación local

Validado el 2026-07-14 sobre PostgreSQL 17 real y Chromium real:

| Control | Resultado |
|---|---|
| Alembic base → head y downgrade/upgrade | correcto; revisión final `0002 (head)` |
| Backend | 47 pruebas aprobadas |
| Cobertura | 81.00% (umbral 80%) |
| Ruff | aprobado con `F,I,UP,B` |
| mypy | 46 archivos sin errores |
| Frontend | 13 pruebas aprobadas; 1 integración condicionada omitida |
| E2E Chromium | 1 flujo completo aprobado |
| Build backend | wheel y sdist generados |
| Build Next.js | 20 rutas generadas correctamente |

El workflow de GitHub Actions ejecutó los mismos gates críticos, sin `continue-on-error`, sobre el commit validado. El Run `29365183544` terminó en `success`: `backend-quality`, `frontend-quality`, `playwright-e2e` y `modules-1-2-gate` aprobaron. Los artifacts publicados fueron `nexus-backend-evidence` y `nexus-playwright-evidence`.

## Riesgos pendientes

- El dispatcher y worker necesitan supervisión de proceso antes de producción.
- No hay broker externo; la extracción futura debe preservar envelope/inbox.
- No existe binding RBAC distinto por Store; permisos son tenant-wide y el scope valida pertenencia/estado.
- Limpieza de idempotency/outbox/inbox requiere jobs programados operacionales.
- Auditoría heredada del Módulo 1 aún no es criptográficamente inmutable.
- La migración `0001` sigue usando metadata viva; Platform evita agravarla, pero una futura consolidación requiere estrategia documentada.
- `npm audit` mantiene dos vulnerabilidades moderadas conocidas; no se aplicó una actualización disruptiva automática.
- Data residency, sharding y tenant directory quedan para escala posterior.
