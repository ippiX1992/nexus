# Options (M3.1) y Attributes/Features (M3.2) — análisis comparativo y propuesta de diseño

> Estado: **propuesta de diseño, no implementada.** Sigue el proceso obligatorio definido en
> `CLAUDE.md` — análisis de PrestaShop, análisis de otras plataformas, tabla de comparación,
> diseño Nexus, y **espera de aprobación explícita antes de escribir código**. Ningún incremento
> posterior a M3.0 está autorizado todavía.

## 0. Estado real de M3.0 (verificado contra GitHub, no contra el README)

Antes de proponer M3.1/M3.2 se verificó el estado de cierre de M3.0 directamente contra la API de
GitHub del repo `ippiX1992/nexus` (repo público, sin necesidad de auth):

| Pregunta | Resultado |
|---|---|
| ¿`feature/catalog-core` publicada? | Sí. `origin/feature/catalog-core` en `47fad54` ("docs: document catalog foundation release candidate"). |
| ¿CI GitHub-hosted en verde? | Sí. Workflow *Nexus Modules 1-2 and Catalog Foundation Quality Gate*, run `29385756346` sobre push a `feature/catalog-core` @ `47fad54` (2026-07-15T03:07:21Z): 4/4 jobs `success` (backend, frontend, Playwright E2E, gate final). |
| ¿Existe Pull Request? | **No.** `GET /repos/ippiX1992/nexus/pulls?state=all` devuelve `[]`. |
| ¿M3.0 integrado a `main`? | **No.** `origin/main` sigue en `0642cd8` ("docs: close identity and platform kernel modules"), anterior a todo el trabajo de catalog-core. Sin commit de merge. |
| ¿Run verde sobre `main`? | Hay runs verdes sobre `main`, pero todos en `0642cd8`/`49bfea76` (Módulos 1-2, pre-Catalog). Ninguno incluye código de Catalog. |
| ¿Tag final creado? | **No.** Solo existe `module-3-catalog-foundation-v0.1.0-rc.1` (release candidate) apuntando a `47fad54`. No existe `...v0.1.0` sin `-rc`. |

**Discrepancia detectada**: el README del proyecto afirma "esta entrega no realiza push" y "su
validación GitHub-hosted está pendiente", pero en los hechos sí hubo push y el CI corrió en verde
dos veces (branch y tag RC). Lo que falta para cerrar M3.0 no es CI ni push — es abrir PR, mergear
a `main` y cortar el tag final sin sufijo `-rc`. Esto es una nota documental, no bloquea lo que
sigue; se deja registrado para no repetir la confusión al cerrar M3.0.

**Corrección posterior (2026-07-16)**: M3.0 Catalog Foundation ya está **CERRADO** — PR #1
integrado a `main` mediante merge commit `59859c3e`, quality gate verde en las tres instancias del
mismo contenido, tag final `module-3-catalog-foundation-v0.1.0`. La condición (a) de más abajo ya
se cumplió; se deja la tabla de verificación de arriba como registro histórico de cómo se detectó
el estado en su momento, sin reescribirla.

**Consecuencia para este documento**: sigue siendo solo la propuesta de diseño para M3.1 y M3.2, a
la espera de que se apruebe explícitamente este diseño (condición (b)) — el cierre de M3.0 no
implica aprobación automática de lo que sigue.

## 1. Separación conceptual (no negociable)

| | Options (M3.1) | Attributes / Features (M3.2) |
|---|---|---|
| Rol | Generan variantes vendibles | Describen el producto |
| Ejemplos | Color, Talla, Capacidad | Potencia, Material, Voltaje |
| Afecta SKU | Sí — cada combinación es (potencialmente) una Variant distinta | No — es metadata del Product, no de la Variant |
| Cardinalidad de valores | Siempre de una lista curada y finita | Puede ser texto libre, número, booleano o lista |
| Concurrencia/duplicados | Riesgo real (dos variantes con la misma combinación) | No aplica — no hay combinación que deduplicar |

