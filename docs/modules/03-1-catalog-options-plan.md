# M3.1 — Options y Variant Combinations: plan de incremento

> Estado: **diseño funcional y técnico APROBADO (2026-07-16), implementación PENDIENTE.** Siguió
> el proceso obligatorio de `CLAUDE.md` (pasos 1–4: PrestaShop, otras plataformas, diseño Nexus,
> tabla de comparación) hasta el paso 5 (aprobación explícita del usuario), que ya ocurrió para el
> diseño — no para la implementación, que sigue requiriendo autorización explícita separada antes
> de escribir migración, modelo, endpoint, test o frontend. M3.0 Catalog Foundation está
> **CERRADO** (PR #1, merge commit `59859c3e`, tag `module-3-catalog-foundation-v0.1.0`; commit
> documental final `08a70d7`, alineación de arquitectura `5d025d9`). El Módulo 3 permanece
> **EN PROGRESO**.
>
> Documentos relacionados: [catalog-options-attributes-prestashop-mapping.md](../architecture/catalog-options-attributes-prestashop-mapping.md)
> (investigación comparativa de 5 plataformas), [catalog-options-domain.md](../architecture/catalog-options-domain.md)
> (conceptos y reglas de negocio), [catalog-option-combinations.md](../architecture/catalog-option-combinations.md)
> (fingerprint, control de explosión, modelo de datos, RLS, concurrencia).

## 0. Trabajo heredado del stash — estado congelado

Tres líneas de trabajo llegaron sin terminar desde antes de que existiera la metodología de
`CLAUDE.md`, recuperadas solo para análisis (`backup/stash-mixed-work` @ `a187d94`,
`feature/catalog-bulk-import` y `feature/storefronts` locales, sin publicar, sin commit). Ninguna
se retoma como parte de M3.1.

### Bulk-import heredado

```text
Estado: CONGELADO.
No integrar.
No adaptar todavía.
Se rediseñará en M3.9 bajo CLAUDE.md.
```

Motivos:
- Depende de schemas mezclados (`app/modules/catalog/api/schemas.py` combina los tipos de
  bulk-import con campos nuevos de `ProductSummary` que pertenecen a Catalog Admin UX, ver abajo).
- Depende de rutas compartidas (`routes.py` mezcla el endpoint de import con filtros de listado
  no relacionados).
- Depende de cambios de listado administrativo (`ProductListRecord`, `get_*_by_code` en
  `infrastructure/repositories.py` sirven a ambas features a la vez).
- No compila aislado — verificado empíricamente: `import app.modules.catalog.application.bulk_import`
  falla con `ImportError: cannot import name 'BulkImportSummary'` contra el `main` actual.
- Fue desarrollado antes de que existiera `CLAUDE.md` — sin análisis comparativo formal contra
  PrestaShop/VTEX/Shopify/BigCommerce/Magento.
- Podría quedar obsoleto o necesitar rediseño una vez que Options, Attributes, Assets y Search
  existan — un import masivo diseñado antes de que el modelo de catálogo soporte esas capas
  probablemente subestima columnas que el archivo de origen debería poder traer.

### Storefronts actuales

```text
Estado: PROTOTIPO VISUAL CONGELADO.
No es funcionalidad productiva.
Pertenece a Storefront Runtime/CMS/Builder futuro.
```

Verificado: `frontend/lib/storefronts.ts` y `frontend/components/StorefrontDemo.tsx` no contienen
ninguna llamada a la API de Catalog ni a ningún módulo de backend — dos tiendas demo ("Voltio",
"Casa Viva") con productos, precios e ilustraciones SVG completamente estáticos (datos
hardcodeados, sin backend real, sin CMS, sin Builder, sin Pricing, sin Inventory), pensadas como
muestra visual de dirección de producto, no como funcionalidad. Podrá revisarse cuando existan CMS,
Builder, Themes y un Storefront Runtime real — ninguno de los cuatro está siquiera diseñado
todavía. No se publica la rama, no se continúa su desarrollo.

