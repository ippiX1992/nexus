# Catalog Options — Domain Design (M3.1)

> Estado: **propuesta de diseño, no implementada.** Sigue el proceso de `CLAUDE.md`. Depende del
> análisis comparativo ya hecho en
> [catalog-options-attributes-prestashop-mapping.md](catalog-options-attributes-prestashop-mapping.md)
> (PrestaShop, VTEX, Shopify, BigCommerce, Adobe Commerce) — este documento no repite esa
> investigación, la aplica a las decisiones concretas de dominio que M3.1 necesita. No incluye
> Attributes/Features descriptivos (M3.2) ni combinaciones/fingerprint (ver
> [catalog-option-combinations.md](catalog-option-combinations.md)).

## 1. Conceptos

| Concepto | Rol | Análogo en M3.0 |
|---|---|---|
| **Option** | Define una dimensión de variación vendible ("Color", "Talla") | `ProductTypeModel`/`BrandModel` (master data tenant-scoped) |
| **Option Value** | Un valor concreto de esa dimensión ("Rojo", "XL") | `CategoryModel` (hijo de un padre tenant-scoped) |
| **Product Option** | Declara que un Product concreto usa una Option, y en qué posición | `ProductCategoryModel` (tabla de asignación) |
| **Variant Option Value** | La combinación real: qué Option Value tiene cada Variant para cada Option | Sin análogo directo — nuevo en M3.1, ver `catalog-option-combinations.md` |

Ninguno de los cuatro genera SKU por sí mismo. La `ProductVariantModel` (M3.0) sigue siendo la
única entidad que representa una fila vendible con SKU; Options y Option Values solo la describen.

## 2. Decisión obligatoria — Ownership de Options

### 2.1 Alternativas comparadas

| Alternativa | Descripción | Precedente | Ventaja | Limitación |
|---|---|---|---|---|
| **A — Option global por tenant** | Una Option ("Color") existe una sola vez por tenant, se reutiliza en cualquier Product | `BrandModel`/`TaxonomyModel` (M3.0), `attribute_group` (PrestaShop, sin scoping real) | No duplica vocabulario; consistente con el patrón ya establecido en M3.0 para master data | Sin mecanismo propio de "qué Options son típicas de qué tipo de producto" — hay que resolverlo aparte |
| **B — Option dentro de Product Type** | Cada `ProductTypeModel` es dueño de su propio set de Options; "Color" en Ropa y "Color" en Electrónica son filas distintas | Ninguna de las 5 plataformas analizadas lo hace así; es el opuesto del patrón VTEX (categoría) y Magento (Attribute Set) | Aislamiento total entre tipos, cero riesgo de reutilización incorrecta | Duplica vocabulario (N Options "Color" para N tipos); rompe reportes/agregaciones cross-type; contradice el patrón ya usado por `BrandModel` en M3.0 |
| **C — Option exclusiva del Product** | Cada Product crea sus propias Options desde cero, sin catálogo compartido | Magento permite esto vía atributos ad-hoc, pero lo desaconseja (mismo problema de EAV disperso) | Máxima flexibilidad por producto | Imposible de gobernar a escala (470 productos demo → hasta 470 Options "Color" distintas); imposible reportar/filtrar por Option a nivel catálogo; sin reutilización |

### 2.2 Decisión aprobada (2026-07-16)

**Alternativa A — Option reusable tenant-wide**, con `catalog_product_options` (ya diseñada en el
documento comparativo) resolviendo el uso específico por Product, y herencia opcional por
categoría (patrón VTEX, ya factible porque `catalog_category_closure` existe desde M3.0) como
mecanismo de sugerencia — nunca de restricción dura.

**Impacto de la recomendación**:
- Reutilización real: "Color" se define una vez, se usa en remeras y en fundas de celular.
- `catalog_product_options` (M3.0-style junction table) es la única fuente de verdad de "qué usa
  este Product" — un Product Type NO restringe qué Options puede usar un Product; puede
  *sugerir* (UX, no constraint) vía herencia de categoría, igual que el punto 4.2 ya propuesto para
  Attributes/Features en el documento comparativo.
