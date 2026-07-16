# Architecture Decision Records (ADR)

Registro histórico de las decisiones arquitectónicas permanentes de Nexus. Un ADR documenta
**por qué** se decidió algo — no cómo se implementa dentro de un módulo concreto (eso vive en
`docs/modules/`) ni las reglas globales de proceso y metodología (eso vive en `CLAUDE.md`).

## Las tres capas de documentación de Nexus

- **`CLAUDE.md`** → metodología y reglas globales: cómo se diseña cualquier módulo nuevo, qué
  plataformas se comparan, qué es obligatorio antes de implementar.
- **`docs/adr/`** (este directorio) → decisiones permanentes de arquitectura: qué se decidió,
  qué alternativas se descartaron y por qué, qué consecuencias y riesgos acepta el proyecto.
- **Documentación de módulos** (`docs/modules/`, `docs/architecture/catalog-*.md`, etc.) →
  implementación específica: cómo un módulo concreto aplica las decisiones ya tomadas en los ADR.

Un ADR no repite el detalle de implementación de un módulo; un documento de módulo no re-explica
ni re-justifica una decisión arquitectónica ya registrada en un ADR — la referencia.

## Cómo crear un ADR nuevo

1. Copiar `template.md` a `ADR-XXX-titulo-en-kebab-case.md`, con `XXX` como el siguiente número
   secuencial de tres dígitos.
2. Completar las 11 secciones del template. Ninguna es opcional.
3. Un ADR se propone (`Estado: Propuesto`) y se aprueba (`Estado: Aprobado`) siguiendo el mismo
   proceso de aprobación explícita del usuario que ya exige `CLAUDE.md` para cualquier decisión
   de arquitectura.
4. Un ADR nunca se edita para cambiar su decisión ya aprobada. Si la decisión cambia, se crea un
   ADR nuevo con estado `Aprobado`, se marca el ADR anterior como `Reemplazado` en su campo
   "Estado", y se completa el campo "Reemplaza o es reemplazado por" en ambos documentos.
5. Un ADR se marca `Obsoleto` cuando la decisión deja de aplicar sin haber sido reemplazada por
   otra (por ejemplo, porque el problema que resolvía dejó de existir).

## Índice

| ADR | Título | Estado |
|---|---|---|
| [ADR-001](ADR-001-multi-tenancy.md) | Multi-tenancy real con `tenant_id` compartido | Aprobado |
| [ADR-002](ADR-002-row-level-security.md) | Aislamiento por Row Level Security forzada | Aprobado |
| [ADR-003](ADR-003-event-envelope.md) | Envelope de evento único vía Transactional Outbox | Aprobado |
| [ADR-004](ADR-004-idempotency.md) | Idempotencia obligatoria vía `Idempotency-Key` | Aprobado |
| [ADR-005](ADR-005-nexus-experience-system.md) | Nexus Experience System (NXS) | Aprobado |
| [ADR-006](ADR-006-catalog-ownership.md) | Product tenant-owned, `active` ≠ `published` | Aprobado |
| [ADR-007](ADR-007-variant-fingerprint.md) | Fingerprint SHA-256 para combinaciones de Variant | Aprobado |

Este índice se actualiza en el mismo commit que crea o cambia el estado de un ADR.
