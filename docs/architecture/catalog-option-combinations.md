# Catalog Option Combinations — Fingerprint, Explosion Control, Data Model (M3.1)

> Estado: **implementado como M3.1: RELEASE CANDIDATE local** en `feature/catalog-options` (no
> integrado a `main`) — ver evidencia en
> [`docs/modules/03-1-catalog-options.md`](../modules/03-1-catalog-options.md). Complementa
> [catalog-options-domain.md](catalog-options-domain.md) (conceptos y reglas de negocio) con el
> mecanismo técnico de combinación: fingerprint, control de explosión combinatoria, modelo de datos
> completo, RLS y concurrencia. Sigue el proceso de `CLAUDE.md`.

## 1. Combination fingerprint

### 1.1 Requisitos (dados)

- Depende de IDs estables (`option_id`, `option_value_id`), nunca de nombres, slugs ni
  traducciones.
- Independiente del orden en que el usuario asignó los valores.
- Contiene exactamente un valor por Option **activa** del Product (ver decisión de opcionalidad en
  `catalog-options-domain.md` sección 9 — con la recomendación preliminar de "todas obligatorias",
  el fingerprint siempre tiene tantos pares como `catalog_product_options` activas tenga el
  Product).
- Impide combinaciones duplicadas del mismo Product.
- Protegido por constraint de PostgreSQL, no solo por validación de aplicación.
- Nunca usa nombres, slugs ni traducciones — solo UUIDs.

### 1.2 String canónico

```text
option_id:value_id|option_id:value_id
```

- Cada par es `f"{option_id}:{option_value_id}"` con ambos UUID en su forma canónica de 36
  caracteres (minúsculas, con guiones) — nunca `hex` compacto, para que la representación sea
  determinista independientemente de cómo la serialice cada capa.
- Los pares se ordenan por `option_id` ascendente (comparación lexicográfica de string UUID, no
  numérica) antes de unir. Ordenar por `option_id` es suficiente para un orden total determinista
  porque el constraint de la sección 4 ya garantiza como máximo un `option_value_id` por
  `option_id` en la misma Variant — no hace falta un criterio de desempate.
- Separador `|` entre pares. Sin espacios, sin corchetes, sin comas.
- Variant sin ningún Option Value asignado (producto simple, o Variant configurable todavía sin
  combinación) → string canónico vacío, tratado como caso especial (ver 1.4).

### 1.3 Algoritmo

1. Leer todas las filas de `catalog_variant_option_values` para la Variant (siempre dentro de la
   misma transacción que las escribió).
2. Ordenar por `option_id` ascendente.
3. Construir el string canónico (1.2).
4. Calcular `SHA-256` del string canónico codificado en UTF-8.
5. Persistir el hash resultante (ver 1.5) — **nunca** el string canónico crudo.

Se recalcula síncronamente, dentro de la misma transacción que escribe/borra filas de
`catalog_variant_option_values` — mismo patrón que M3.0 ya usa para confirmar/revertir
Product+Variant+audit+outbox juntos (`docs/modules/03-catalog-foundation.md` sección 7). Nunca se
recalcula de forma diferida ni por un job aparte: el fingerprint debe ser válido en el mismo commit
que la combinación que describe, o el índice único de la sección 4 no protege nada.

### 1.4 Caso vacío (sin sentinel de string)

Una Variant sin ningún valor asignado (producto simple, o Variant "configurable" que todavía no
recibió su combinación) tiene `combination_fingerprint = NULL`, no el hash de la cadena vacía. Es
una decisión deliberada: `NULL` queda excluido nativamente de cualquier índice único parcial de
Postgres (`WHERE combination_fingerprint IS NOT NULL`), así que múltiples Variants sin combinación
del mismo Product coexisten sin fricción — necesario porque M3.0 ya crea la Variant default sin
combinación para todo producto simple (470 de los productos demo actuales), y M3.1 no debe romper
eso ni exigir backfill.

### 1.5 Columna, constraint y migración

