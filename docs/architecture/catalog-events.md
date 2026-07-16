# Catalog Core — Target and Implemented Event Contracts

> Estado: envelope y 21 eventos de M3.0 implementados; contratos restantes son objetivo futuro.
> Incremento: **M3.0 RELEASE CANDIDATE**; Módulo 3 EN PROGRESO.
> Transporte: outbox/inbox del Platform Kernel.
> Semántica: entrega at-least-once, consumers idempotentes, sin orden global.

## 1. Objetivos

Los eventos de Catalog permiten que Assets, Search, Publishing, Marketplace, Pricing, Inventory y futuras integraciones reaccionen sin acceder a tablas privadas. Deben:

- representar hechos de dominio ya confirmados;
- quedar en el outbox dentro de la misma transacción del agregado;
- preservar tenant, correlación, actor y causalidad;
- admitir replay y duplicados;
- exponer solo datos mínimos y estables;
- evolucionar mediante versiones aditivas o nuevos event types;
- permitir reconstruir proyecciones consultando Catalog cuando el payload no sea suficiente.

No son comandos remotos, webhooks públicos ni un change-data-capture indiscriminado.

## 2. Envelope obligatorio

Catalog reutiliza sin modificar el envelope de `docs/architecture/event-contracts.md`:

```json
{
  "event_id": "uuid",
  "event_type": "catalog.product.created.v1",
  "event_version": 1,
  "occurred_at": "2026-07-14T12:00:00Z",
  "tenant_id": "uuid",
  "store_id": null,
  "aggregate_type": "catalog.product",
  "aggregate_id": "uuid",
  "correlation_id": "uuid",
  "causation_id": "uuid-or-null",
  "actor": {
    "user_id": "uuid-or-null",
    "session_id": "uuid-or-null"
  },
  "data": {}
}
```

Reglas específicas:

- `event_id` es UUID único por ocurrencia, nunca se reutiliza en retry.
- `event_type` termina en `.v1`; `event_version` coincide con esa versión mayor.
- `tenant_id` siempre está presente.
- `store_id` solo se llena cuando el hecho está inequívocamente limitado a una Store, como un assignment; cambios del Product master lo dejan null.
- `aggregate_type` usa nombres estables: `catalog.product`, `catalog.product_type`, `catalog.taxonomy`, `catalog.collection`, `catalog.brand`, `catalog.metafield_definition`, `catalog.import`.
- `aggregate_id` identifica el root que protege la transacción. Un cambio de Variant usa el Product como aggregate root y también incluye `variant_id` en `data`.
- `correlation_id` procede del request, Operation o mensaje causante.
- `causation_id` contiene el event/job/request lógico anterior cuando existe.
- actor de workers conserva user/session originales cuando son fiables y añade identidad de job en `data.operation`; no simula un usuario.

## 3. Convenciones de payload

Todo `data` de evento de agregado incluye:

| Campo | Tipo | Uso |
|---|---|---|
| `aggregate_version` | integer | Descartar eventos viejos y ordenar por agregado |
| `change_source` | string | `api`, `admin`, `import`, `integration`, `system` |
| `changed_fields` | string[] | Nombres de campos públicos, sin valores sensibles |
| `occurred_by_operation_id` | UUID/null | Vincular trabajos largos e imports |

Reglas:

- IDs se expresan como UUID strings.
- Fechas en RFC 3339 UTC.
- Strings de estado y reason codes son contratos, no labels traducidos.
- No se publican descripciones completas, alt text, metafield values privados, archivos, tokens ni credenciales.
- Si un consumer necesita el estado completo, usa la API/port de lectura o la proyección versionada.
- Arrays potencialmente grandes se resumen mediante count y un ID de batch; no se envían miles de miembros en un evento.
- El payload máximo se define y mide antes de implementación; el dispatcher rechaza oversized events de forma observable.

## 4. Catálogo de eventos v1

### 4.1 Product

