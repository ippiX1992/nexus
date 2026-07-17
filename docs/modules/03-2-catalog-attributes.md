# M3.2 — Catalog Attributes and Product Specifications

> Estado: **RELEASE CANDIDATE — criterios técnicos locales cumplidos** (141 tests, cobertura
> 88.45%, Ruff/mypy/migraciones/RLS/concurrencia/RBAC/build backend/build Next.js/E2E Chromium
> real, todo en verde). Rama `feature/catalog-attributes`, **apilada sobre**
> `feature/catalog-options` (no sobre `main` — M3.1 todavía no está integrado a `main`, solo
> tiene CI remoto verde). No integrado a `main`, sin PR, sin tag, sin merge. Depende de M3.1.

## 1. Qué es un Attribute y por qué es distinto de una Option

Una **Option** (M3.1) genera combinaciones: dos valores distintos de una Option producen dos
Variants distintas del mismo Product (Color Rojo vs Color Negro son productos físicamente
distintos que hay que trackear con SKU/stock propio). Un **Attribute** (M3.2) es información
descriptiva que no genera combinaciones: la Potencia (500W) o el Material (Aluminio) de un
producto no crean una Variant nueva — son datos que describen la única Variant que ya existe (o
todas las Variants por igual, ya que en este incremento el Attribute se guarda a nivel de
**Product**, no de Variant).

Esta distinción es la que exige `CLAUDE.md` (comparación PrestaShop `features` vs `combinations`,
VTEX `specifications` vs `variations`, Shopify `metafields` vs `options`) y la razón por la que
M3.2 **no reutiliza** `catalog_options`/`catalog_option_values`: aunque técnicamente parecidas
(ambas son "definición + valores controlados"), mezclarlas acoplaría dos dominios con reglas de
negocio incompatibles (Options fuerzan unicidad de combinación vía fingerprint; Attributes no
generan combinación en absoluto). Se comparten solo patrones técnicos (CatalogResourceMixin,
traducciones satélite, archive/restore, RLS, RBAC granular), nunca las tablas.

## 2. Modelo de datos

9 tablas nuevas, todas tenant-owned, `FORCE ROW LEVEL SECURITY`:

| Tabla | Propósito |
|---|---|
| `catalog_attributes` | definición: code, name, data_type, unit, flags (required/filterable/searchable/comparable/visible_storefront), position, status |
| `catalog_attribute_translations` | name/description por locale |
| `catalog_attribute_options` | valores controlados para `SELECT`/`MULTI_SELECT` |
| `catalog_attribute_option_translations` | label por locale |
| `catalog_attribute_groups` | agrupación visual (Información general, Dimensiones, ...) |
| `catalog_attribute_group_translations` | name/description por locale |
| `catalog_product_type_attributes` | asignación Product Type ↔ Attribute, con overrides |
| `catalog_product_attribute_values` | valor tipado por Product+Attribute (una fila) |
| `catalog_product_attribute_value_options` | membresía `MULTI_SELECT` (múltiples filas) |

### 2.1 Tipos de dato (`catalog_attributes.data_type`)

`TEXT`, `LONG_TEXT`, `INTEGER`, `DECIMAL`, `BOOLEAN`, `DATE`, `DATETIME`, `SELECT`,
`MULTI_SELECT`. `catalog_attribute_options` solo puede referenciar Attributes con
`data_type IN ('SELECT','MULTI_SELECT')` — validado a nivel de aplicación (un `CHECK` no puede
consultar otra tabla); a nivel de columna se protege con constraint de FK normal.

### 2.2 Almacenamiento de valores — decisión de diseño

`catalog_product_attribute_values` usa **columnas tipadas** (`value_text`, `value_long_text`,
`value_integer`, `value_decimal`, `value_boolean`, `value_date`, `value_datetime`,
`value_option_id`) en vez de una columna JSON/texto genérica. Un `CHECK` a nivel de fila garantiza
que **como máximo una** columna esté poblada (defensa estructural); que la columna poblada
**coincida con `data_type`** del Attribute se valida en el servicio de aplicación (requiere JOIN,
no expresable en `CHECK`). Se descarta guardar todo como texto sin tipar — exactamente lo que
`CLAUDE.md`/la comparación con plataformas líderes identifica como debilidad de implementaciones
ingenuas de EAV.