### Catalog Admin UX (nueva línea identificada, sin recuperar)

```text
Estado: REFERENCIA NO INTEGRADA.
Se evaluará en M3.9.
```

El stash contiene una tercera línea de trabajo, parcial, que no es ni bulk-import ni storefronts:
listado mejorado de Products (`ProductsTable.tsx`, `StatusBadge.tsx`), filtros adicionales,
navegación administrativa (`adminNavigation.ts`, cambios en `Shell.tsx`/`CatalogNav.tsx`/
`PlatformNav.tsx`), rediseño de la ficha de Product en pestañas, y un documento de auditoría
UX/UI (`docs/audits/NEXUS_UX_UI_AUDIT_2026-07-15.md`) que aparentemente motivó esos cambios.

No se recupera ni se implementa nada de esto ahora. Corresponde al incremento oficial
**M3.9 — Catalog Administration, Imports y Bulk Actions** (numeración definitiva, sección 1):
tablas administrativas, filtros avanzados, columnas configurables, acciones masivas,
exportaciones, bulk-import (rediseñado bajo `CLAUDE.md`, no el heredado congelado), estados
visuales, navegación administrativa, búsqueda administrativa, reportes de errores por fila.
Deliberadamente amplio y no comprometido en detalle — el número y el nombre son definitivos, el
alcance exacto se valida con el mismo proceso de `CLAUDE.md` cuando se autorice.

## 1. Roadmap del Módulo 3 — numeración oficial reconciliada (2026-07-16)

Se revisaron los ocho documentos pedidos. Hay **tres numeraciones distintas y contradictorias**
conviviendo hasta antes de esta reconciliación. **Numeración oficial, definitiva, reemplaza las
tres anteriores**:

| # | Nombre oficial | Resuelve la ambigüedad previa |
|---|---|---|
| M3.0 | Catalog Foundation | **CERRADO** — sin cambios |
| M3.1 | Options y Variant Combinations | Reemplaza "Product–Variant avanzado" (ambas fuentes originales lo dejaban "pendiente de rebaseline" sin contenido concreto nunca definido — ver justificación abajo) |
| M3.2 | Attributes / Features descriptivos | Coincide con el diseño preliminar ya aprobado; reemplaza el bundle "Options+Attributes" de las fuentes originales |
| M3.3 | Collections y Tags | Ya no incluye Brand/Taxonomy/Category/closure — entregados en M3.0 |
| M3.4 | Localization y SEO avanzado | **Resuelto**: incremento propio (ver justificación abajo), no integrado en M3.2/M3.6/CMS |
| M3.5 | Assets y Media Associations | Debe preceder a M3.6/M3.7 y a CMS/Builder/storefronts reales |
| M3.6 | Channel y Market Eligibility | Ya no incluye Store — entregado en M3.0 |
| M3.7 | Metafields y Extensibilidad | Separado de Media (ahora en M3.5) |
| M3.8 | Search Projections y Catalog Hardening | Reemplaza "futuro separado" sin número de las fuentes originales |
| M3.9 | Catalog Administration, Imports y Bulk Actions | Nuevo — motivado por el hallazgo de Catalog Admin UX en el stash (sección 0); incluye el rediseño de bulk-import |

### Justificación de los cambios (dada, no derivada)

- M3.0 ya entregó Brand, Taxonomy, Categories, closure table, traducción básica, SEO básico y Store
  assignment — por lo tanto ninguno vuelve a figurar como pendiente en M3.3/M3.4/M3.6.
- Localization y SEO avanzado mantiene incremento propio (M3.4) porque su alcance real —
  fallbacks, redirects, canonicalización avanzada, Open Graph, structured data, gobernanza de
  locales — es distinto en naturaleza de lo ya entregado en M3.0 (traducción/SEO básicos) y de
  Attributes/Features (M3.2, que describe *qué es* el producto, no *en qué idioma se muestra*).
  Con esto queda resuelta la pregunta que este mismo documento dejaba abierta en su versión previa
  (¿incremento propio, integrar en M3.2, integrar en Channel/Market, o dejar para CMS?) — la
  resolución vino del propio proceso de aprobación, no de una decisión unilateral de este documento.