| Aspecto | Decisión |
|---|---|
| **¿Dónde vive el fingerprint?** | `catalog_product_variants.combination_fingerprint` — no una tabla de combinación separada, no una proyección aparte. Ver 1.6 para la justificación frente a las otras dos opciones. |
| **Tipo de columna** | `CHAR(64)` (hex de SHA-256), `NULL`able |
| **Constraint de unicidad** | Índice único parcial: `UNIQUE (tenant_id, product_id, combination_fingerprint) WHERE archived_at IS NULL AND combination_fingerprint IS NOT NULL` |
| **Migración** | Alembic agrega la columna `combination_fingerprint` a `catalog_product_variants` (tabla ya existente desde M3.0) con `NULL` por defecto — no requiere backfill porque toda Variant existente hoy no tiene combinación (`NULL` es el valor correcto para ellas). Downgrade elimina la columna y su índice. |
| **Comportamiento al archivar una Option o un Option Value** | El fingerprint **no se recalcula** cuando se archiva una Option/Value referenciada por una combinación existente — el fingerprint describe qué combinación *fue* asignada, no si sus componentes siguen activos. Combinación histórica (ver `catalog-options-domain.md` sección 4) conserva su fingerprint intacto. Esto es consistente con "nunca se re-valida retroactivamente". |

### 1.6 ¿Dónde vive el fingerprint? — comparación de las tres opciones dadas

| Opción | Ventaja | Limitación | Decisión |
|---|---|---|---|
| **`catalog_product_variants`** (columna en la tabla ya existente) | Un solo `UPDATE` por combinación, en la misma fila que ya tiene `version`/`archived_at`/RLS de M3.0; el índice único parcial es directo sobre esa tabla, sin JOIN | Acopla el concepto "combinación" a la tabla de Variant, que también sirve productos simples sin Options | **Elegida** — el acoplamiento es aceptable porque toda Variant, con o sin Options, ya es la misma entidad conceptual (una fila vendible); no hay dos tipos de Variant que ameriten tablas separadas |
| **Tabla de combinación separada** (`catalog_variant_combinations`, 1:1 con Variant) | Separación conceptual más limpia | Une por FK 1:1 en cada lectura de listado de Variants (el mismo N+1 que M3.0 ya se cuidó de evitar en el listado de Products, sección 9 de `03-catalog-foundation.md`); no aporta nada que la columna directa no resuelva, porque la relación es siempre 1:1, nunca 1:N | Descartada — complejidad sin beneficio para una relación 1:1 |
| **Proyección separada** (tabla de solo-lectura recalculada por job) | Útil si el cálculo fuera costoso o necesitara agregación entre muchas filas | El cálculo es un hash sobre, como máximo, `catalog_product_options.max_per_product` pares (tope bajo, sección 5) — trivial, no amerita proyección asíncrona | Descartada — sobre-ingeniería para un cálculo que cabe en la misma transacción de escritura |

## 2. Explosión combinatoria — generación controlada

M3.0 ya estableció "Variants explícitas": nada se genera automáticamente hoy. M3.1 introduce la
*posibilidad* de generación en lote (útil cuando un Product tiene 3 Options con varios valores cada
una y crear cada Variant a mano es impráctico), pero **nunca sin control explícito**. Flujo completo,
en el orden pedido:

1. **Cálculo previo**: dado un Product con `catalog_product_options` activas, el tamaño del
   producto cartesiano es `∏ (cantidad de Option Values activos por cada Option)`. Se calcula en
   memoria, sin tocar la base más que para leer los conteos — operación de solo lectura, instantánea.
2. **Dry run**: `POST /products/{id}/variant-generation/preview` (ver sección 6, API) es de solo
   lectura — no escribe nada — y devuelve exactamente estos diez campos:

   | Campo | Contenido |
   |---|---|
   | `options_considered` | Options y su `option_id`, tal como están declaradas en `catalog_product_options` para el Product |
   | `values_per_option` | cantidad de Option Values activos por cada Option considerada |
   | `theoretical_total` | `∏ values_per_option` — el producto cartesiano completo, exista o no ya cada combinación |
   | `existing_combinations` | cuántas de esas combinaciones ya tienen una Variant activa (no se re-crean) |
   | `new_combinations` | `theoretical_total - existing_combinations` — lo que la confirmación crearía |
   | `duplicate_combinations` | combinaciones candidatas que colisionan entre sí dentro del mismo request (payload con la misma combinación repetida dos veces, si el request permite selección parcial en vez de "todas") |
   | `tenant_limit` | valor vigente de `catalog.variant_combinations.max_per_product` para el tenant |
   | `remaining_capacity` | `tenant_limit - existing_combinations` — cuánto margen real queda antes de tocar el límite |
   | `warnings` | lista de advertencias legibles (por ejemplo, "excede la capacidad restante", "una Option no tiene Values activos") |
   | `estimated_work` | `new_combinations` menos `duplicate_combinations` — el número real de Variants que la Operation intentaría crear |