`MULTI_SELECT` no cabe en "una fila, un valor": se resuelve con la tabla hija
`catalog_product_attribute_value_options` (mismo patrón que `catalog_variant_option_values` de
M3.1 para membresía de conjunto), donde `catalog_product_attribute_values` actúa como fila
"contenedora" (todas sus columnas tipadas quedan `NULL`) y las selecciones viven como filas hijas.

### 2.3 Traducciones — alcance de este incremento

Se traducen: nombre/descripción de Attribute, nombre/descripción de Attribute Group, y el label de
cada Attribute Option — mismo patrón satélite que M3.0/M3.1. **No se traduce** el valor libre de
un Attribute `TEXT`/`LONG_TEXT` por Product en este incremento (ej. una descripción técnica en
inglés y español) — construir esa infraestructura para valores libres por producto es un esfuerzo
mayor sin caso de uso confirmado todavía; se documenta como límite conocido, no como omisión
accidental.

### 2.4 Archive/restore

Attributes, Attribute Options y Attribute Groups usan archive lógico (no DELETE). Un Attribute
archivado no puede asignarse a nuevos Product Types ni recibir nuevos valores, pero los valores ya
guardados en Products existentes **se conservan** (no se borran, no bloquean lectura) — igual que
M3.1 conserva combinaciones con Option Values archivados. `restore` revierte `status` a `active`
sin recrear historial perdido (no había ninguno que perder).

## 3. API

| Recurso | Endpoints |
|---|---|
| Attributes | `GET/POST /catalog/attributes`, `GET/PATCH /catalog/attributes/{id}`, `POST .../archive`, `POST .../restore`, `PUT .../translations/{locale}` |
| Attribute Options | `GET/POST /catalog/attributes/{id}/options`, `PATCH /catalog/attribute-options/{id}`, `POST .../archive`, `PUT .../translations/{locale}` |
| Attribute Groups | `GET/POST /catalog/attribute-groups`, `GET/PATCH /catalog/attribute-groups/{id}`, `POST .../archive`, `POST .../restore` |
| Product Type ↔ Attributes | `GET/PUT /catalog/product-types/{id}/attributes` (PUT reemplaza el conjunto completo, mismo patrón que Product↔Options de M3.1) |
| Product specifications | `GET/PUT /catalog/products/{id}/attributes` (PUT reemplaza el conjunto completo de valores) |

Convención de errores idéntica a M3.0/M3.1: `404` cross-tenant indistinguible, `409`
versión/duplicado/cuota, `422` validación de dominio (tipo incorrecto, opción inválida,
obligatoriedad), `429` reservado solo para rate limiting de transporte.

## 4. RBAC — 14 permisos nuevos

```
catalog.attribute.read / .create / .update / .archive
catalog.attribute_option.read / .create / .update / .archive
catalog.attribute_group.read / .create / .update / .archive
catalog.product_type_attribute.read / .manage
catalog.product_attribute_value.read / .manage
```

Mismo esquema de asignación que M3.1: Owner/Admin/Manager todos; Editor subset operativo (sin
archive); Analyst/Viewer solo lectura.

## 5. Eventos (outbox)

`catalog.attribute.created/updated/archived/restored.v1`,
`catalog.attribute_option.created/updated/archived.v1`,
`catalog.attribute_group.created/updated/archived.v1`,
`catalog.product_type.attributes_changed.v1`,
`catalog.product.attribute_values_changed.v1`. Mismo envelope, mismas garantías transaccionales
que M3.0/M3.1 (ver ADR-003 Event Envelope).

## 6. Frontend

