# ADR-003 — Envelope de evento único y estable, vía Transactional Outbox

## Estado

Aprobado

## Fecha

2026-07-14

## Contexto

Nexus es event-driven: módulos futuros (Search, Assets, Publishing, Marketplace, Pricing,
Inventory) necesitan reaccionar a hechos de otros módulos sin acceder directamente a sus tablas
privadas. El Platform Kernel (Módulo 2) es el primer módulo en necesitar publicar eventos hacia
afuera, y Catalog (M3.0/M3.1) es el primer consumidor real del mismo contrato.

## Problema

Cómo publicar hechos de dominio de forma confiable (nunca perdidos, nunca publicados si la
transacción que los originó falla) y con un formato que cualquier módulo futuro pueda consumir
sin acoplarse a los detalles internos del módulo que los emite.

## Alternativas consideradas

- **Publicar eventos directamente a un broker externo dentro del mismo commit de aplicación**:
  introduce un fallo de dos fases — la transacción de base de datos puede confirmar mientras la
  publicación al broker falla, o viceversa, dejando estado inconsistente sin forma barata de
  detectarlo.
- **Change Data Capture (CDC) sobre las tablas de dominio**: evita el problema de dos fases, pero
  expone la forma física de las tablas a los consumers, acoplando su esquema interno a contratos
  externos — exactamente lo que Nexus quiere evitar entre módulos.
- **Transactional Outbox** (opción elegida): el evento se escribe en una tabla outbox dentro de
  la misma transacción que el cambio de dominio; un proceso aparte lee la tabla y publica —
  garantiza que el evento existe si y solo si el cambio se confirmó, sin acoplar el contrato al
  esquema físico interno.

## Decisión

Todo evento de dominio en Nexus usa un envelope único y estable (`event_id`, `event_type`,
`event_version`, `occurred_at`, `tenant_id`, `store_id`, `aggregate_type`, `aggregate_id`,
`correlation_id`, `causation_id`, `actor`, `data`), se escribe en la tabla outbox del Platform
Kernel dentro de la misma transacción que confirma el cambio de dominio, y se entrega con
semántica at-least-once. Los módulos de negocio (como Catalog) reutilizan este envelope sin
modificarlo — no definen su propio formato de evento.

## Justificación

Garantizar que un evento exista si y solo si su transacción de origen se confirmó es más valioso
que la latencia mínima que ofrecería publicar directamente a un broker. Un envelope único y
compartido entre todos los módulos evita que cada equipo/módulo invente su propio formato,
reduciendo el costo de integrar un consumer nuevo a "entender un solo contrato", no uno por
módulo productor.

## Consecuencias

- Cualquier módulo nuevo que emita eventos reutiliza el envelope del Platform Kernel tal cual —
  no lo extiende con campos propios fuera de `data`.
- `data` nunca incluye tokens, cookies, secretos, contraseñas, códigos 2FA ni PII innecesaria —
  regla dura, no una guía.
- Los consumers deben ser idempotentes (registrar `(consumer_name, event_id)` antes de producir
  efectos) porque la entrega es at-least-once, nunca exactly-once.
- No hay orden global entre eventos de distintos agregados; los consumers no pueden asumir orden
  de llegada más allá de `aggregate_version` dentro del mismo agregado.
- Cambios dentro de una versión (`v1`) solo pueden ser aditivos; un cambio incompatible requiere
  una nueva versión de evento, no modificar la existente.

## Riesgos

- Un módulo productor que incluya datos sensibles en `data` por error los expone a todos los
  consumers presentes y futuros — mitigado por revisión obligatoria de payload en el proceso de
  diseño de cada módulo (`CLAUDE.md`, punto 6 del proceso obligatorio).
- Sin orden global, un consumer que asuma orden entre agregados distintos puede procesar eventos
  en una secuencia inesperada — mitigado documentando explícitamente esta garantía (o su
  ausencia) en cada catálogo de eventos de módulo.

## Referencias

- `docs/architecture/event-contracts.md`
- `docs/architecture/catalog-events.md` (reutilización sin modificar por Catalog)

## ADRs relacionados

Depende de [[ADR-001-multi-tenancy]] (`tenant_id` es obligatorio en el envelope). Es prerequisito
conceptual de cualquier módulo que necesite reaccionar a hechos de otro módulo (Content, AI,
Marketplace, según `CLAUDE.md` — "Arquitectura de capas").

## Reemplaza o es reemplazado por

Ninguno.