3. **Total estimado**: `new_combinations` (del preview) es el número que la UI muestra antes de
   pedir confirmación (ver sección 7, wireframes) — nunca `theoretical_total` a secas, para no
   confundir "combinaciones que existirían en total" con "combinaciones que se crearían ahora".
4. **Límite por entitlement**: si `existing_combinations + new_combinations` supera
   `catalog.variant_combinations.max_per_product` (nuevo, sección 3 del plan de incremento,
   default 100), o si `estimated_work` supera `catalog.combination_generation.max_per_operation`
   (nuevo, default 50, tope por Operation individual — protege contra pedir de una sola vez todo el
   margen restante de un Product), el preview devuelve el resultado igual pero con `warnings`
   pobladas y marca el request como "excede el límite" — el usuario ve el problema antes de
   confirmar, no después de un fallo a mitad de operación. `catalog.variants.max_per_product` (ya
   existe desde M3.0) sigue aplicando como tope general de Variants del Product, con o sin
   combinación — los dos límites son independientes y ambos se validan.
5. **Confirmación**: `POST /products/{id}/variant-generation` requiere `Idempotency-Key` (mismo
   patrón que los ocho comandos de creación de M3.0) y **no** re-ejecuta el cálculo — recibe el
   mismo payload que generó el preview, y falla con `409` si el estado del Product cambió entre el
   preview y la confirmación (optimistic concurrency vía `version` del Product, igual que cualquier
   otro comando de M3.0).
6. **Operation durable**: la confirmación no ejecuta la generación de forma síncrona dentro del
   request HTTP — crea un registro de Operation (estado `pending`/`running`/`completed`/`failed`,
   con `operation_id`) y devuelve `202 Accepted` con `Location: /api/v1/operations/{operation_id}`.
   Se reutiliza el mismo modelo de Operations que ya use el Platform Kernel para trabajos
   asíncronos, si existe uno genérico — no se crea un mecanismo de tracking paralelo solo para esto.
   `GET /operations/{operation_id}` expone el progreso (`processed_count`/`total_count`, no solo el
   estado final) para que la UI pueda mostrar una barra de avance (sección 7, wireframes).
7. **Job durable, procesado por lotes**: el trabajo real (crear N Variants + N filas de
   `catalog_variant_option_values` + N fingerprints) corre como un `JobModel` del Platform Kernel
   (`app/modules/platform/application/jobs.py`, ya existente, `claim_jobs`/`complete_job`/
   `fail_job`) — tenant-scoped, con `lease`/retry/`dead_letter` ya resueltos por ese mecanismo, en
   vez de inventar uno nuevo para M3.1. Procesa las combinaciones candidatas en lotes acotados (no
   una combinación por transacción, tampoco todo `estimated_work` en una sola transacción) — mismo
   criterio que M3.0 ya aplicó al import masivo para no sostener una transacción gigante ni perder
   todo el progreso ante un fallo a mitad de camino. El progreso (`processed_count`) se actualiza al
   confirmar cada lote, no al final del Job completo.
8. **Idempotencia**: el Job procesa cada combinación candidata de forma individualmente idempotente
   — si el Job se reintenta (lease expirado, worker caído), las combinaciones ya creadas se
   detectan por el índice único de la sección 4 (`unique violation` → se trata como "ya existe", no
   como error) y se saltan, nunca se duplican.
9. **Reporte de duplicados**: el resultado final de la Operation incluye, por cada combinación
   candidata: `created` \| `skipped_already_exists` \| `failed` con motivo — mismo shape de reporte
   por fila que M3.0 ya usa en el import masivo (`ImportProductOutcome`/`ImportRowIssue`, aunque ese
   componente específico queda congelado, ver `03-1-catalog-options-plan.md`), reutilizando el
   patrón, no el código.
10. **Rollback lógico**: si el Job falla a mitad de camino, las combinaciones ya creadas
    **no se revierten** — se reporta como parcial (`completed_with_errors`), y las Variants creadas
    quedan activas (son válidas por sí mismas, no dependen de que el resto del lote se complete). No
    hay rollback físico de una operación parcialmente exitosa porque cada Variant es una unidad
    completa y consistente por su cuenta (misma filosofía que el import masivo de M3.0: aislamiento
    por fila, no una transacción gigante todo-o-nada). El usuario puede volver a ejecutar el preview
    para ver qué falta y reintentar solo lo pendiente.

### Guardarraíles adicionales