- Assets y Media (M3.5) debe existir antes de CMS, Builder y storefronts reales — cualquier
  incremento posterior que necesite referenciar media (Metafields en M3.7, Catalog Admin UX en
  M3.9) depende de que el Asset Reference Port ya exista.
- Search (dentro de M3.8) se diseña cuando el modelo de catálogo esté más estable — después de
  M3.1–M3.7, no antes, consistente con la nota ya existente en `03-catalog-foundation.md` §12
  ("necesitará proyección/Search para escala").
- Bulk-import queda al final (M3.9) porque depende del modelo definitivo de catálogo (Options,
  Attributes, Collections/Tags, Assets, todos los cuales un archivo de import debería poder poblar)
  y de la experiencia administrativa resultante — construirlo antes arriesga quedar obsoleto de
  nuevo, como ya le pasó al bulk-import heredado y congelado (sección 0).
- Storefronts no forma parte del roadmap de Catalog — pertenece al futuro Storefront
  Runtime/CMS/Builder, ninguno de los cuales está todavía ni bocetado.

## 2. Alcance de M3.1 (Options — no Attributes)

Mantiene la separación conceptual ya aprobada:

```text
Options
→ generan variantes
→ Color, Talla, Capacidad

Attributes / Features
→ describen el producto
→ Potencia, Material, Voltaje (M3.2, fuera de alcance aquí)
```

Diseño completo de conceptos, ownership, unicidad, archivado, traducciones, orden, swatches y
comportamiento de Variant default: [catalog-options-domain.md](../architecture/catalog-options-domain.md).
Fingerprint, explosión combinatoria, modelo de datos, RLS y concurrencia:
[catalog-option-combinations.md](../architecture/catalog-option-combinations.md).

## 3. Entitlements — oficiales, aprobados (2026-07-16)

Lista cerrada — no se crean más cuotas en M3.1 más allá de estas cinco, todas clasificadas
**obligatorias** (ninguna "medida inicialmente" ni "futuro"):

| Entitlement | Rol | Default propuesto |
|---|---|---|
| `catalog.product_options.max_per_product` | Primera línea de defensa contra explosión combinatoria — cuántas Options puede declarar un Product (ver `catalog-option-combinations.md` §2). Deliberadamente **no** copia el límite de 3 de Shopify | 6 |
| `catalog.option_values.max_per_option` | Cuántos Option Values puede tener una Option | 200 |
| `catalog.variant_combinations.max_per_product` | Cuántas combinaciones (Variants con `combination_fingerprint` no nulo) puede tener un Product — distinto de `variants.max_per_product`: cubre específicamente Variants *con* combinación, no el total | 100 |
| `catalog.combination_generation.max_per_operation` | Tope de combinaciones que una sola Operation de generación en lote puede crear, independiente del tope total del Product — protege contra un preview que pida generar todo de una sola vez incluso si el Product tiene margen bajo `variant_combinations.max_per_product` | 50 |
| `catalog.variants.max_per_product` | **Reutilizado** de M3.0, sin cambios — tope general de Variants del Product, con o sin combinación | 100 (sin cambio) |

`catalog.options.max_per_tenant` (propuesto en la primera pasada de este diseño) **no forma parte
de la lista aprobada** — se descarta, no se implementa en M3.1.

## 4. Eventos

Los catorce propuestos en el mensaje original, sin agregar ninguno sin consumidor probable:

```text
catalog.option.created.v1
catalog.option.updated.v1
catalog.option.archived.v1

catalog.option_value.created.v1
catalog.option_value.updated.v1
catalog.option_value.archived.v1

catalog.product.option_attached.v1
catalog.product.option_detached.v1

catalog.variant.combination_created.v1
catalog.variant.combination_updated.v1
catalog.variant.combination_archived.v1

catalog.variant_generation.requested.v1
catalog.variant_generation.completed.v1
catalog.variant_generation.failed.v1
```