Estas dos nociones no comparten tabla base ni lógica de negocio. Comparten únicamente el patrón
estructural (`CatalogResourceMixin`, RLS, archivado lógico) que ya usa todo Catalog.

## 2. Paso 1 — Cómo lo resuelve PrestaShop 9.x

Fuente: `install-dev/data/db_structure.sql` en `github.com/PrestaShop/PrestaShop` (rama `9.1.x`).

| Tabla | Rol | Relevante para |
|---|---|---|
| `attribute_group` (+ `_lang`) | Define una opción ("Color"), `group_type` = select/radio/color | Options |
| `attribute` (+ `_lang`) | Un valor de esa opción ("Rojo"), con `color` hex si aplica | Options |
| `product_attribute` | La variante en sí — SKU, precio delta, peso delta | Ya existe en Nexus (`catalog_product_variants`) |
| `product_attribute_combination` | Unión attribute↔product_attribute, PK compuesta `(id_attribute, id_product_attribute)` | Options |
| `feature` (+ `_lang`) | Define una especificación ("Potencia") | Attributes/Features |
| `feature_value` (+ `_lang`) | Un valor de esa especificación ("1200W"), o texto libre vía `custom` | Attributes/Features |
| `feature_product` | Unión feature↔product↔feature_value | Attributes/Features |

**Problema que resuelve**: separar "lo que compone el SKU" de "lo que describe el producto", con
un modelo EAV liviano de dos niveles (grupo/valor) para ambos casos.

**Limitaciones de PrestaShop relevantes para no copiar**:
- IDs enteros autoincrementales globales (`id_attribute`, `id_feature`) — sin aislamiento por
  tienda salvo a través de `id_shop` disperso en tablas satélite (`*_shop`), no de RLS.
- `product_attribute_combination` no impide dos valores del mismo `attribute_group` en la misma
  variante a nivel de base — se controla en PHP/JS del admin, no en SQL.
- Ninguna deduplicación de combinaciones a nivel de constraint — dos variantes idénticas del mismo
  producto son posibles si el admin las crea manualmente.
- `feature_value.custom` mezcla "valor de catálogo controlado" y "texto libre por producto" en la
  misma tabla con una columna booleana — funciona, pero es un remiendo, no un modelo tipado.
- Multilenguaje vía columnas `_lang` con `id_lang` repetido en cada tabla satélite (no una tabla de
  traducción reutilizable).

## 3. Paso 2 — Cómo lo resuelven otras plataformas

### VTEX — Catalog API / SKU Specifications