`frontend/app/catalog/attributes/page.tsx` (listar/crear/archivar/restaurar Attributes, gestionar
Attribute Options para SELECT/MULTI_SELECT), `frontend/app/catalog/attribute-groups/page.tsx`,
extensión de la ficha de Product Type con asignación de Attributes (grupo, posición, obligatorio),
y sección "Especificaciones" en la ficha de Product con un control por tipo de dato.

## 7. Pruebas

Backend: unit (dominio: validación de tipo, cardinalidad) + integración real contra PostgreSQL
(CRUD, traducciones, SELECT/MULTI_SELECT, asignación a Product Type, valores de Product por cada
tipo, obligatoriedad, RLS ofensivo, RBAC, idempotencia, concurrencia, outbox, migración
round-trip). Frontend: cliente HTTP (mismo patrón que `catalog-options.test.ts`). E2E: flujo
completo con Chromium real + casos negativos (tipo incorrecto, opción inválida, permiso
insuficiente).

## 8. No objetivos de este incremento

MX.0, Builder, Marketplace; traducción de valores libres por Product; drag-and-drop de posición
(controles simples de número/orden, sin librería de UI nueva); búsqueda facetada por Attribute
(requiere Search, M3.8); Attributes heredados automáticamente al cambiar el Product Type de un
Product (se documenta la política pero no se implementa migración automática de valores).

## 9. Evidencia local

- Pytest: 141 passed (108 M3.0+M3.1 + 33 nuevos: 15 dominio, 11 API, 2 RLS, 2 concurrencia, 2
  edge cases, 1 round-trip de migración).
- Cobertura total backend: **88.45%**, por encima del 80% requerido (medición correcta, con el
  fix de `concurrency = greenlet` ya aplicado en M3.1).
- Ruff: aprobado en `app/`, `tests/`, `scripts/`.
- mypy: aprobado, `--no-incremental`, 61 archivos fuente.
- Migraciones: round-trip `0004↔0005` y `base→head` verificado, sin `create_all/drop_all`.
- RLS ofensivo: cross-tenant vía API (`404` en Attributes/Attribute Options/Product Type
  Attributes/Product Attribute Values), SQL directo sin contexto (0 filas en las 9 tablas
  nuevas), Attribute Option perteneciente a un Attribute distinto rechazado.
- Concurrencia real contra PostgreSQL: `code` duplicado de Attribute y escritura concurrente de
  especificaciones de Product, ambos con exactamente un ganador (constraint de unicidad y
  optimistic concurrency respectivamente, no locking de aplicación).
- RBAC: viewer puede leer Attributes pero no crearlos (403 real); cuota de Attribute Options
  aplicada vía entitlement override (409 real).
- Frontend: 42 passed, 1 skipped (10 tests nuevos del cliente de Attributes, mismo patrón que
  `catalog-options.test.ts`).
- Next.js build: aprobado, incluye `/catalog/attributes`, `/catalog/attribute-groups`, y
  `/catalog/products/[id]` con la sección de Especificaciones.
- Backend build: wheel + sdist correctos.
- E2E Chromium real: `frontend/e2e/catalog-attributes.spec.ts` — flujo completo (Group →
  Attribute DECIMAL requerido → Attribute SELECT con opciones → asignar ambos a un Product Type
  respetando `is_required` del Attribute como default → crear Product → guardar
  especificaciones → recargar → verificar persistencia) más tres casos negativos reales: tipo
  incorrecto (`422`), opción inválida (`422`), permiso insuficiente (`403`).

### Bug real encontrado y corregido durante este incremento

El formulario "Agregar Attribute" de la ficha de Product Type siempre creaba la asignación con
`required=false`, ignorando el `is_required` por defecto declarado en el propio Attribute — lo
cual contradice la semántica documentada en la sección 2 (`is_required` como sugerencia de
default). Corregido para que `addAttribute` use `attribute.is_required` como valor inicial del
checkbox `required` de la asignación, dejando que el usuario lo cambie manualmente después si lo
necesita. Encontrado por el flujo E2E real, no por revisión de código.
