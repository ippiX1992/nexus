# ADR-002 — Aislamiento por Row Level Security forzada, con contexto por transacción

## Estado

Aprobado

## Fecha

2026-07-14

## Contexto

[[ADR-001-multi-tenancy]] establece que Nexus usa un esquema compartido con `tenant_id` en cada
tabla. Esa columna por sí sola no impide que una query mal escrita omita el filtro y devuelva
datos de otro tenant.

## Problema

Cómo garantizar, a nivel de motor de base de datos y no de disciplina de aplicación, que ninguna
query — presente o futura, escrita por un humano o por un agente — pueda leer o escribir filas de
un tenant distinto al de la sesión actual.

## Alternativas consideradas

- **Confiar en el ORM/capa de aplicación** para añadir `WHERE tenant_id = :current` en cada
  query: fràgil — cualquier query nueva, cualquier `JOIN`, cualquier script de mantenimiento
  puede olvidarlo sin que nada lo impida en tiempo de ejecución.
- **Vistas filtradas por tenant** en vez de RLS: multiplica objetos de base de datos por tabla y
  no cubre `INSERT`/`UPDATE`/`DELETE` directos igual de bien que una policy.
- **Row Level Security de PostgreSQL sin `FORCE`**: RLS normal no aplica a los dueños de tabla ni
  a roles con `BYPASSRLS`; un bug de configuración de rol podría desactivar el aislamiento sin
  que ninguna query lo note.
- **`FORCE ROW LEVEL SECURITY` + políticas explícitas por operación (`SELECT`/`INSERT`/`UPDATE`/
  `DELETE`) + rol de aplicación sin `BYPASSRLS`** (opción elegida): el aislamiento se aplica
  siempre, incluso si una query de aplicación no filtra por tenant, porque PostgreSQL rechaza el
  acceso a nivel de fila antes de que la query se ejecute.

## Decisión

Toda tabla tenant-aware de Nexus habilita `ROW LEVEL SECURITY` y además `FORCE ROW LEVEL
SECURITY`, con cuatro políticas explícitas (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) comparando
contra `app.current_tenant_id`. Ese valor se establece por transacción mediante `SET LOCAL` /
`set_config(..., true)` a partir del tenant ya autenticado y revalidado — nunca a partir de un ID
enviado directamente por el cliente. El rol de aplicación (`nexus_app`) nunca tiene `BYPASSRLS`
ni `SUPERUSER`; esto se verifica ofensivamente en CI.

## Justificación

`FORCE ROW LEVEL SECURITY` mueve la garantía de aislamiento del código de aplicación al motor de
base de datos: incluso una query nueva, mal escrita o generada por un agente sin contexto
completo, no puede leer ni escribir filas fuera del tenant activo, porque PostgreSQL la bloquea
antes de ejecutarla. El alcance por transacción (`SET LOCAL`) evita que el contexto de un tenant
se filtre accidentalmente a la siguiente operación en una conexión reutilizada por un pool.

## Consecuencias

- Cada módulo nuevo debe crear sus 4 políticas por tabla como parte de su migración inicial — no
  es opcional ni se pospone.
- El contexto de tenant se pierde en cada `COMMIT` (por ser `SET LOCAL`, transaccional). Cualquier
  operación de larga duración que haga varios commits (por ejemplo, un job en lote) debe
  re-establecer el contexto después de cada uno — error real ya encontrado y corregido en la
  generación durable de combinaciones de M3.1 (ver `docs/modules/03-1-catalog-options.md` sección 8).
- Cada módulo se verifica ofensivamente antes de cerrarse: acceso cross-tenant vía API debe
  devolver 404 indistinguible, y consultas SQL directas sin contexto deben devolver 0 filas.
- El rol `nexus_app` nunca puede tener `BYPASSRLS`; esto se re-verifica en cada corrida de CI, no
  solo una vez.

## Riesgos

- Un desarrollador o agente que olvide re-establecer `app.current_tenant_id` tras un commit
  intermedio en una operación larga introduce un fallo de escritura (no de fuga de datos, porque
  RLS bloquea) que puede no ser obvio hasta production. Mitigación: patrón documentado y probado
  explícitamente en tests de generación en lote.
- Migraciones que crean una tabla tenant-aware sin sus 4 políticas quedan sin protección real
  hasta que se detecta — mitigado por el test de RLS ofensivo obligatorio por módulo, no por
  revisión manual únicamente.

## Referencias

- `docs/architecture/resource-scopes.md`
- `docs/modules/03-catalog-foundation.md` (evidencia de verificación ofensiva de RLS en M3.0)
- `docs/modules/03-1-catalog-options.md` sección 8 (bug real de contexto perdido en jobs en lote)

## ADRs relacionados

Implementa el aislamiento exigido por [[ADR-001-multi-tenancy]]. Es prerequisito de
[[ADR-006-catalog-ownership]] y de cualquier módulo de negocio futuro.

## Reemplaza o es reemplazado por

Ninguno.
