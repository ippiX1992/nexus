# M3.1 — Options y Variant Combinations

> Estado del módulo: **Módulo 3: EN PROGRESO**.
> Estado del incremento: **M3.1: RELEASE CANDIDATE local**.
> Rama: `feature/catalog-options` (local, sin publicar).
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
  `option_value_ids` opcional (sin endpoint nuevo, reutiliza el ya existente).
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

Extiende `/api/v1/catalog` con 17 operaciones nuevas (15 endpoints del diseño aprobado + 2 de
traducción necesarias para cumplir el modelo de dominio, mismo patrón que
`PUT /products/{id}/translations/{locale}` de M3.0):

| Recurso | Operaciones |
|---|---|
| Options | listar, crear, obtener, actualizar, archivar, traducción |
| Option Values | listar por Option, crear, actualizar, archivar, traducción |
| Product Options | listar, reemplazar (`PUT`, mismo patrón que Product–Category) |
| Variant | `POST /products/{id}/variants` extendido con `option_value_ids` opcional |
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
Option Values (crear/archivar, con preview de swatch). Enlazado desde `CatalogNav`. Build de
Next.js y `tsc --noEmit` verificados en verde.

**No implementado en este incremento** (alcance reducido, documentado explícitamente como
pendiente, no como completo): pestaña "Opciones" dentro de la ficha de Product, selector de
combinación en la pestaña Variantes, UI de preview/confirmación/progreso de generación en lote.
`docs/modules/03-1-catalog-options-plan.md` sección 6 mantiene los wireframes textuales completos
para cuando se retome.

## 10. Evidencia local

- Pytest: 107 passed (94 M3.0 + 13 tests de dominio M3.1 + integración M3.1).
- Cobertura total backend: ver informe final (por debajo del 80% requerido al cierre de esta
  entrega — ver riesgos).
- Ruff: aprobado en `app/`, `tests/`, `scripts/`.
- mypy: aprobado, `--no-incremental`, 61 archivos fuente.
- Migraciones: `0003↔0004` y `base→head` verificadas, sin `create_all/drop_all`.
- RLS ofensivo: cross-tenant vía API (`404`), SQL directo sin contexto (0 filas en las 6 tablas
  nuevas), contexto de tenant A no filtra hacia tenant B, Option Value ajeno a la Option indicada
  rechazado, Option Value archivado rechazado en asignación nueva pero conservado en Variant
  existente.
- Concurrencia real contra PostgreSQL: `code` duplicado de Option y combinación duplicada, ambos
  con exactamente un ganador.
- Frontend: `20 passed, 1 skipped` (sin regresión; no se agregaron tests unitarios nuevos para la
  página de Options — riesgo documentado).
- Next.js build: aprobado, incluye `/catalog/options` como ruta estática.
- E2E Chromium: **no ejecutado en este incremento** — riesgo documentado, no falso positivo.

## 11. Riesgos y límites conocidos

Además de los ya heredados de M3.0 (sin cambios):

- Cobertura de pytest por debajo de 80% al cierre de esta entrega — concentrada en
  `app/modules/catalog/api/routes.py` y `application/services.py`, donde M3.1 añadió ~500 líneas
  con más ramas de error de las que alcanzó a cubrir esta sesión.
- Sin pruebas E2E Chromium reales para el flujo de Options — solo integración a nivel de API.
- Sin pestaña de Options/combinaciones en la ficha de Product — solo la página standalone.
- Worker de generación sin supervisión de proceso — mismo riesgo ya aceptado para el resto de
  jobs de Nexus, documentado, no nuevo.
- `duplicate_combinations` del preview siempre es `0` — no hay selección de candidatos parcial en
  este incremento, solo "generar todo lo faltante".
- `enforce_admins=false` en `main` (heredado de M3.0) sigue permitiendo push directo del owner —
  sin cambios en este incremento.

## 12. Trabajo pendiente

M3.2 (Attributes/Features) y siguientes, según `docs/modules/03-catalog-core-plan.md` sección 20.
Ninguno de esos incrementos está implementado ni autorizado por esta entrega.