Consumidores probables por grupo: los primeros seis (Option/Option Value lifecycle) — Search (M3.8,
para indexar filtros de faceta), Catalog Admin UX (M3.9, para invalidar caché de listados). Los dos
de `product.option_*` — igual, más un futuro motor de recomendaciones. Los tres de
`variant.combination_*` — Search, Inventory (cuando exista, para saber qué SKUs monitorear), y
Pricing (cuando exista, para saber qué SKUs necesitan precio). Los tres de `variant_generation.*`
— exclusivamente Catalog Admin UX (M3.9), para mostrar progreso de la Operation en el wireframe de
la sección 6. Envelope existente del Platform Kernel, sin cambios; payloads mínimos, solo IDs —
nunca nombres traducidos ni valores largos (mismo criterio ya fijado para el fingerprint).

## 5. API propuesta

Los quince endpoints del mensaje original. Formato: permiso, request, response, idempotencia,
concurrencia, eventos, errores.

### Convención única de errores (aplica a los quince endpoints)

| Código | Uso exclusivo |
|---|---|
| `409 Conflict` | Versión incorrecta (`If-Match` obsoleto); combinación duplicada (fingerprint ya existe); misma `Idempotency-Key` con payload distinto (fingerprint de request, no de combinación); transición de estado incompatible; **cuota excedida** (`catalog.product_options.max_per_product`, `catalog.option_values.max_per_option`, `catalog.variant_combinations.max_per_product`, `catalog.combination_generation.max_per_operation`, `catalog.variants.max_per_product`) |
| `422 Unprocessable Entity` | Validaciones de dominio: Option Value no pertenece a la Option indicada, Option no vinculada al Product, valor faltante para una Product Option obligatoria, formato inválido (`swatch_hex`, etc.) |
| `404 Not Found` | Recurso de otro tenant o inexistente — **siempre indistinguible**, nunca revela cuál de los dos casos es |
| `429 Too Many Requests` | **Exclusivamente** rate limiting de transporte (`app/core/rate_limit.py`) — nunca para cuotas de dominio, aunque el efecto visible ("demasiadas X") se sienta similar |

`429` queda reservado para el mecanismo de rate limit ya existente en Nexus; toda cuota de
catálogo (Options, Values, combinaciones, generación) usa `409`, consistente con cómo M3.0 ya trata
sus propias cuotas (`catalog.products.max`, `catalog.variants.max_per_product`).

| Endpoint | Permiso | Idempotencia | Concurrencia | Eventos | Errores propios |
|---|---|---|---|---|---|
| `GET /catalog/options` | `catalog.option.read` | N/A (lectura) | N/A | — | — |
| `POST /catalog/options` | `catalog.option.manage` | `Idempotency-Key` obligatorio | N/A (creación) | `option.created.v1` | `409` code duplicado |
| `GET /catalog/options/{id}` | `catalog.option.read` | N/A | N/A | — | `404` cross-tenant/inexistente |
| `PATCH /catalog/options/{id}` | `catalog.option.manage` | No requerido (no es creación) | `If-Match`/`version` | `option.updated.v1` | `409` versión obsoleta |
| `POST /catalog/options/{id}/archive` | `catalog.option.manage` | No requerido | `If-Match`/`version` | `option.archived.v1` | `409` versión obsoleta |
| `GET /catalog/options/{id}/values` | `catalog.option_value.read` | N/A | N/A | — | — |
| `POST /catalog/options/{id}/values` | `catalog.option_value.manage` | `Idempotency-Key` obligatorio | N/A | `option_value.created.v1` | `409` code duplicado, `409` cuota `max_per_option` |
| `PATCH /catalog/option-values/{id}` | `catalog.option_value.manage` | No requerido | `If-Match`/`version` | `option_value.updated.v1` | `409` versión obsoleta |
| `POST /catalog/option-values/{id}/archive` | `catalog.option_value.manage` | No requerido | `If-Match`/`version` | `option_value.archived.v1` | `409` versión obsoleta |
| `GET /catalog/products/{id}/options` | `catalog.assignment.read` | N/A | N/A | — | — |
| `PUT /catalog/products/{id}/options` | `catalog.assignment.manage` | `Idempotency-Key` obligatorio (reemplazo total del conjunto, mismo patrón que Product–Category en M3.0) | `If-Match`/`version` del Product | `product.option_attached.v1` por cada nueva, `product.option_detached.v1` por cada retirada | `409` cuota `max_per_product`, `409` versión obsoleta |
| `POST /catalog/products/{id}/variants` | `catalog.variant.create` (ya existe) | `Idempotency-Key` obligatorio (ya vigente desde M3.0) | `If-Match`/`version` del Product | `variant.created.v1` (ya existe) + `variant.combination_created.v1` si trae combinación | `409` fingerprint duplicado, `409` cuota `max_per_product` |
| `POST /catalog/products/{id}/variant-generation/preview` | `catalog.variant.create` | No requerido (solo lectura, no persiste) | N/A | — | `422` si `product_options` vacío |
| `POST /catalog/products/{id}/variant-generation` | `catalog.variant.create` | `Idempotency-Key` obligatorio | `If-Match`/`version` del Product | `variant_generation.requested.v1` inmediato; `completed.v1`/`failed.v1` al terminar el Job | `409` versión obsoleta, `409` excede `max_per_operation`/`max_per_product` |
| `GET /operations/{operation_id}` | Mismo permiso que originó la Operation | N/A | N/A | — | `404` cross-tenant/inexistente |