- `catalog.product_options.max_per_product` (nuevo, sección 8) limita cuántas Options puede
  declarar un Product **antes** de que el cálculo previo pueda siquiera ser grande — un tope bajo
  aquí es la primera línea de defensa contra la explosión, más barata que validar después del
  cálculo.
- El cálculo previo (paso 1) se valida contra `catalog.variant_combinations.max_per_product`,
  `catalog.combination_generation.max_per_operation` y `catalog.variants.max_per_product`
  **antes** de generar, nunca después — ninguna escritura ocurre si el total ya excede cualquiera
  de los tres límites, salvo que el usuario reduzca el alcance del request (por ejemplo, generar
  solo un subconjunto de combinaciones candidatas).

## 3. Modelo de datos

Todas las tablas heredan `CatalogResourceMixin` (`id` UUID v4, `tenant_id`, `version` `BigInteger`,
`created_at`/`updated_at` `DateTime(timezone=True)`, `archived_at` nullable, `created_by`/`updated_by`
FK a `users.id` con `ondelete=SET NULL`) salvo las tablas de asignación puras (sin mixin, con PK
compuesta y solo `created_at`/`updated_at`), exactamente el patrón de
`app/modules/catalog/infrastructure/models.py`. `FORCE ROW LEVEL SECURITY` en las seis.

### 3.1 `catalog_options`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK, del mixin |
| `tenant_id` | UUID | FK `tenants.id` ON DELETE CASCADE, del mixin |
| `code` | `String(100)` | `UniqueConstraint(tenant_id, code)`, nunca reutilizado tras archivar |
| `name` | `String(200)` | Fallback tenant-wide |
| `input_type` | `String(20)` | `CheckConstraint IN ('select','swatch')` |
| `position` | `Integer` default `0` | |
| `status` | `String(20)` | `CheckConstraint IN ('active','archived')` |
| `version`, timestamps, actores | — | Del mixin |

Índices: `UniqueConstraint(tenant_id, id)` (para FKs compuestas entrantes),
`Index(tenant_id, status, position, id)`.

### 3.2 `catalog_option_translations`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `tenant_id` | UUID | FK `tenants.id` CASCADE |
| `option_id` | UUID | FK compuesta `(tenant_id, option_id) → catalog_options(tenant_id, id)` ON DELETE RESTRICT |
| `locale` | `String(35)` | |
| `name` | `String(200)` | |
| `created_at`/`updated_at` | — | Sin `version` (no es un aggregate editable independiente, es contenido satélite) |

`UniqueConstraint(tenant_id, option_id, locale)`. Sin `CatalogResourceMixin` completo — mismo
patrón que `ProductTranslationModel` en M3.0 (solo `id`/`tenant_id`/timestamps, sin `version` ni
`archived_at` propios: se archiva en cascada con la Option).

### 3.3 `catalog_option_values`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK, del mixin |
| `tenant_id` | UUID | Del mixin |
| `option_id` | UUID | FK compuesta `(tenant_id, option_id) → catalog_options(tenant_id, id)` ON DELETE RESTRICT |
| `code` | `String(100)` | `UniqueConstraint(tenant_id, option_id, code)` |
| `value` | `String(200)` | Fallback tenant-wide |
| `swatch_hex` | `String(7)` nullable | `CheckConstraint` formato `^#[0-9a-fA-F]{6}$` cuando no es NULL |
| `position` | `Integer` default `0` | |
| `status` | `String(20)` | `CheckConstraint IN ('active','archived')` |
| `version`, timestamps, actores | — | Del mixin |

Índices: `UniqueConstraint(tenant_id, id)`, `UniqueConstraint(tenant_id, option_id, id)` (ancla para
FKs compuestas de nivel inferior), `Index(tenant_id, option_id, status, position, id)`.

### 3.4 `catalog_option_value_translations`

Igual patrón que 3.2, referenciando `catalog_option_values`: `id`, `tenant_id`, `option_value_id`
(FK compuesta), `locale`, `value`, timestamps. `UniqueConstraint(tenant_id, option_value_id, locale)`.

### 3.5 `catalog_product_options`

Tabla de asignación pura (sin mixin completo, PK compuesta):

| Columna | Tipo | Notas |
|---|---|---|
| `tenant_id` | UUID | PK compuesta, FK `tenants.id` CASCADE |
| `product_id` | UUID | PK compuesta |
| `option_id` | UUID | PK compuesta |
| `position` | `Integer` default `0` | |
| `created_at`/`updated_at` | — | |