Fuentes: [SKU specifications](https://developers.vtex.com/docs/guides/sku-specifications),
[Specifications](https://developers.vtex.com/docs/guides/specifications),
[SKUs](https://developers.vtex.com/docs/guides/skus).

- Un único concepto, **Specification**, sirve tanto para Options como para Attributes/Features; se
  diferencian con un flag `IsStockKeepingUnit`. Si es `true`, la especificación genera variación de
  SKU y **solo admite `FieldType` Combo o Radio** (lista curada — nunca texto libre ni número: no
  se puede generar una combinación de un campo continuo). Si es `false`, es descriptiva.
- `FieldType` cubre 9 tipos: Text, Multi-line Text, Number, Combo, Radio, Checkbox, y dos variantes
  indexadas para buscador.
- Las especificaciones se agrupan en `FieldGroup` y **se registran a nivel de Categoría**, con
  `CategoryId = null` para aplicar globalmente o una categoría específica para heredar hacia sus
  hijas. Producto y SKU heredan las especificaciones de su categoría y de todas las categorías
  ancestro.
- Cuando una especificación SKU-level está activa para una categoría, es **obligatoria para todos
  los SKUs de esa categoría** — un SKU no se activa hasta tener valor asignado.

**Idea rescatable, la más valiosa de las cuatro plataformas**: el scoping por árbol de categorías
con herencia. Nexus ya tiene exactamente la infraestructura para esto — `catalog_category_closure`
— construida y probada en M3.0. No hace falta inventar herencia nueva, se reutiliza la que ya
existe.

**Lo que no se copia**: unificar Option y Attribute en una sola entidad con un flag. El usuario
pidió explícitamente mantenerlos separados (sección 1), y la separación además evita que un
Attribute de texto libre "se convierta por error" en generador de combinaciones.

### Shopify — Product Options / Variants

Fuentes: [Support high-variant products](https://shopify.dev/docs/storefronts/themes/product-merchandising/variants/support-high-variant-products),
[About combined listings](https://shopify.dev/docs/apps/build/product-merchandising/combined-listings),
búsqueda sobre límites 2026.

- Máximo **3 Options por producto**, límite duro desde siempre y todavía vigente. Es la fuente de
  más quejas documentadas de comerciantes (múltiples artículos de terceros sobre "workarounds").
- Hasta 2048 variantes por producto en el rollout más reciente (antes 100); `product.variants` en
  Storefront API sigue acotado a 250 por razones de rendimiento del tema — hay APIs separadas para
  no forzar la carga de todas las variantes de una.
- **Combined listings**: productos independientes (SKUs, inventarios, a veces hasta vendors
  distintos) presentados como una sola ficha con opciones combinadas — resuelve el límite de 3
  options y el caso "estos productos son variaciones entre sí pero no comparten estructura".
- Fortaleza real: la UX del editor de opciones/variantes en el admin es la referencia de
  simplicidad del mercado.

**Idea rescatable**: el límite de 3 options de Shopify es la razón por la que **no** hay que copiar
un límite tan bajo — es una limitación técnica heredada, no una decisión de producto deseable.
Nexus debe ser más generoso (ver sección 6, entitlements) sin llegar a "sin límite" (riesgo de
explosión combinatoria, sección 7).

**Lo que no se copia**: el modelo de "combined listings" como solución al límite de opciones — es
un parche sobre una limitación propia; Nexus no tiene esa limitación de origen, así que no necesita
el parche.

### BigCommerce — Variants vs. Modifiers

Fuentes: [Variants and Modifiers](https://support.bigcommerce.com/s/article/Variants-and-Modifiers?language=en_US),
[Product Variant Options](https://developer.bigcommerce.com/docs/rest-catalog/product-variant-options).

- Distinción explícita de dos conceptos que **ninguna otra plataforma separa tan claramente**:
  - **Variant Options** → generan SKU propio, inventario propio, precio propio. Máx. 600
    variantes/producto.
  - **Modifiers** → personalización del comprador (grabado, mensaje de regalo, "agregar
    envoltorio") que **no** genera SKU ni inventario propio; el precio se ajusta por regla
    (suma/resta), no por variante independiente. Sin límite de cantidad.
- Inventario solo se trackea a nivel de Variant o de producto base — nunca a nivel de Modifier.

**Idea rescatable**: confirma una decisión que ya estaba tomada en el diseño de Nexus — precio y
stock no viven en Option/Option Value (sección 6) — y expone un tercer concepto, **Modifiers**
(personalización del comprador en el momento de compra), que **no** es ni Option ni
Attribute/Feature. No está pedido por el usuario para M3.1/M3.2 y se deja fuera de alcance
explícitamente (ver sección 9, riesgos) para no romper la separación de dos conceptos que sí pidió.

### Adobe Commerce (Magento) — EAV y Configurable Products

Fuentes: [EAV and Extension Attributes](https://developer.adobe.com/commerce/php/development/components/attributes),
[Configurable product](https://experienceleague.adobe.com/en/docs/commerce-admin/catalog/products/types/product-create-configurable),
[Magento 2 EAV Model — scandiweb](https://scandiweb.com/blog/magento-series-the-eav-model/).

- Modelo EAV puro: `eav_attribute` define el atributo (compartido potencialmente entre tipos de
  entidad), y el valor se guarda en una tabla distinta **por tipo de dato**
  (`catalog_product_entity_varchar`, `_int`, `_decimal`, `_text`, `_datetime`...). Leer un producto
  completo implica un JOIN por cada atributo tipado presente — el motivo histórico de los
  problemas de rendimiento y de reindexado de Magento a escala.
- **Attribute Sets**: plantillas nombradas y reutilizables que agrupan qué atributos aplican a qué
  productos — independiente del árbol de categorías.
- **Configurable Products**: el "padre" es un SKU no vendible que declara qué atributos son
  configurables; cada combinación real es un **Simple Product completo e independiente** (no una
  fila liviana tipo "variant") con su propio SKU, inventario, y hasta su propio conjunto de
  atributos. Más flexible, mucho más pesado — cada variante paga el costo completo de ser una
  entidad Producto.

**Idea rescatable**: Attribute Sets valida, desde un ángulo distinto al de VTEX, que "agrupar
atributos esperados por tipo de producto" es un patrón real y usado en al menos dos plataformas
líderes (VTEX vía categoría, Magento vía attribute set nombrado).

**Lo que no se copia — con motivo explícito**:
- El modelo EAV valor-por-tipo-de-dato. Es la causa raíz de los problemas de rendimiento más
  citados de Magento; Postgres con columnas tipadas (`value_text`/`value_number`/`value_boolean`)
  en una sola tabla de asignación resuelve lo mismo sin el costo de JOIN.
- Variantes como Product completo independiente. Nexus ya resolvió esto mejor en M3.0:
  `catalog_product_variants` es una fila liviana con FK al Product, no un aggregate propio. No hay
  razón para retroceder a un modelo más pesado.
- Attribute Sets como entidad nueva y nombrada: sería una segunda mecánica de agrupación/herencia
  compitiendo con la que ya se decide adoptar de VTEX (categoría + closure table). Tener dos
  mecanismos de herencia para el mismo problema es complejidad sin beneficio — se prefiere
  extender la que Nexus ya construyó y probó en M3.0 antes que importar una segunda.

## 4. Paso 3 — Diseño Nexus

Todas las tablas nuevas heredan `CatalogResourceMixin` (UUID, `tenant_id`, `version`, timestamps,
actor, archivado lógico), FKs compuestas con `tenant_id`, `CheckConstraint` para enums, índices
parciales para invariantes condicionales — exactamente el patrón de
`app/modules/catalog/infrastructure/models.py`. Ninguna tabla nueva omite `FORCE ROW LEVEL
SECURITY`.

### 4.1 M3.1 — Options y combinaciones de variantes

**Tablas** (mantiene el diseño ya circulado, con ajustes menores):

- `catalog_options` — reemplaza `attribute_group`. Campos: `code`, `name`, `input_type`
  (`select`\|`swatch`), `position`, `status`. Tenant-scoped, reutilizable — ver punto 1 abajo.
- `catalog_option_values` — reemplaza `attribute`. Campos: `option_id`, `code`, `value`,
  `swatch_hex` (con `CheckConstraint` de formato hex — mejora sobre el `varchar` libre de
  PrestaShop), `position`, `status`.
- `catalog_product_options` — declara qué Options aplican a un Product y en qué orden. Sin
  equivalente 1:1 en PrestaShop (que lo infiere de las combinaciones existentes); necesario porque
  Nexus crea variantes de forma explícita, no por matriz generada.
- `catalog_variant_option_values` — reemplaza `product_attribute_combination`. PK compuesta
  `(tenant_id, variant_id, option_id, option_value_id)` con `UniqueConstraint(tenant_id,
  variant_id, option_id)` — un valor por Option por variante, **a nivel de base**, no solo de
  aplicación (mejora explícita sobre PrestaShop, sección 2).

**1. ¿Options reutilizables por tenant o pertenecen al Product Type?**
Reutilizables por tenant — mismo nivel que `BrandModel`/`TaxonomyModel`, no scoped a
`catalog_product_types`. "Color" se usa en remeras y en fundas de celular; duplicarlo por tipo de
producto rompe la reutilización sin necesidad. `catalog_product_options` ya resuelve la asignación
real (qué Options usa un Product concreto). No se adopta el "Attribute Set" de Magento como
mecanismo de default sugerido por tipo — ver 4.2 para dónde sí se usa herencia por categoría (VTEX).

**2. ¿Cómo se traducen Options y Option Values?**
El campo base (`name`/`value`) es el fallback tenant-wide, igual que `BrandModel.name`. Si el
tenant sirve storefronts en más de un locale, se agregan tablas satélite
`catalog_option_translations` / `catalog_option_value_translations` (mismo patrón que
`catalog_product_translations`, sin slug ni SEO — no lo necesitan). Ausencia de traducción cae al
campo base, nunca a un locale hardcodeado. No se duplica el campo por locale en la tabla base (así
sí lo hace PrestaShop con sus tablas `_lang` — aceptable ahí, no aquí, porque Nexus ya tiene un
patrón de tabla-satélite establecido y reutilizable).

**3. ¿Cómo se archivan valores ya utilizados?**
`archived_at` (nunca DELETE físico — ni PrestaShop llega a proponer eso). El FK
`fk_catalog_variant_option_values_tenant_value` usa `ondelete=RESTRICT`; archivar es un UPDATE, no
toca el FK, así que las variantes existentes conservan la referencia intacta automáticamente. La
capa de aplicación rechaza asignar un Option Value archivado a una variante *nueva*, pero no oculta
ni rompe la variante que ya lo usa (misma lógica que ya rige SKU/identificadores archivados en
M3.0). Restore/purge queda fuera de alcance, igual que en M3.0 (limitación ya documentada y
aceptada, sección 12 de `03-catalog-foundation.md`).

**4. ¿Cómo se comporta la Variant default existente?**
Sin cambios en su creación atómica (M3.0 sección 1) — sigue creándose sin exigir valores de Option.
Asignar combinación a cualquier variante (default o no) es un `PUT` posterior, opcional. Esto es
deliberadamente más laxo que VTEX (que fuerza el spec SKU-level como obligatorio para toda la
categoría): se prioriza no romper compatibilidad con los 470 productos demo ya cargados en M3.0,
todos de una sola variante sin opciones. Si a futuro se quiere el comportamiento estricto de VTEX
(spec obligatoria por categoría), es una validación de aplicación agregable después, no un cambio
de esquema.

**5. ¿Cómo se genera el fingerprint canónico de combinación?**
Fingerprint = pares `(option_id, option_value_id)` de `catalog_variant_option_values` para esa
variante, **ordenados por `option_id` ascendente** (orden estable de UUID, no depende de posición
de UI ni de orden de creación), formateados `"{option_id}:{option_value_id}"` unidos con `|`.
Ejemplo conceptual, tal como lo planteó el usuario: `option_id:value_id|option_id:value_id`. Se
persiste el **SHA-256** de esa cadena en `catalog_product_variants.combination_fingerprint`
(columna de ancho fijo — igual razón que ya motivó `sku_normalized` separado de `sku` en M3.0), no
la cadena cruda. Nunca se usan nombres traducidos en el fingerprint ni en los eventos — solo IDs.
Variante sin Options asignadas → `combination_fingerprint = NULL` (sin sentinel de string vacío);
el índice único parcial descrito en el punto 6 ya excluye `NULL` de forma nativa en Postgres, así
que el caso "producto sin opciones" (mayoría de los 470 productos demo) sigue sin ningún constraint
nuevo interviniendo. Se recalcula dentro de la misma transacción que escribe
`catalog_variant_option_values`, igual que M3.0 ya hace confirmar/revertir Product+Variant+audit+
outbox juntos.

**6. ¿Cómo impedir combinaciones duplicadas en concurrencia?**
Índice único parcial en `catalog_product_variants`:
`UNIQUE (tenant_id, product_id, combination_fingerprint) WHERE archived_at IS NULL AND
combination_fingerprint IS NOT NULL`. Un índice único de Postgres es seguro bajo concurrencia por
construcción (inserción a nivel de B-tree, no un patrón check-then-act) — no hace falta lock de
aplicación adicional para la corrección, a diferencia de la cuota (sección 8) que sí necesita el
advisory lock porque contar no es atómico por sí solo. La violación del índice se traduce a `409
Conflict`, mismo tratamiento que ya M3.0 da a duplicados en la importación masiva.
`Idempotency-Key` en `PUT /catalog/variants/{id}/option-values` cubre la dimensión de reintento
seguro — es un problema distinto (y complementario) al de unicidad entre variantes distintas.

**7. ¿Cómo evitar generar automáticamente demasiadas combinaciones?**
M3.0 ya eligió "Variants explícitas" — no hay generación automática de matriz, así que el riesgo de
explosión no existe todavía como feature. El límite real hoy es `catalog.variants.max_per_product`
(ya existe, default 100 — más conservador que BigCommerce (600) y el nuevo tope de Shopify (2048),
suficiente para un M3.1 que no auto-genera). Se agrega un techo nuevo sobre cuántas Options puede
declarar un Product (`catalog_product_options`), ver sección 6. Si en el futuro se agrega
generación automática de matriz (no parte de este alcance), ese feature deberá multiplicar
`max_options_per_product` contra el tamaño de cada Option y validar contra
`catalog.variants.max_per_product` **antes** de generar, no después.

### 4.2 M3.2 — Attributes / Features descriptivas

**Tablas:**

- `catalog_attribute_definitions` — reemplaza conceptualmente `feature`. Campos: `code`, `name`,
  `value_type` (`text`\|`long_text`\|`number`\|`boolean`\|`select`), `unit` (nullable, p.ej. "W",
  "V" — Potencia/Voltaje lo necesitan), `position`, `status`. Tenant-scoped reutilizable, igual
  razonamiento que Options.
- `catalog_attribute_values` — solo aplica cuando `value_type = 'select'` (reemplaza
  `feature_value` cuando no es `custom`). Campos: `attribute_definition_id`, `code`, `value`,
  `position`, `status`.
- `catalog_product_attribute_values` — asignación a nivel de **Product** (no Variant — los
  ejemplos del usuario, Potencia/Material/Voltaje, son atributos del producto, no de cada
  variante). Una fila por `(product_id, attribute_definition_id)`. Columnas tipadas
  `value_text`/`value_number`/`value_boolean`/`value_attribute_value_id`, solo una no-nula según el
  `value_type` del `AttributeDefinition` referenciado (`CheckConstraint` de exclusividad) — evita
  el modelo EAV de Magento (una tabla por tipo de dato con JOINs); Postgres puede tener las cuatro
  columnas tipadas en una sola tabla de asignación sin ese costo.
- `catalog_category_attribute_definitions` — declara qué Attribute Definitions son
  esperadas/recomendadas para una Categoría (y se heredan a sus hijas), inspirado en VTEX. Se
  resuelve consultando `catalog_category_closure` (ya existe, ya probado) — no se construye
  mecanismo de herencia nuevo. A diferencia de VTEX, esto es *recomendación* para UX (qué campos
  mostrar primero al editar un Product de esa categoría), no una obligación dura que bloquee
  activación — mantiene la misma laxitud que el punto 4 de M3.1 explica para no romper
  compatibilidad con datos existentes.

No hay fingerprint, no hay problema de combinación duplicada, no hay variante involucrada — este
módulo es estructuralmente más simple que M3.1 porque Attributes no generan SKU.

Traducción: mismo patrón satélite que Options (`catalog_attribute_definition_translations`,
`catalog_attribute_value_translations`), opcional según necesidad de storefront multi-locale.

Archivado: mismo patrón `archived_at` + `ondelete=RESTRICT`; un `AttributeDefinition` archivado deja
de ofrecerse para nuevas asignaciones, las existentes se conservan legibles.

## 5. Tabla de comparación obligatoria

### M3.1 — Options

| Aspecto | PrestaShop | Nexus |
|---|---|---|
| Modelo | `attribute_group`/`attribute`/`product_attribute_combination`, IDs enteros globales, sin RLS | `catalog_options`/`catalog_option_values`/`catalog_product_options`/`catalog_variant_option_values`, UUID, `tenant_id` en toda FK, RLS forzada |
| UX | Generación de matriz de combinaciones en el admin (PHP/JS) | Variantes explícitas (ya definido en M3.0); asignación de combinación vía `PUT` idempotente |
| Limitación | Sin constraint de "un valor por grupo por variante"; sin deduplicación de combinaciones a nivel de base; multilenguaje vía columnas `_lang` repetidas | — |
| Mejora propuesta | — | `UniqueConstraint` un valor por Option por variante; fingerprint SHA-256 + índice único parcial para combinación no repetida, seguro bajo concurrencia real de Postgres; traducción vía tabla satélite reutilizable |

### M3.2 — Attributes / Features

| Aspecto | PrestaShop | Nexus |
|---|---|---|
| Modelo | `feature`/`feature_value`/`feature_product`, valor controlado o `custom` (texto libre) mezclados en la misma tabla vía flag | `catalog_attribute_definitions` tipado (`text`/`long_text`/`number`/`boolean`/`select`) + `catalog_attribute_values` solo para `select` + asignación tipada en columnas separadas |
| UX | Asignación manual por producto, sin herencia por categoría | Herencia opcional de Attributes esperados vía `catalog_category_attribute_definitions`, reutilizando el closure table ya construido en M3.0 (idea tomada de VTEX, no de PrestaShop) |
| Limitación | Sin tipado real de valor (todo es texto o "custom"); sin scoping por categoría | — |
| Mejora propuesta | — | Tipado real a nivel de constraint; recomendación de campos por categoría sin obligar (evita el "bloqueo duro" de VTEX que rompería compatibilidad con datos existentes) |

## 6. Entitlements y límites

| Entitlement | Default propuesto | Referencia |
|---|---|---|
| `catalog.variants.max_per_product` | 100 (ya existe, sin cambios) | Conservador vs. BigCommerce (600) / Shopify (2048) |
| `catalog.options.max_per_tenant` | 200 | Nuevo — cap de master data, mismo espíritu que `catalog.products.max` |
| `catalog.option_values.max_per_option` | 200 | Nuevo |
| `catalog.product_options.max_per_product` | 6 | Nuevo — más generoso que el límite duro de 3 de Shopify (fuente de quejas documentadas), pero acotado para no habilitar explosión combinatoria si a futuro se agrega generación de matriz |
| `catalog.attribute_definitions.max_per_tenant` | 300 | Nuevo |
| `catalog.attribute_values.max_per_definition` | 200 | Nuevo |

Todos los defaults son tunables por tenant (mismo mecanismo de entitlements ya vigente) y se
validan dentro de la transacción vía el advisory lock por tenant que M3.0 ya estableció — no se
introduce un mecanismo de cuota nuevo, se reutiliza el existente.

## 7. Eventos mínimos

M3.1: `catalog.option.created.v1`, `catalog.option.updated.v1`, `catalog.option.archived.v1`,
`catalog.option_value.created.v1`, `catalog.option_value.updated.v1`,
`catalog.option_value.archived.v1`, `catalog.product.options_set.v1`,
`catalog.variant.option_values_set.v1`.

M3.2: `catalog.attribute_definition.created.v1`, `catalog.attribute_definition.updated.v1`,
`catalog.attribute_definition.archived.v1`, `catalog.attribute_value.created.v1`,
`catalog.attribute_value.archived.v1`, `catalog.product.attribute_values_set.v1`.

Payloads mínimos, solo IDs — nunca nombres traducidos ni valores largos en el envelope, mismo
criterio ya usado en M3.0 y explícitamente pedido por el usuario para el fingerprint.

## 8. Pruebas RLS y PostgreSQL obligatorias

- RLS ofensivo por cada tabla nueva (8 en total entre M3.1 y M3.2): sin `app.current_tenant_id` →
  vacío/error; tenant ajeno no lee ni escribe vía UUID adivinado; CRUD directo SQL sigue bloqueado
  por policy.
- Concurrencia real (no mock) contra Postgres: dos transacciones asignando el mismo fingerprint al
  mismo Product simultáneamente → una gana, la otra recibe unique-violation → mapeada a `409`.
- Invariante "un valor por Option por variante": intento de violarlo → constraint error esperado,
  test explícito.
- Invariante fingerprint `NULL` para variante sin Options: múltiples variantes sin combinación
  coexisten sin chocar contra el índice.
- Archivado: Option/Attribute Value archivado sigue legible en asignaciones existentes, rechazado
  en asignaciones nuevas — test funcional, no solo de constraint.
- Cuotas nuevas (sección 6): test de límite alcanzado → respuesta de cuota excedida, mismo patrón
  ya usado para `catalog.products.max`.
- Migración Alembic: upgrade/downgrade de ambas migraciones (M3.1, M3.2) y `base → head` conjunto.
- Reutilización de pool: extender el test ya existente en M3.0 para cubrir las tablas nuevas.

## 9. Riesgos

- El recálculo de fingerprint en cada cambio de combinación añade una escritura extra sobre
  `catalog_product_variants` dentro de la misma transacción — mismo tipo de riesgo de hot-spot que
  M3.0 ya señaló para el lock de cuota por tenant; a medir antes de escalar, no antes de lanzar.
- Separar M3.1 (Options) de M3.2 (Attributes) en dos incrementos implica que entre ambos el
  catálogo tendrá variantes sin especificaciones descriptivas — aceptable, coincide con lo pedido
  explícitamente por el usuario.
- **Modifiers (BigCommerce) queda fuera de alcance a propósito.** Es un tercer concepto genuino
  (personalización del comprador en el momento de compra, sin SKU propio) que no encaja ni en
  Options ni en Attributes/Features tal como el usuario los definió. No se mezcla en M3.1/M3.2; si
  se quiere, es un módulo propio a analizar con el mismo proceso de `CLAUDE.md` cuando corresponda.
- La numeración M3.1=Options / M3.2=Attributes diverge de la tabla ya publicada en
  `docs/modules/03-catalog-foundation.md` sección 13 (que tenía M3.1=Product-Variant avanzado,
  M3.2=Options+Attributes combinados). Hay que reconciliar esa tabla cuando se autorice el primer
  incremento posterior a M3.0, para no dejar dos fuentes de verdad contradictorias.
- Traducción vía tabla satélite (Options y Attributes) agrega un JOIN a cualquier lectura que
  necesite el nombre localizado — mismo costo ya aceptado para Product; el listado administrativo
  de M3.0 tuvo que protegerse explícitamente contra N+1 (sección 9 de ese doc), la misma disciplina
  aplica acá.
- Herencia de Attributes por categoría (`catalog_category_attribute_definitions`) reutiliza el
  closure table, pero cualquier cambio de estructura de categorías (mover un nodo) ya dispara
  reconstrucción transaccional del closure en M3.0 — hay que confirmar que esa reconstrucción no
  deje momentáneamente huérfana la recomendación de Attributes de un subárbol movido (revisar en
  diseño detallado, no bloquea esta propuesta).

## 10. Siguiente paso

Este documento es la propuesta de diseño para M3.1 y M3.2, siguiendo el proceso de `CLAUDE.md`
(pasos 1-4: PrestaShop, otras plataformas, diseño Nexus, tabla de comparación). **No se avanza al
paso 5 (aprobación) por decisión propia** — M3.0 ya cerró formalmente (PR + merge a `main` + tag
final, ver corrección en sección 0), pero eso no aprueba este diseño: queda a la espera de
aprobación explícita del usuario antes de escribir ninguna migración, modelo, endpoint o test.