| Event type | Hecho | Datos adicionales mínimos |
|---|---|---|
| `catalog.product.created.v1` | Product y Variant default confirmados | `product_type_id`, `default_variant_id`, `status` |
| `catalog.product.updated.v1` | Cambiaron datos maestros, traducciones, SEO, tags, attributes o metafields | `change_groups[]`, `locales[]` limitados/resumidos |
| `catalog.product.status_changed.v1` | Cambió draft/active/archived o restore | `from_status`, `to_status`, `reason_code` |
| `catalog.product.product_type_changed.v1` | Se completó transición validada de Product Type | `from_product_type_id`, `to_product_type_id`, `migration_operation_id` |
| `catalog.product.brand_changed.v1` | Cambió Brand | `from_brand_id`, `to_brand_id` |
| `catalog.product.slug_changed.v1` | Cambió slug localizado | `locale_code`, `old_slug`, `new_slug` |

`old_slug` es información pública editorial; el evento no crea redirects. Si una actualización masiva afecta varios locales se emiten eventos por cambio o un evento resumido con referencia a Operation, dentro del límite de payload.

### 4.2 Variant y Options

| Event type | Hecho | Datos adicionales mínimos |
|---|---|---|
| `catalog.variant.created.v1` | Nueva Variant dentro del Product | `variant_id`, `sku`, `status`, `is_default`, `combination_key` |
| `catalog.variant.updated.v1` | Cambiaron SKU, identificadores, attributes, metafields o nombre | `variant_id`, `changed_fields` |
| `catalog.variant.status_changed.v1` | Cambió lifecycle | `variant_id`, `from_status`, `to_status`, `reason_code` |
| `catalog.variant.combination_changed.v1` | Cambió combinación de Option Values | `variant_id`, `old_combination_key`, `new_combination_key`, `option_value_ids` |
| `catalog.product.options_changed.v1` | Cambió definición/orden/valores de Options | `option_ids`, `change_kind`, `affected_variant_count` |

El SKU se expone porque es identificador de integración, no secreto. Los identificadores externos se exponen solo en eventos específicos autorizados o se recuperan por port para evitar divulgar namespaces privados a todos los consumers.

### 4.3 Classification

| Event type | Hecho | Datos adicionales mínimos |
|---|---|---|
| `catalog.taxonomy.created.v1` | Taxonomy creada | `taxonomy_id`, `key`, `status` |
| `catalog.taxonomy.updated.v1` | Cambió metadata/estado | `taxonomy_id`, `changed_fields` |
| `catalog.category.created.v1` | Category creada y closure actualizado | `taxonomy_id`, `category_id`, `parent_id`, `depth` |
| `catalog.category.updated.v1` | Cambió metadata/traducción/estado | `taxonomy_id`, `category_id`, `changed_fields` |
| `catalog.category.moved.v1` | Se movió un subtree sin ciclo | `taxonomy_id`, `category_id`, `old_parent_id`, `new_parent_id`, `affected_descendant_count` |
| `catalog.product.categories_changed.v1` | Cambió clasificación de Product | `product_id`, `taxonomy_ids`, `added_count`, `removed_count` |
| `catalog.collection.created.v1` | Collection manual creada | `collection_id`, `status` |
| `catalog.collection.updated.v1` | Cambió metadata/estado | `collection_id`, `changed_fields` |
| `catalog.collection.membership_changed.v1` | Cambió membresía/orden | `collection_id`, `added_count`, `removed_count`, `reordered_count` |
| `catalog.brand.changed.v1` | Brand creada o modificada | `brand_id`, `change_kind`, `status` |

Una membresía masiva no incluye todos los Product IDs. El consumer invalida/reconstruye por Collection u obtiene páginas del change set asociado a Operation.

### 4.4 Schemas extensibles

| Event type | Hecho | Datos adicionales mínimos |
|---|---|---|
| `catalog.product_type.changed.v1` | Product Type o sus Attribute Definitions cambiaron | `product_type_id`, `change_kind`, `definition_ids`, `affected_product_count` |
| `catalog.metafield_definition.changed.v1` | Cambió definición/esquema | `definition_id`, `namespace`, `key`, `target_type`, `change_kind` |

Los consumers nunca interpretan `constraints` o validation JSON sin comprobar `schema_version`; normalmente vuelven a leer el contrato completo.

### 4.5 Media