## 6. UX inspirada en PrestaShop — wireframes textuales

No se implementa frontend. Estructura de navegación del Product (familiar para quien usa
PrestaShop):

```text
Product
├── Información
├── Variantes          ← foco de esta sección
├── Opciones            ← nueva pestaña, M3.1
├── Categorías
├── Marca
├── Tiendas
└── Historial
```

### Pestaña "Opciones"

```text
┌─ Opciones de este Product ──────────────────────────────┐
│ [+ Agregar Opción]                                        │
│                                                             │
│  ☰ Color        [Reordenar]           [Quitar]            │
│     Valores: Rojo · Azul · Verde (3 activos)               │
│  ☰ Talla        [Reordenar]           [Quitar]            │
│     Valores: S · M · L · XL (4 activos)                    │
│                                                             │
│  Total posible: 3 × 4 = 12 combinaciones                   │
└───────────────────────────────────────────────────────────┘
```

### Pestaña "Variantes" (rediseñada para combinaciones)

```text
┌─ Variantes ───────────────────────────────────────────────┐
│ Resumen: 5 de 12 combinaciones creadas                     │
│                                                             │
│ [Crear combinación manual]   [Generar combinaciones ▾]     │
│                                                             │
│  SKU          Combinación         Estado   Default          │
│  ROJO-S       Color:Rojo Talla:S  Activo   ●                │
│  ROJO-M       Color:Rojo Talla:M  Activo                    │
│  AZUL-S       Color:Azul Talla:S  Borrador                  │
│  ...                                                        │
│                                                             │
│  ⚠ 7 combinaciones posibles sin crear                       │
└───────────────────────────────────────────────────────────┘
```

### Flujo "Generar combinaciones" (dry run → confirmación → progreso)

