# ADR-006 — Product es master tenant-owned; asignación a Store no es publicación

## Estado

Aprobado

## Fecha

2026-07-16

## Contexto

M3.0 Catalog Foundation introduce Product y Variant en un sistema que ya soporta multi-Store por
tenant (Módulo 2 — Platform Kernel: Stores, Sites, Channels, Environments, Markets). Había que
decidir dónde vive el dato maestro de un Product frente a las múltiples Stores de un tenant, y
qué significa que un Product esté "disponible" en una Store concreta.

## Problema

Cómo modelar Product/Variant de forma que un tenant con varias Stores no duplique su catálogo por
Store, evitando a la vez que "existir" en el sistema se confunda con "estar publicado" en un
canal de venta concreto — dos conceptos que PrestaShop y otras plataformas suelen mezclar.

## Alternativas consideradas

- **Product propiedad de una Store** (una fila de Product por Store): duplica datos maestros
  entre Stores del mismo tenant y complica cualquier operación que afecte al Product en todas
  sus Stores a la vez (por ejemplo, cambiar su Product Type).
- **Registrar cada Product en `platform_resource_scopes`** (el registry general de recursos del
  Platform Kernel): convertiría ese registry en un hot path de millones de filas para un volumen
  de catálogo que no lo necesita — el registry está pensado para recursos administrativos, no
  para el volumen de un catálogo de productos.
- **`active` implica automáticamente publicado en todas las Stores asignadas**: simplifica el
  modelo pero elimina la posibilidad real de tener un Product activo internamente sin exponerlo
  todavía en ningún canal — un caso de uso legítimo (preparar catálogo antes de publicarlo).
- **Product tenant-owned (no Store-owned), con asignación explícita y separada a Store, y
  `active` desacoplado de `published`** (opción elegida): un solo dato maestro por tenant,
  asignación a Store como relación explícita y administrativa, sin usar el registry general del
  Kernel.

## Decisión

Product y su Variant default son propiedad del tenant, no de una Store — se crean atómicamente y
existen una sola vez por tenant sin importar cuántas Stores tenga. La asignación de un Product a
una Store (`catalog_product_stores`) es una relación explícita y administrativa, separada del
master, y `active` en el Product **no implica ni produce** `published` — ese concepto pertenece a
un módulo de Publishing futuro, no a M3.0. Catalog no registra cada Product en
`platform_resource_scopes`; usa ownership por tenant, RLS forzada (ver [[ADR-002-row-level-security]])
y assignments tenant/store-aware en su lugar. SKU e identificadores permanecen reservados a nivel
de tenant incluso después de archivar un Product — nunca se reutilizan.

## Justificación

Separar "existir en el catálogo del tenant" de "estar publicado en una Store" evita el error
común de mezclar ambos conceptos, y deja espacio explícito para el módulo de Publishing futuro sin
tener que rediseñar Catalog cuando llegue. Evitar el registry general del Kernel para Products
individuales mantiene ese registry utilizable para lo que fue diseñado (recursos administrativos),
no para volumen de catálogo.

## Consecuencias

- Cualquier módulo futuro que necesite saber "¿este Product está publicado?" no puede
  preguntárselo a Catalog — esa pregunta pertenece al futuro módulo de Publishing/Content.
- Cambiar el Product Type, Brand o datos maestros de un Product afecta automáticamente a todas
  sus Stores, sin necesidad de propagarlo manualmente Store por Store.
- SKU e identificadores archivados quedan reservados permanentemente — un tenant no puede
  reutilizar un SKU de un Product archivado para uno nuevo, lo cual es una restricción
  intencional, no un descuido.
- El volumen de catálogo (potencialmente millones de Products/Variants a través del tiempo) nunca
  presiona al registry general de recursos del Platform Kernel.

## Riesgos

- Sin un módulo de Publishing todavía implementado, la ausencia de un concepto de "publicado" es
  una limitación real hoy, no solo una separación de responsabilidades — un tenant no tiene forma
  de controlar visibilidad de cara al comprador final todavía.
- La reserva permanente de SKU podría sorprender a un tenant que no entienda por qué no puede
  reutilizar un código después de archivar un Product — riesgo de UX, no de datos.

## Referencias

- `docs/modules/03-catalog-foundation.md`
- `docs/architecture/catalog-data-model.md`
- `docs/architecture/MASTER_ARCHITECTURE.md` sección 5 (Commerce)

## ADRs relacionados

Depende de [[ADR-001-multi-tenancy]] y [[ADR-002-row-level-security]]. Es prerequisito de
[[ADR-007-variant-fingerprint]] (las combinaciones de Variant viven dentro de este mismo modelo
de ownership).

## Reemplaza o es reemplazado por

Ninguno.