FKs compuestas: `(tenant_id, product_id) → catalog_products(tenant_id, id)` ON DELETE RESTRICT;
`(tenant_id, option_id) → catalog_options(tenant_id, id)` ON DELETE RESTRICT.
`Index(tenant_id, product_id, position, option_id)`.

### 3.6 `catalog_variant_option_values`

Tabla de asignación pura, con el fingerprint viviendo en `catalog_product_variants` (sección 1.5),
**no** en esta tabla:

| Columna | Tipo | Notas |
|---|---|---|
| `tenant_id` | UUID | PK compuesta, FK `tenants.id` CASCADE |
| `variant_id` | UUID | PK compuesta |
| `option_id` | UUID | PK compuesta |
| `option_value_id` | UUID | PK compuesta |
| `created_at`/`updated_at` | — | |

FKs compuestas: `(tenant_id, variant_id) → catalog_product_variants(tenant_id, id)` ON DELETE
RESTRICT; `(tenant_id, option_id, option_value_id) → catalog_option_values(tenant_id, option_id, id)`
ON DELETE RESTRICT. `UniqueConstraint(tenant_id, variant_id, option_id)` — el constraint central de
"un valor por Option por Variant" (sección 9 del documento de dominio).
`Index(tenant_id, option_value_id, variant_id)` para resolver "qué Variants usan este valor" sin
tabla scan.

### 3.7 Columna nueva en tabla existente

`catalog_product_variants.combination_fingerprint` — `CHAR(64)` nullable (sección 1.5), agregada
por migración a la tabla ya existente desde M3.0. No se agrega ninguna otra columna a
`catalog_product_variants`.

### 3.8 Auditoría

Todas las escrituras (creación/archivado de Options, Option Values, asignación de Product Options,
asignación de combinación) emiten evento de auditoría vía el mecanismo ya existente del Platform
Kernel (`app/application/auth.py::audit`, o equivalente en el módulo que corresponda) — mismo
patrón que M3.0 ya usa para sus propios comandos, no se diseña un mecanismo de auditoría nuevo.

## 4. RLS y aislamiento

Las seis tablas (3.1–3.6) llevan `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` con
policy sobre `app.current_tenant_id`, sin excepción — mismo criterio que M3.0 aplicó a sus 12 tablas
sin ninguna quedar fuera.

### Pruebas ofensivas obligatorias

| Caso | Verificación esperada |
|---|---|
| Option de otro tenant | `SELECT`/`UPDATE` con `tenant_id` ajeno vía `app.current_tenant_id` correcto → 0 filas, nunca error revelador |
| Option Value ajeno | Idem, a través de `catalog_option_values` |
| Product ajeno | Intentar `catalog_product_options` apuntando a un `product_id` de otro tenant → rechazado por FK compuesta (la FK exige que `(tenant_id, product_id)` exista en `catalog_products` del mismo tenant) antes de llegar a RLS |
| Variant ajena | Idem, vía `catalog_variant_option_values` → `product_variants` |
| Product Option cruzada | Asignar un `option_id` que no pertenece al `tenant_id` del `product_id` → rechazado por la FK compuesta `(tenant_id, option_id)` |
| Variant Option Value cruzado | Asignar un `option_value_id` cuyo `option_id` no coincide con el `option_id` de la fila → rechazado por la FK compuesta de tres columnas `(tenant_id, option_id, option_value_id)` |
| IDs manipulados | UUID válido mas no perteneciente al tenant en cualquiera de las seis tablas → 404 indistinguible en la capa de aplicación (mismo criterio ya usado en M3.0: "los servicios convierten referencias cross-tenant en 404 indistinguible") |
| SQL directo | CRUD directo sin pasar por la capa de aplicación, con rol de aplicación (`NOSUPERUSER`, `NOBYPASSRLS`) → bloqueado por policy |
| Worker sin contexto | Ejecutar cualquier query sobre estas seis tablas sin `SET app.current_tenant_id` primero → 0 filas / error, nunca fuga |
| Pool reuse | Reutilizar una conexión del pool entre dos tenants distintos sin resetear `app.current_tenant_id` → test explícito de que el contexto no se filtra, extendiendo el test ya existente de M3.0 a estas seis tablas |
| Combinación creada con Values de distintos Products | Intentar asignar a una Variant del Product A un `option_value_id` que pertenece a una Option declarada solo en `catalog_product_options` del Product B (mismo tenant) → rechazado en la capa de aplicación: la validación de "Option Value pertenece a una Option declarada en `catalog_product_options` de este Product" no es expresable como FK simple (requiere JOIN de tres tablas), así que es el único caso de esta lista que depende de un test funcional además del constraint de base |
| Mezcla de values archivados | Intentar asignar (asignación **nueva**, no ya existente) un `option_value_id` cuyo `archived_at IS NOT NULL` → rechazado en la capa de aplicación (sección 9 del documento de dominio); test explícito de que una Option Value archivada sigue siendo legible desde una combinación ya existente pero nunca aceptada en una asignación nueva |
| Bypass mediante asociación indirecta | Intentar llegar a datos de otro tenant encadenando JOINs a través de una fila propia (por ejemplo, un `option_value_id` propio cuyo `option_id` fue manipulado para apuntar, vía UUID adivinado, a una Option de otro tenant) → rechazado por la FK compuesta de tres columnas `(tenant_id, option_id, option_value_id)`, que exige que las tres pertenezcan al mismo `tenant_id` simultáneamente — no hay combinación de valores propios que permita "asomarse" a filas ajenas |

