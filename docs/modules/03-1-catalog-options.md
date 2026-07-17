# M3.1 — Options y Variant Combinations

> Estado del módulo: **Módulo 3: EN PROGRESO**.
> Estado del incremento: **M3.1: RELEASE CANDIDATE — criterios técnicos locales cumplidos**
> (cobertura ≥80%, E2E Chromium real, frontend tests de Options, integración Product↔Options,
> Ruff/mypy/migraciones/RLS/concurrencia/build en verde). **No cerrado**: falta CI GitHub-hosted
> verde sobre el commit publicado (requiere push adicional, no autorizado en este incremento) y
> aprobación/merge explícitos. No confundir con M3.0, que sí está formalmente CERRADO.
> Rama: `feature/catalog-options`, publicada en `origin` (sin PR listo para merge, sin tag).
> Diseño aprobado: `docs/modules/03-1-catalog-options-plan.md`,
> `docs/architecture/catalog-options-domain.md`,
> `docs/architecture/catalog-option-combinations.md`.
> Depende de M3.0 Catalog Foundation (CERRADO).

## 1. Alcance entregado

Implementa el vertical completo de Options y combinaciones de Variant sobre M3.0, sin tocar
Attributes/Features descriptivos (M3.2, fuera de alcance):

- `catalog_options` / `catalog_option_translations` — dimensiones de variación reutilizables por
  tenant (Color, Talla), con traducción satélite opcional.
- `catalog_option_values` / `catalog_option_value_translations` — valores concretos (Rojo, S),
  con `swatch_hex` validado por constraint para `input_type='swatch'`.
- `catalog_product_options` — qué Options usa un Product concreto y en qué orden; todas
  `required=true` en M3.1 (sin Options opcionales).
- `catalog_variant_option_values` — la combinación real por Variant, con
  `UniqueConstraint(tenant_id, variant_id, option_id)` reforzando "un valor por Option por
  Variant" a nivel de base.
- `catalog_product_variants.combination_fingerprint` — SHA-256 sobre pares
  `option_id:option_value_id` ordenados por `option_id`, `NULL` para Variants sin combinación,
  con índice único parcial `(tenant_id, product_id, combination_fingerprint) WHERE archived_at IS
  NULL AND combination_fingerprint IS NOT NULL`.
- Creación manual de combinación: `POST /products/{id}/variants` extendido con
  `option_value_ids` opcional (reutiliza el endpoint ya existente). Lectura de la combinación de
  una Variant: `GET /variants/{id}/options` (único endpoint nuevo de este cierre, necesario para
  que el frontend muestre qué valores tiene cada Variant).
- Generación en lote durable: preview de solo lectura, `POST .../variant-generation` crea un
  `platform_operations`/`platform_jobs` (reutilizados del Platform Kernel, sin mecanismo nuevo) y
  devuelve `202` sin generar el producto cartesiano dentro del request; un worker
  (`scripts/run_catalog_generation_worker.py`) procesa el Job por lotes con SAVEPOINT por
  combinación.

Quedan fuera de M3.1: Attributes/Features (M3.2), Collections/Tags (M3.3), Localization/SEO
avanzado (M3.4), Assets/Media (M3.5), Channel/Market Eligibility (M3.6), Metafields (M3.7), Search
(M3.8), Catalog Administration/bulk-import rediseñado (M3.9).

## 2. Boundary y dependencias

Mismo boundary de M3.0 (`app/modules/catalog/{api,application,domain,infrastructure,contracts}`).
Nuevo: `app/modules/catalog/application/generation.py` (Operation+Job durables), que depende de
`app/modules/platform/application/jobs.py` y de los modelos `OperationModel`/`JobModel` ya
existentes en el Platform Kernel — ningún mecanismo de jobs nuevo.

## 3. Modelo persistente real

La migración `0004_catalog_options` crea 6 tablas y agrega 1 columna a una tabla existente:

1. `catalog_options`;
2. `catalog_option_translations`;
3. `catalog_option_values`;
4. `catalog_option_value_translations`;
5. `catalog_product_options`;
6. `catalog_variant_option_values`;
7. `catalog_product_variants.combination_fingerprint` (columna nueva).

Todas las relaciones usan FKs compuestas con `tenant_id`. Invariantes reforzadas en PostgreSQL:

- `code` de Option único por tenant, nunca reutilizado tras archivar;
- `code` de Option Value único por Option;
- `swatch_hex` con formato `#RRGGBB` o `NULL`;
- un valor por Option por Variant (`UniqueConstraint` en `catalog_variant_option_values`);
- Option Value debe pertenecer a la Option indicada, y esa Option debe estar asignada al Product
  (FK compuesta de 3 columnas, no solo validación de aplicación);
- combinación no duplicada por Product (índice único parcial sobre `combination_fingerprint`,
  protege bajo concurrencia real, verificado con dos requests simultáneos — sección 6).

Validado: `0003 → 0004 → 0003 → 0004` y `base → head`, sin `Base.metadata.create_all/drop_all`.

## 4. API real

Extiende `/api/v1/catalog` con 18 operaciones nuevas (15 endpoints del diseño aprobado + 2 de
traducción necesarias para cumplir el modelo de dominio, mismo patrón que
`PUT /products/{id}/translations/{locale}` de M3.0, + 1 endpoint de lectura agregado en el cierre
local para que el frontend pueda mostrar la combinación de una Variant):

| Recurso | Operaciones |
|---|---|
| Options | listar, crear, obtener, actualizar, archivar, traducción |
| Option Values | listar por Option, crear, actualizar, archivar, traducción |
| Product Options | listar, reemplazar (`PUT`, mismo patrón que Product–Category) |
| Variant | `POST /products/{id}/variants` extendido con `option_value_ids` opcional; `GET
  /variants/{id}/options` para leer su combinación |
| Generación | preview de solo lectura, solicitud durable (`202` + Operation) |
| Operations | `GET /operations/{id}` — reutilizado del Platform Kernel, sin cambios |