- Nada impide que a futuro se agregue una tabla `catalog_product_type_options` puramente
  informativa (defaults sugeridos al crear un Product de ese tipo) — está fuera de alcance de M3.1,
  no es necesaria para que el modelo funcione.

**Riesgo de la recomendación**: sin restricción dura por tipo, nada impide asignar "Talla de
calzado" a un Product de tipo "Electrónica" por error de UX. Se mitiga en la capa de aplicación
(sugerencia visible, no bloqueo) — es la misma laxitud ya aceptada para Attributes/Features en el
documento comparativo, sección 4.2, y evita construir dos mecanismos de restricción distintos para
el mismo problema.

## 3. Unicidad

| Regla | Alcance | Mecanismo |
|---|---|---|
| `code` de Option único | Por tenant | `UniqueConstraint(tenant_id, code)` |
| `code` de Option Value único | Por Option (no por tenant — "S" puede repetirse en "Talla Ropa" y "Talla Calzado" si en el futuro coexisten como Options distintas) | `UniqueConstraint(tenant_id, option_id, code)` |
| Nombres traducibles | Sí — ver sección 5 | Tabla satélite, no columna `_lang` repetida |
| Códigos internos estables | `code` nunca cambia una vez creado (es el ancla de integraciones/import); `name`/`value` sí son editables | Regla de aplicación, no constraint de base — mismo criterio que `BrandModel.code` en M3.0 |
| Archivado lógico | Nunca DELETE físico | `archived_at`, `ondelete=RESTRICT` en toda FK entrante |
| No reutilización insegura de códigos | Un `code` archivado **no se libera** para una nueva Option/Option Value — evita que integraciones viejas (por ejemplo, un import que todavía referencia el `code` archivado) apunten sin saberlo a una entidad nueva y distinta | El `UniqueConstraint` no excluye filas archivadas (a diferencia del índice parcial de "un default por Product" en M3.0, que sí excluye archivadas) — aquí la unicidad es total, incluyendo archivadas, exactamente como ya rige para `sku_normalized` y `catalog_product_identifiers` en M3.0 |

## 4. Archivado

| Entidad | Regla al archivar |
|---|---|
| **Option** | Se permite archivar aunque tenga Option Values activos o esté en uso — el archivado es sobre la Option como *disponible para nuevas asignaciones*, no borra su historial. Bloquea: crear nuevas Option Values bajo ella, agregarla como Product Option nueva. No bloquea: Products que ya la usan siguen funcionando. |
| **Option Value** | Igual criterio. Una Variant que ya tiene asignado un Option Value archivado conserva la asignación y sigue siendo una Variant válida y vendible. Bloquea: asignarla a una Variant *nueva*. |
| **Product Option** | **Aprobado (revisión 2026-07-16): no se permite retirar una Product Option mientras existan Variants activas que la utilicen** — a diferencia del diseño original de este documento (que permitía retirar y dejar la combinación como histórica), la operación de des-asignar queda bloqueada por completo si hay al menos una Variant activa con un valor de esa Option. No hay retiro parcial ni modificación silenciosa de combinaciones existentes. Retirar una Option de un Product sin ninguna Variant activa que la use sí se permite. Una operación explícita de migración o archivo lógico (mover las Variants afectadas a un estado seguro antes de permitir el retiro) queda **fuera de alcance de M3.1** — se ofrecerá en un incremento futuro. |
| **Variant asociada** | Sigue las reglas de `ProductVariantModel` ya vigentes en M3.0 — `archived_at`, sin purge, sin restore. |
| **Combinación histórica** | No es una entidad separada — es el estado resultante de una Variant cuya Option Value o Product Option fue archivada/retirada después de crear la combinación. Se conserva legible, nunca se re-valida retroactivamente. |
| **Productos archivados** | Un Product archivado no permite nuevas Options, Option Values ni combinaciones — mismo criterio que M3.0 ya aplica a Variants de un Product archivado. |