```text
Paso 1 — Selección
┌───────────────────────────────────────────┐
│ Generar combinaciones para: Color × Talla   │
│ [Seleccionar todas] [Seleccionar pendientes]│
└───────────────────────────────────────────┘

Paso 2 — Preview (dry run, sin escribir nada)
┌───────────────────────────────────────────┐
│ Ya existen: 5                               │
│ Se crearán: 7                               │
│ Total final: 12 / 100 (límite del plan)     │
│                                             │
│ ⚠ Ninguna advertencia — dentro del límite   │
│                                             │
│           [Cancelar]   [Confirmar]          │
└───────────────────────────────────────────┘
   (si excediera el límite: banner de error
    bloqueando "Confirmar", con el número exacto
    que sí cabe)

Paso 3 — Progreso (Operation durable, polling a
GET /operations/{id})
┌───────────────────────────────────────────┐
│ Generando combinaciones… 4 / 7               │
│ [██████████░░░░░░░░]                        │
│                                             │
│ ROJO-L      creada                          │
│ AZUL-M      creada                          │
│ AZUL-L      creada                          │
│ VERDE-S     creando…                        │
└───────────────────────────────────────────┘

Paso 4 — Resultado
┌───────────────────────────────────────────┐
│ Completado: 7 creadas, 0 omitidas, 0 fallidas│
│                    [Ver Variantes]           │
└───────────────────────────────────────────┘
   (si hubo fallidas: fila por fila, con motivo,
    igual que el reporte de import masivo de M3.0)
```

Errores de versión obsoleta (`If-Match`), cuota excedida, y combinación duplicada se muestran con
el mismo patrón de error técnico + correlation ID que M3.0 ya estableció en el resto del panel
administrativo (`docs/modules/03-catalog-foundation.md` §9).

## 7. Riesgos (consolidado)

- El recálculo de fingerprint en cada cambio de combinación añade una escritura extra sobre
  `catalog_product_variants` dentro de la misma transacción — mismo tipo de riesgo de hot-spot ya
  señalado para el lock de cuota por tenant en M3.0; a medir antes de escalar, no antes de lanzar.
- Bulk-import heredado podría requerir rediseño completo, no solo desenredo de archivos, cuando se
  aborde M3.9 — si M3.1–M3.8 cambian columnas que un import masivo debería poblar (por ejemplo,
  Options por fila), el rediseño es aún más profundo que solo desenredar los archivos actuales.
- Catalog Admin UX (M3.9) no tiene análisis comparativo propio todavía — el hallazgo en el stash no
  reemplaza el proceso de `CLAUDE.md`; el nombre y el número son definitivos, el alcance detallado no.
- Traducción vía tabla satélite agrega un JOIN a cualquier lectura que necesite nombre localizado —
  mismo costo ya aceptado para Product en M3.0; requiere la misma disciplina anti-N+1.
- "Todas las Options son obligatorias por Variant" (decisión aprobada, revisable solo ante caso de
  negocio real, `catalog-options-domain.md` §9) — riesgo residual bajo, documentado explícitamente
  como la única vía de reapertura.
- El nuevo bloqueo duro de "no retirar Product Option con Variants activas usándola" (decisión
  aprobada, `catalog-options-domain.md` §4) no incluye todavía una operación de migración — un
  usuario que necesite retirar una Option en uso real no tiene camino en M3.1 más que archivar las
  Variants afectadas primero; queda documentado como límite conocido, no como bug.
- `catalog.variant_combinations.max_per_product` y `catalog.variants.max_per_product` son dos
  cuotas independientes con semántica parecida (una cuenta solo Variants con combinación, la otra
  cuenta todas) — riesgo de confusión operativa si no se documentan claramente en el panel de
  entitlements cuando se implemente.

## 8. Trabajo excluido de M3.1 (explícito)

Attributes/Features (M3.2), Collections/Tags (M3.3), Localization/SEO avanzado (M3.4), Assets/Media
(M3.5), Channel/Market Eligibility (M3.6), Metafields/Extensibilidad (M3.7), Search
Projections/Hardening (M3.8), Catalog Administration/Imports/Bulk Actions (M3.9), bulk-import
heredado (congelado), storefronts (congelado), CMS, Builder, Checkout, Pricing, Inventory. Nada de
esto se toca en el diseño de M3.1 ni se implementa en esta entrega.

## 9. Siguiente paso

Diseño funcional y técnico **APROBADO** (2026-07-16), roadmap reconciliado formalmente (sección 1).
Queda pendiente únicamente la autorización explícita de **implementación** — migración, modelo,
endpoint, test, frontend — que sigue sin existir. Este documento y los dos documentos de
arquitectura vinculados constituyen la base de diseño para esa implementación cuando se autorice.