| Event type | Hecho | Datos adicionales mínimos |
|---|---|---|
| `catalog.product.media_changed.v1` | Cambiaron asociaciones de Product | `product_id`, `change_kind`, `asset_ids`, `roles` |
| `catalog.variant.media_changed.v1` | Cambiaron asociaciones de Variant | `product_id`, `variant_id`, `change_kind`, `asset_ids`, `roles` |

Los arrays se limitan. Catalog no emite asset URLs ni transformación metadata. Assets puede consumir retire events para recalcular referencias, pero decide retención.

### 4.6 Assignments y elegibilidad

| Event type | Hecho | Datos adicionales mínimos |
|---|---|---|
| `catalog.product.store_assignment_changed.v1` | Alta/cambio/archive de assignment Store | `product_id`, `store_id`, `from_status`, `to_status`, `availability_window` |
| `catalog.product.channel_assignment_changed.v1` | Alta/cambio/archive de assignment Channel | `product_id`, `store_id`, `channel_id`, `from_status`, `to_status` |
| `catalog.product.market_assignment_changed.v1` | Alta/cambio/archive de assignment Market | `product_id`, `store_id`, `market_id`, `from_status`, `to_status` |
| `catalog.product.eligibility_invalidated.v1` | Un cambio de Catalog invalida diagnósticos/proyecciones | `product_id`, `reason_codes`, `target_scope_summary` |

Catalog no emite `product.published`: la publicación pertenece al módulo que cree el release/snapshot para un Environment. `eligibility_invalidated` es una señal de recomputación, no afirma que un target sea ineligible.

### 4.7 Importaciones futuras

| Event type | Hecho | Datos adicionales mínimos |
|---|---|---|
| `catalog.import.accepted.v1` | El manifest fue validado y se creó Operation | `import_id`, `operation_id`, `source_type`, `mode`, `dry_run` |
| `catalog.import.completed.v1` | Finalizó procesamiento | `import_id`, `operation_id`, `result`, `created`, `updated`, `skipped`, `failed`, `report_reference` |
| `catalog.import.rollback_completed.v1` | Terminó compensación lógica autorizada | `import_id`, `operation_id`, `result`, `reverted`, `conflicted`, `report_reference` |

Los eventos individuales de Product/Variant siguen emitiéndose por cada agregado confirmado. El evento de importación resume el batch y no lo reemplaza.

## 5. Ejemplos normativos

### 5.1 Product created

```json
{
  "event_id": "c8e4ef47-77d5-4f63-ae2c-e160117f0190",
  "event_type": "catalog.product.created.v1",
  "event_version": 1,
  "occurred_at": "2026-07-14T18:30:00Z",
  "tenant_id": "cc3be365-59e1-42c9-86fb-24b028cd65f0",
  "store_id": null,
  "aggregate_type": "catalog.product",
  "aggregate_id": "415584cb-bae7-465e-b531-5d907180bfa5",
  "correlation_id": "72d594f1-8939-45c4-bf68-26cebcafc84a",
  "causation_id": null,
  "actor": {
    "user_id": "2ed55d78-7387-43de-9ab4-6fc74bb67bb5",
    "session_id": "1f8fe730-5932-4c3a-a888-e05f620ab315"
  },
  "data": {
    "aggregate_version": 1,
    "change_source": "admin",
    "changed_fields": ["product_type_id", "handle", "internal_name"],
    "occurred_by_operation_id": null,
    "product_type_id": "cc800565-da92-4cc8-895e-eb02899aa6e4",
    "default_variant_id": "7424133b-018d-4807-a86c-fec21f784a00",
    "status": "draft"
  }
}
```

### 5.2 Channel assignment changed

```json
{
  "event_id": "c3482606-9806-4bf0-a65f-d8780bf8c79b",
  "event_type": "catalog.product.channel_assignment_changed.v1",
  "event_version": 1,
  "occurred_at": "2026-07-14T18:40:00Z",
  "tenant_id": "cc3be365-59e1-42c9-86fb-24b028cd65f0",
  "store_id": "f6841c15-92b0-48ce-8a0c-c85b5ac07b95",
  "aggregate_type": "catalog.product",
  "aggregate_id": "415584cb-bae7-465e-b531-5d907180bfa5",
  "correlation_id": "91ec47ec-9df8-48b8-bab6-14dd83b9dc14",
  "causation_id": null,
  "actor": {
    "user_id": "2ed55d78-7387-43de-9ab4-6fc74bb67bb5",
    "session_id": "1f8fe730-5932-4c3a-a888-e05f620ab315"
  },
  "data": {
    "aggregate_version": 14,
    "change_source": "admin",
    "changed_fields": ["status"],
    "occurred_by_operation_id": null,
    "product_id": "415584cb-bae7-465e-b531-5d907180bfa5",
    "store_id": "f6841c15-92b0-48ce-8a0c-c85b5ac07b95",
    "channel_id": "cdb312b1-eb90-4533-93ce-bdff4eef0fa4",
    "from_status": "draft",
    "to_status": "active"
  }
}
```

