# ADR-001 — Multi-tenancy real con `tenant_id` compartido, no aislamiento físico

## Estado

Aprobado

## Fecha

2026-07-14

## Contexto

Nexus se diseña desde el inicio como SaaS multi-tenant (Módulo 1 — Identidad y Multi-Tenant).
Cada tenant es un cliente independiente con sus propios usuarios, datos y configuración, sobre
una única base de código y un único despliegue de aplicación.

## Problema

Cómo aislar los datos de cada tenant de forma que sea imposible, no solo improbable, que un
tenant lea o modifique datos de otro — sin renunciar a la simplicidad operativa de un único
esquema y un único despliegue.

## Alternativas consideradas

- **Base de datos por tenant**: aislamiento físico máximo, pero migraciones, backups y
  observabilidad se multiplican por cada tenant; inviable operar a escala con un equipo pequeño.
- **Esquema por tenant** (un `CREATE SCHEMA` por cliente): aislamiento fuerte, pero migraciones
  N veces por release y límites prácticos de PostgreSQL en número de esquemas/conexiones.
  Además, un router debe resolver qué esquema usar clase por request, sumando una capa de
  abstracción no capturada por RLS.
- **Esquema compartido, aislamiento solo a nivel de aplicación** (columna `tenant_id` + filtro en
  cada query): rápido de implementar, pero cualquier query sin `WHERE tenant_id = ...` es una
  fuga de datos entre tenants — depende enteramente de que cada desarrollador nunca lo olvide.
- **Esquema compartido con `tenant_id` en cada tabla + Row Level Security forzada a nivel de
  PostgreSQL** (opción elegida, ver [[ADR-002-row-level-security]]): un único esquema, migraciones
  únicas, pero el aislamiento lo garantiza la base de datos, no la disciplina del desarrollador.

## Decisión

Nexus usa un esquema PostgreSQL compartido por todos los tenants. Toda tabla que contiene datos
de un tenant incluye una columna `tenant_id`, y el aislamiento real se aplica mediante Row Level
Security forzada (ver ADR-002), no mediante confiar en que cada query de aplicación filtre
correctamente.

## Justificación

Un único esquema mantiene las migraciones, el versionado y la observabilidad simples y uniformes
para todos los tenants, algo crítico para un equipo pequeño operando muchos incrementos en
paralelo. El riesgo de fuga de datos entre tenants que introduce el esquema compartido se
neutraliza empujando el aislamiento a la capa de base de datos (RLS), en vez de depender de que
cada desarrollador — humano o agente — recuerde añadir el filtro correcto en cada query nueva.

## Consecuencias

- Toda tabla nueva de cualquier módulo debe incluir `tenant_id` desde su migración inicial; no
  hay excepción para tablas "internas" o "de solo lectura".
- Las FKs internas siempre incluyen `tenant_id` en la relación, no solo el ID del recurso
  referenciado, para que el propio motor de base de datos impida referencias cross-tenant.
- El aislamiento no depende de disciplina de código de aplicación — se verifica ofensivamente
  (ver ADR-002) en cada módulo antes de cerrarlo.
- Todos los tenants comparten capacidad de cómputo y de base de datos; un tenant con carga
  anómala puede afectar a otros si no hay límites de recursos (riesgo, ver abajo).

## Riesgos

- Ruido/carga de un tenant grande puede degradar a otros al compartir instancia de PostgreSQL —
  no mitigado todavía con límites de recursos por tenant.
- Un bug en una migración que olvide `tenant_id` en una tabla nueva pasa desapercibido hasta que
  se detecta en revisión o en el test de RLS ofensivo del módulo correspondiente.

## Referencias

- `docs/architecture/MASTER_ARCHITECTURE.md`
- `docs/modules/01-identity-tenancy.md`

## ADRs relacionados

[[ADR-002-row-level-security]] implementa el mecanismo de aislamiento que este ADR exige.

## Reemplaza o es reemplazado por

Ninguno.