**No se permite borrado físico normal en ningún caso** — ni siquiera vía endpoint administrativo
"forzado"; el único mecanismo de baja es `archived_at`. Restore y purge quedan fuera de alcance de
M3.1, igual que quedaron fuera de alcance de M3.0 (limitación ya documentada y aceptada).

## 5. Traducciones

Mismo patrón que M3.0 usa para `catalog_product_translations`, sin slug ni SEO (Options/Values no
tienen URL propia):

- `catalog_options` / `catalog_option_values` mantienen `name`/`value` como fallback tenant-wide
  (igual que `BrandModel.name`).
- `catalog_option_translations(tenant_id, option_id, locale, name)` y
  `catalog_option_value_translations(tenant_id, option_value_id, locale, value)` son satélites
  opcionales — se pueblan solo para los locales que un storefront realmente necesita.
- Ausencia de traducción para un locale cae al campo base — nunca a un locale hardcodeado ni a
  cadena vacía.
- Columnas completas en `catalog-option-combinations.md` sección 3 (modelo de datos).

## 6. Orden

`catalog_options.position` (orden entre Options del tenant, usado como default cuando una Option
no tiene posición específica en un Product) y `catalog_product_options.position` (orden específico
por Product, puede diferir del orden tenant-wide — por ejemplo, un Product puede querer mostrar
"Talla" antes que "Color" aunque el orden general del tenant sea al revés). `catalog_option_values.position`
ordena los valores dentro de su Option (por ejemplo, tallas en orden S/M/L/XL, no alfabético).
Ninguno de los tres campos de posición participa en el fingerprint de combinación (ver
`catalog-option-combinations.md` sección 1) — el fingerprint se ordena por `option_id`, nunca por
posición de UI, para que reordenar en el admin no invalide combinaciones ya creadas.

## 7. Swatches futuros

`catalog_option_values.swatch_hex` (ya definido en el documento comparativo, con
`CheckConstraint` de formato `#RRGGBB`) cubre el caso de color sólido. `catalog_options.input_type`
acepta `select`\|`swatch` — un tercer valor (por ejemplo `image_swatch`, para texturas o patrones
que no son un color plano) queda fuera de alcance de M3.1: el campo `input_type` es un `String`, no
un enum cerrado a nivel de aplicación fuera del `CheckConstraint` actual, así que agregar un tercer
valor a futuro no requiere migración de esquema, solo relajar el `CheckConstraint` y agregar la
columna adicional que ese tipo necesite (por ejemplo `swatch_image_ref`, condicionado a que exista
el módulo Assets — no antes).

## 8. Variant default — comportamiento completo

La `ProductVariantModel.is_default` (M3.0, índice único parcial por Product) es ortogonal a si el
Product tiene Options o no. Reglas por escenario:

| Escenario | Comportamiento |
|---|---|
| **Producto simple sin Options** | Sin cambios respecto a M3.0. La Variant default se crea atómicamente con el Product, sin combinación asignada (`combination_fingerprint = NULL`). Este sigue siendo el caso común — los 470 productos demo de M3.0 quedan exactamente como están, sin ninguna migración de datos. |
| **Primera Option agregada a un Product ya existente (conversión a configurable)** | **Aprobado (revisión 2026-07-16)**: agregar la primera `catalog_product_options` no genera combinaciones automáticamente y no modifica ninguna Variant existente en su contenido, pero la Variant simple existente (sin combinación) pasa a un estado **pendiente de configuración** — un indicador (no necesariamente un nuevo valor de `status`; puede resolverse como una condición derivada: "Product tiene `catalog_product_options` activas Y al menos una Variant activa sin fila en `catalog_variant_option_values`") que la UI usa para exigir acción del usuario. El Product **no se activa como "configurable completo"** mientras exista esa condición — el usuario debe asignarle valores válidos a la Variant existente o crear nuevas combinaciones explícitas. No hay generación automática de combinaciones en este paso. |
| **Creación de nuevas combinaciones** | Cada combinación nueva es una Variant nueva, explícita (`POST /products/{id}/variants` + asignación de combinación), o generada en lote controlado (ver `catalog-option-combinations.md` sección 2). Ninguna combinación nueva se vuelve automáticamente `is_default` — el default no cambia solo. |
| **Conversión de producto simple a configurable** | No es una operación con nombre propio ni un estado de esquema distinto — es simplemente "el Product ahora tiene `catalog_product_options` y la Variant default (u otra) tiene una combinación asignada". No hay bandera `is_configurable`; se deriva de si existe al menos una fila en `catalog_product_options` para ese Product. |
| **Eliminación o archivado de Options** | Ver sección 4 — no afecta la Variant default existente. Si la Variant default tenía una combinación que incluía la Option archivada, conserva la asignación (combinación histórica), no se invalida retroactivamente. |
| **Selección de nueva Variant default** | Si la Variant default se archiva, M3.0 ya exige elegir una nueva default explícitamente (invariante "una sola Variant default por Product" mediante índice único parcial — no permite cero defaults con Variants activas). M3.1 no cambia esa regla; una Variant con combinación puede ser default igual que una sin combinación. La UI (sección 15, wireframes) debe ofrecer el selector de nueva default en el mismo flujo de archivar. |

**Invariante no negociable**: un Product activo nunca queda sin ninguna Variant válida y no
archivada. M3.1 no introduce ninguna operación que pueda dejar un Product en ese estado — el
archivado de la última Variant activa ya está bloqueado desde M3.0 (mismo invariante, sin cambios).

## 9. Reglas de combinación (qué puede tener una Variant)

Cada Variant configurable (con al menos una Option asignada al Product) debe cumplir, verificado en
la capa de aplicación **y** reforzado con constraints de base donde es posible:

| Regla | Nivel | Mecanismo |
|---|---|---|
| Exactamente un Option Value por cada Product Option **obligatoria** | Aplicación (ver decisión pendiente abajo) | Validación en `application/services.py` antes de confirmar la combinación |
| Cero o uno cuando la Option es **opcional** (si se decide permitir Options opcionales) | Aplicación | Idem — ver nota de decisión abajo |
| Ningún valor de Options no asociadas al Product | Base + aplicación | FK compuesta `catalog_variant_option_values → catalog_product_options` (mismo tenant+product+option) |
| Ningún valor de otro tenant | Base | Toda FK es compuesta con `tenant_id`, reforzada por RLS |
| Ningún valor archivado (en asignación **nueva**) | Aplicación | Chequeo explícito antes de INSERT — el constraint de base no puede distinguir "asignación nueva" de "ya existente conservada" |
| Ningún valor duplicado del mismo Option | Base | `UniqueConstraint(tenant_id, variant_id, option_id)` en `catalog_variant_option_values` — un valor por Option por Variant, a nivel de base, no solo de aplicación (mejora ya señalada sobre PrestaShop en el documento comparativo) |

**Decisión aprobada (2026-07-16)**: en M3.1, **todas** las Options declaradas en
`catalog_product_options` son obligatorias para cualquier Variant configurable del Product — no se
implementan Options opcionales. Los cinco precedentes analizados no coincidían: VTEX fuerza
obligatoriedad a nivel de categoría; PrestaShop/Shopify/BigCommerce no distinguen — toda Option
declarada en el producto es efectivamente obligatoria para generar una combinación; esta decisión
sigue el criterio de las cuatro plataformas de e-commerce puro (no VTEX) analizadas. **Esta decisión
es revisable únicamente ante un caso de negocio real** que la justifique — no se reabre por
preferencia de diseño. Si ese caso aparece, opcionalidad es un campo booleano agregable en
`catalog_product_options` sin romper el modelo — no se diseña ahora para no introducir complejidad
no pedida por ningún caso de uso concreto todavía.