## 6. Atomicidad y publicación en outbox

Para cada comando:

1. Se abre UoW con tenant context ya establecido.
2. Se carga y bloquea/versiona el aggregate requerido.
3. Se validan RBAC, entitlements, Platform references e invariantes.
4. Se persiste el cambio.
5. Se añade audit evidence.
6. Se inserta el envelope en `platform_outbox_events` en la misma transacción.
7. Se confirma una sola vez.

Si falla el outbox insert, no se confirma el cambio de Catalog. Los tests deben demostrar rollback sin orphan Product ni evento.

El dispatcher supervisado reclama por lease, publica y marca resultado. Retry mantiene el mismo `event_id` para que consumers dedupliquen. Dead-letter no cambia el estado del agregado, pero genera alerta/Operation observable.

## 7. Orden, duplicados y concurrencia

- No existe orden global entre agregados.
- `aggregate_version` es monotónico por aggregate root.
- La clave recomendada de partición es `tenant_id + aggregate_type + aggregate_id`.
- Un consumer registra `(consumer_name, event_id)` en `platform_inbox_events`.
- Si recibe versión menor o igual a su checkpoint, confirma como duplicate/stale.
- Si detecta un gap y requiere estado continuo, vuelve a leer el snapshot actual; no espera indefinidamente.
- Eventos distintos de la misma transacción llevan correlation común y versiones compatibles, pero el consumer no asume publicación multi-evento atómica.

## 8. Matriz de consumers previstos

| Consumer | Eventos principales | Efecto idempotente |
|---|---|---|
| Search Projector | Product/Variant/classification/assignment/media changes | Upsert/tombstone de `CatalogIndexProjection` por versión |
| Publishing | status, assignment, slug, eligibility invalidated | Recalcular eligibility y marcar snapshots stale |
| Assets Reference Tracker | media changed, product/variant archived | Recalcular referencias; nunca borrar directamente |
| Pricing | variant created/status changed | Preparar referencias sin crear precio implícito |
| Inventory | variant created/status changed | Preparar referencias sin crear stock implícito |
| Marketplace Feeds | product/classification/assignment changes | Invalidar feed derivado por target |
| Integration Export | eventos autorizados por tenant | Encolar transformación/webhook con filtros |
| Analytics | hechos no sensibles | Append idempotente a modelo analítico |

No todos los consumers se implementan en Módulo 3. La tabla define contratos futuros y evita acoplamiento directo.

## 9. Evolución y compatibilidad

Cambios compatibles dentro de `.v1`:

- añadir campos opcionales;
- añadir reason/change codes que consumers deban tratar como unknown;
- ampliar metadata no requerida;
- relajar una restricción de lectura.

Requiere `.v2`:

- renombrar/eliminar campos;
- cambiar tipo o significado;
- cambiar aggregate identity;
- hacer obligatorio un campo antes opcional;
- alterar reglas de seguridad o privacidad.

Para una v2:

1. Publicar schema y fixtures.
2. Permitir consumers dual-read.
3. Emitir v1+v2 durante ventana acotada solo si el volumen lo permite.
4. Medir adopción y dead letters.
5. Retirar v1 mediante decisión documentada, nunca silenciosamente.

Los schemas deben validarse en contract tests y registrarse junto al código del módulo; el event name no se recicla.

## 10. Projection invalidation y backpressure

Un cambio puede afectar múltiples facetas del documento Search. En vez de enviar el documento completo:

- el evento señala aggregate/version/change groups;
- el projector agrupa invalidaciones próximas del mismo Product;
- lee una proyección consistente después del último evento observado;
- hace upsert por versión;
- aplica rate limits y retry del Kernel;
- produce tombstone al archivar o retirar todos los assignments activos.