## 5. Concurrencia

| Caso | Mecanismo de protección | Isolation level | Respuesta HTTP esperada |
|---|---|---|---|
| Dos Options con mismo `code` (misma transacción concurrente) | `UniqueConstraint(tenant_id, code)` — el segundo `INSERT` espera el lock del índice y falla con `unique_violation` al confirmar | READ COMMITTED (default de la app, igual que M3.0) | `409 Conflict` |
| Dos Option Values con mismo `code` (mismo Option) | `UniqueConstraint(tenant_id, option_id, code)` | READ COMMITTED | `409 Conflict` |
| Dos Product Options duplicadas | PK compuesta `(tenant_id, product_id, option_id)` — el segundo `INSERT` colisiona con la PK | READ COMMITTED | `409 Conflict` (o no-op idempotente si coincide `Idempotency-Key`) |
| Dos Variants con mismo fingerprint | Índice único parcial (sección 1.5) — el segundo `UPDATE`/`INSERT` que fija el mismo `combination_fingerprint` para el mismo Product falla al confirmar, sin importar el orden de llegada; no requiere lock de aplicación adicional porque la enforcement de un índice único de Postgres es atómica a nivel de B-tree, no un patrón check-then-act | READ COMMITTED | `409 Conflict` |
| Archivar Option mientras se crea Variant que la usa | El archivado es un `UPDATE` sobre `catalog_options.archived_at`; la creación de combinación valida "Option activa" leyendo dentro de su propia transacción — si el archivado confirma primero, la creación de combinación ve la Option ya archivada y la rechaza en la validación de aplicación (sección 9 del documento de dominio); si la creación confirma primero, el archivado no revierte combinaciones ya creadas (sección 4 del documento de dominio) — no hay condición de carrera insegura en ningún orden, solo dos resultados válidos distintos según quién gana | READ COMMITTED, sin lock explícito adicional (el propio `UPDATE` de `archived_at` ya toma row lock estándar de Postgres) | Depende del orden: `201`/`200` para quien gana la carrera, `409` (Option ya no disponible) para quien la ve archivada |
| Retirar Product Option mientras se crea combinación que la usa | Mismo patrón que el caso anterior, aplicado a `catalog_product_options` en vez de `catalog_options` | READ COMMITTED | Idem |
| Crear combinaciones simultáneas (distintas, mismo Product) | Sin conflicto real — cada una tiene su propio fingerprint, el índice único solo actúa si coinciden; no requiere lock de tenant como el de cuotas | READ COMMITTED | `201` para ambas |
| Superar el límite de `max_per_product` concurrentemente | Requiere el mismo advisory lock transaccional por tenant que M3.0 ya estableció para `catalog.products.max`/`catalog.variants.max_per_product` (sección 7 de `03-catalog-foundation.md`) — contar filas no es atómico por sí solo, a diferencia de la unicidad del fingerprint; se reutiliza el lock existente, no se crea uno nuevo | READ COMMITTED + advisory lock por tenant | `409 Conflict` (cuota excedida) para quien pierde la carrera del lock |

**Retries**: ninguna de las operaciones anteriores reintenta automáticamente a nivel de aplicación —
un `409` se devuelve tal cual al cliente; el cliente decide si reintenta (mismo criterio que M3.0
ya aplica a sus propios conflictos de versión/cuota). La excepción es el Job durable de generación
en lote (sección 2), que sí reintenta vía el mecanismo de `lease`/`attempts` ya existente en
`app/modules/platform/application/jobs.py`.