Convención única de errores (`docs/modules/03-1-catalog-options-plan.md` sección 5): `409` para
versión/duplicado/idempotency-conflict/**cuota** (nueva subclase `CatalogOptionsQuotaExceeded`,
mapeada distinto de las cuotas de M3.0 que siguen en `429` para no romper sus tests existentes);
`422` para validación de dominio; `404` cross-tenant indistinguible; `429` exclusivo de rate limit
de transporte.

## 5. RBAC

14 permisos nuevos (`catalog.option.{read,create,update,archive}`,
`catalog.option_value.{read,create,update,archive}`, `catalog.product_option.{read,manage}`,
`catalog.variant_combination.{read,create,generate,archive}`), sembrados tanto en la migración
(catálogo global) como en `app/application/authorization.py` (`seed_rbac`, la fuente real que usan
los tests y el registro de tenants — hallazgo de esta implementación: el catálogo de permisos de
la migración por sí solo no basta, `seed_rbac` es quien realmente asigna roles al registrar un
tenant). Owner/Admin/Manager reciben todos; Editor recibe el subconjunto operativo (sin
`archive`/`generate`); Analyst/Viewer reciben lectura.

## 6. Consistencia transversal

- `Idempotency-Key` obligatorio en creación de Option, Option Value, y en la solicitud de
  generación durable.
- `If-Match` obligatorio en actualizaciones y en la solicitud de generación (valida contra el
  Product, no solo contra el recurso mutado).
- Retirar una Product Option con Variants activas usándola queda **bloqueado** (no permite retiro
  parcial ni modifica combinaciones en silencio) — verificado con test de integración real.
- Fingerprint recalculado dentro de la misma transacción que escribe la combinación — nunca
  diferido.
- Concurrencia real verificada contra PostgreSQL (no mock): dos requests simultáneos creando la
  misma combinación → exactamente un ganador (`201`/`409`), protegido por el índice único, no por
  lock de aplicación.

## 7. Eventos implementados

14 eventos v1, los mismos definidos en el diseño aprobado (`catalog.option.*`,
`catalog.option_value.*`, `catalog.product.option_attached/detached.v1`,
`catalog.variant.combination_created/updated/archived.v1`,
`catalog.variant_generation.requested/completed/failed.v1`). Payloads mínimos, solo IDs — nunca
nombres traducidos.

## 8. Generación durable

Preview (`POST .../variant-generation/preview`) es de solo lectura y devuelve los diez campos del
diseño (`options_considered`, `theoretical_total`, `existing_combinations`, `new_combinations`,
`duplicate_combinations` [siempre 0 en este incremento — no hay selección de candidatos parcial
todavía], `tenant_limit`, `remaining_capacity`, `warnings`, `estimated_work`).

La confirmación crea un `platform_operations` + `platform_jobs` (`job_type=
"catalog.variant_generation"`) y devuelve `202` sin generar nada dentro del request. El worker
(`scripts/run_catalog_generation_worker.py`) reutiliza `claim_jobs`/`complete_job`/`fail_job` ya
existentes del Platform Kernel — invocación manual/periódica, no daemon autónomo, mismo criterio
que `scripts/cleanup_rate_limits.py` (riesgo ya documentado y aceptado para el resto de los jobs de
Nexus, no es una regresión introducida por M3.1). Cada combinación candidata corre en su propio
SAVEPOINT (mismo patrón que el bulk-import de M3.0 usa por fila), reportando `created`/
`skipped_already_exists`/`failed` por combinación, con progreso incremental en el `Operation`.

**Bug real encontrado y corregido durante la implementación**: el contexto RLS (`app.current_tenant_id`)
se establece con `SET LOCAL` (transaccional). Los commits intermedios para persistir progreso lo
reseteaban, causando `InsufficientPrivilegeError` a partir de la segunda combinación de cada
generación en lote. Corregido re-estableciendo el contexto después de cada commit; cubierto por
`tests/integration/test_catalog_options_api.py::test_variant_generation_is_durable_not_synchronous_and_worker_creates_combinations`,
que ejecuta el worker real (no un mock) y verifica 4 combinaciones creadas de 2×2 Option Values.

## 9. Frontend

`frontend/app/catalog/options/page.tsx` — listar/crear/archivar Options, expandir y gestionar sus
Option Values (crear/archivar, con preview de swatch). Enlazado desde `CatalogNav`.

`frontend/app/catalog/products/[id]/page.tsx` — extendida con sección "Opciones" (asignar/quitar
Options del Product, siempre `required=true` según la regla de M3.1), formulario de creación de
Variant con un selector por Option asignada (envía `option_value_ids`), y visualización de la
combinación de cada Variant existente (nombre de Option + valor, resuelto vía el nuevo endpoint
`GET /variants/{id}/options`). Build de Next.js y `tsc --noEmit` verificados en verde.

**No implementado en este incremento** (alcance reducido, documentado explícitamente como
pendiente, no como completo): UI de preview/confirmación/progreso de generación en lote (la
generación durable solo se puede disparar hoy vía API, no desde el admin).
`docs/modules/03-1-catalog-options-plan.md` sección 6 mantiene los wireframes textuales completos
para cuando se retome.

## 10. Evidencia local

- Pytest: 108 passed (94 M3.0 + 14 de dominio M3.1 + integración M3.1, incluyendo el nuevo
  endpoint `GET /variants/{id}/options`).
- Cobertura total backend: **89.24%**, por encima del 80% requerido. Ver nota crítica abajo:
  el número real siempre estuvo cerca de este valor — el 77.24% reportado en el cierre anterior
  era un artefacto de medición de `coverage.py`, no una brecha de pruebas real (sección 13).
- Ruff: aprobado en `app/`, `tests/`, `scripts/`.
- mypy: aprobado, `--no-incremental`, 61 archivos fuente.
- Migraciones: `0003↔0004` y `base→head` verificadas, sin `create_all/drop_all`.
- RLS ofensivo: cross-tenant vía API (`404`), SQL directo sin contexto (0 filas en las 6 tablas
  nuevas), contexto de tenant A no filtra hacia tenant B, Option Value ajeno a la Option indicada
  rechazado, Option Value archivado rechazado en asignación nueva pero conservado en Variant
  existente.
- Concurrencia real contra PostgreSQL: `code` duplicado de Option y combinación duplicada, ambos
  con exactamente un ganador.
- Frontend: `30 passed, 1 skipped` (10 tests nuevos para las funciones cliente de Options, mismo
  patrón que `frontend/tests/catalog.test.ts`; sin testing-library instalada, así que no cubren
  renderizado de componentes, solo el cliente HTTP).
- Next.js build: aprobado, incluye `/catalog/options` y `/catalog/products/[id]` (con Options
  integradas) como rutas.
- E2E Chromium real: **ejecutado**, `frontend/e2e/catalog-options.spec.ts` — flujo completo
  (registro → tenant → Store activo → Product Type → Product → Option Color → Values Rojo/Negro →
  asignar Option al Product → crear Variant con combinación → verificar combinación visible) más
  combinación duplicada (`409` real) y permiso insuficiente de un rol viewer (`403` real), contra
  un backend y frontend reales levantados en puertos aislados (no contra los contenedores Docker
  del entorno del usuario).
- Integración Product ↔ Options: la ficha de Product (`/catalog/products/[id]`) ahora incluye
  asignación de Options al Product, creación de Variant con selección de valores por Option
  asignada, y visualización de la combinación de cada Variant existente (vía el nuevo endpoint
  `GET /variants/{id}/options`).

## 11. Riesgos y límites conocidos

Además de los ya heredados de M3.0 (sin cambios):

- Worker de generación sin supervisión de proceso — mismo riesgo ya aceptado para el resto de
  jobs de Nexus, documentado, no nuevo.
- `duplicate_combinations` del preview siempre es `0` — no hay selección de candidatos parcial en
  este incremento, solo "generar todo lo faltante".
- `enforce_admins=false` en `main` (heredado de M3.0) sigue permitiendo push directo del owner —
  sin cambios en este incremento.
- El E2E de M3.1 cubre el flujo principal más duplicado y permiso insuficiente; no repite el caso
  de aislamiento cross-tenant en Chromium porque ya está verificado exhaustivamente a nivel de
  integración backend real (sección RLS arriba) — cubrirlo también en E2E sería redundante, no
  una brecha.

## 13. Corrección de medición de cobertura (hallazgo de esta sesión)

`coverage.py` nunca tuvo configurado `concurrency = greenlet` en `pyproject.toml`. SQLAlchemy usa
la librería `greenlet` internamente para puentear el ORM (fundamentalmente síncrono: flush,
autoflush, cascadas) hacia el mundo async — cada `await session.flush()` (y operaciones
equivalentes) cruza un cambio de greenlet. Sin ese ajuste, `coverage.py` pierde el rastro de la
ejecución después de ese cambio y reporta como "no cubiertas" líneas que en realidad sí se
ejecutaron — confirmado insertando un `print()` de control: el print se ejecutaba dos veces en
consola, pero la línea seguía marcada como no cubierta hasta aplicar el fix.

Esto no era específico de M3.1: afectaba a todo el código que pasa por el ORM async en cualquier
módulo. El 77.24%/77.18%/76.68%/76.86% perseguidos en la sesión anterior de M3.1 eran en su
mayoría medición incorrecta, no pruebas faltantes reales — la cobertura real ya rondaba el 89%
antes de escribir una sola línea nueva de test en esta sesión. Corrección aplicada:
`concurrency = ["greenlet", "thread"]` en `[tool.coverage.run]`. El workflow de CI no necesitó
cambios porque lee esta configuración de `pyproject.toml` automáticamente.

## 14. Trabajo pendiente

M3.2 (Attributes/Features) y siguientes, según `docs/modules/03-catalog-core-plan.md` sección 20.
Ninguno de esos incrementos está implementado ni autorizado por esta entrega.