En importaciones masivas, el dispatcher no se omite. Se usan batches pequeños, límites de outbox pendientes, pausa por backpressure y métricas de lag. Un resumen de import no reemplaza eventos por aggregate.

## 11. Seguridad y privacidad

- El dispatcher establece tenant context antes de leer payloads o enriquecer eventos.
- Suscripciones internas tienen allowlist de event types y propósito.
- Webhooks externos futuros reciben un DTO reducido y firmado, no el envelope interno crudo.
- Audit y logs registran event ID/type/tenant/aggregate/correlation, no el payload completo.
- Datos personales no deben formar parte de Catalog; cualquier aparición en metafields se clasifica y filtra.
- `external` identifier namespaces pueden ser confidenciales; no se incluyen en eventos genéricos.
- Un consumer nunca confía en `store_id` para aislamiento: valida también `tenant_id`.

## 12. Observabilidad mínima

Métricas:

- outbox pending/oldest age por tenant y event family;
- publish attempts, latency, retry y dead-letter;
- inbox duplicate/stale/gap;
- projection lag por aggregate version;
- payload size y oversized rejection;
- import event rate y backpressure pauses.

Logs estructurados incluyen `event_id`, `event_type`, `tenant_id`, `aggregate_id`, `correlation_id`, attempt y resultado. Alertas se disparan por oldest age, dead-letter y gaps persistentes.

## 13. Plan de pruebas de contratos

- Schema contract por cada event type y fixture v1.
- Envelope rechaza ausencia de tenant/correlation/version.
- Product master events tienen `store_id = null`.
- Assignment event incluye Store correcta y mismo tenant.
- Cambio + outbox confirman o revierten juntos.
- Retry conserva event ID; consumer aplica efecto una vez.
- Eventos desordenados no regresan proyección.
- Unknown additive field no rompe consumer v1.
- Payload no contiene campos prohibidos.
- Importación masiva respeta tamaño, batch y backpressure.
- Archive produce invalidación/tombstone observable.
- RLS impide que dispatcher/worker lea eventos de otro tenant sin cambiar contexto.

## 14. Decisiones abiertas antes de implementación

1. Límite exacto de payload y batch según capacidad de broker/runtime.
2. Lista de external identifier namespaces autorizados por tenant.
3. Si slug changes requieren un evento por locale o resumen en imports.
4. Política de dual emission para futuras versiones.
5. SLO de outbox lag y dead-letter recovery.
6. Retención de event evidence y vínculo con Operations.

Ninguna decisión abierta justifica usar acceso directo de consumers a tablas Catalog.

## 15. Eventos materializados en M3.0

La implementación emite únicamente:

- `catalog.product_type.created.v1`;
- `catalog.product_type.updated.v1`;
- `catalog.product_type.archived.v1`;
- `catalog.product.created.v1`;
- `catalog.product.updated.v1`;
- `catalog.product.activated.v1`;
- `catalog.product.archived.v1`;
- `catalog.variant.created.v1`;
- `catalog.variant.updated.v1`;
- `catalog.variant.archived.v1`;
- `catalog.brand.created.v1`;
- `catalog.brand.updated.v1`;
- `catalog.brand.archived.v1`;
- `catalog.taxonomy.created.v1`;
- `catalog.category.created.v1`;
- `catalog.category.updated.v1`;
- `catalog.category.moved.v1`;
- `catalog.category.archived.v1`;
- `catalog.product.assigned_to_category.v1`;
- `catalog.product.assigned_to_store.v1`;
- `catalog.product.unassigned_from_store.v1`.

Todos reutilizan el envelope de Platform Kernel, llevan `event_version=1`, correlation/actor/tenant/aggregate y se insertan en el outbox dentro de la transacción del cambio. Los masters usan `store_id=null`; los eventos de Store identifican la Store. Idempotency replay no duplica eventos y rollback no deja eventos huérfanos.

No se implementan todavía eventos de Options, Attributes, Collections, Tags, media, imports, publicación, eligibility completa ni Search projection. `active` no produce ni implica `published`; ese hecho pertenece a Publishing futuro.
