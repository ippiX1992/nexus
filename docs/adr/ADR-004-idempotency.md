# ADR-004 — Idempotencia obligatoria en comandos de creación vía `Idempotency-Key`

## Estado

Aprobado

## Fecha

2026-07-14

## Contexto

Los clientes HTTP (frontend, integraciones) pueden reintentar una request de creación por
timeout, error de red o doble clic, sin saber si la primera request ya se procesó. Sin
protección, esto crea recursos duplicados (Products, Options, Variants, Stores) de forma
silenciosa.

## Problema

Cómo garantizar que reintentar una request de creación de forma idéntica nunca produzca un
recurso duplicado, sin obligar al cliente a coordinar estado adicional más allá de una cabecera.

## Alternativas consideradas

- **Deduplicar por contenido** (hash del body, sin cabecera explícita): dos creaciones legítimas
  con el mismo contenido (por ejemplo, dos Products con el mismo nombre en momentos distintos)
  se tratarían incorrectamente como el mismo intento.
- **Confiar en que el cliente no reintente** (sin mecanismo del lado servidor): depende de
  disciplina del cliente, no es una garantía — el problema reaparece con cualquier integración
  nueva que no lo respete.
- **`Idempotency-Key` explícita por request, con fingerprint de verificación** (opción elegida):
  el cliente decide qué intento lógico representa cada key; el servidor garantiza que la misma
  key con el mismo contenido devuelve el mismo resultado, y la misma key con contenido distinto
  se rechaza en vez de ejecutarse.

## Decisión

Todo comando de creación en Nexus (Stores, Sites, Channels, Environments, Markets, Products,
Options, Variants, y cualquier recurso creado por un módulo futuro) exige la cabecera
`Idempotency-Key`. La identidad de la operación es `(tenant_id, actor_id, method, endpoint,
key)`, y se almacena un fingerprint SHA-256 del método, endpoint y JSON canónico del body. Mismo
key + mismo fingerprint devuelve la respuesta original ya confirmada; mismo key + fingerprint
distinto devuelve `409`; un registro todavía en proceso devuelve `409` con respuesta segura. El
aggregate, el evento de outbox y el registro de idempotencia se confirman en la misma transacción.

## Justificación

Atar la idempotencia a una cabecera explícita, en vez de deducirla del contenido, deja la
decisión de "qué cuenta como el mismo intento" en manos del cliente que realmente sabe si está
reintentando o creando algo nuevo — evita tanto falsos duplicados como falsos idempotency-hits.
Confirmar aggregate, outbox y registro de idempotencia en la misma transacción evita el estado
inconsistente de "el recurso se creó pero el registro de idempotencia no", que reintroduciría el
problema que esto resuelve.

## Consecuencias

- Cada endpoint de creación de cada módulo nuevo debe implementar este mismo contrato — no es
  opcional ni un patrón "cuando convenga".
- Dos requests concurrentes con la misma key se serializan por constraint único y bloqueo de
  fila, no por lógica de aplicación — el ganador lo decide PostgreSQL.
- Los registros de idempotencia expiran y requieren limpieza periódica (job durable) para no
  crecer indefinidamente.
- Nunca se persisten headers de autorización, cookies o secretos en el fingerprint ni en el
  registro almacenado.

## Riesgos

- Un cliente que reutilice la misma `Idempotency-Key` para dos operaciones lógicamente distintas
  (bug del cliente, no del servidor) recibe `409` en vez del resultado esperado — comportamiento
  correcto pero puede confundirse con un fallo del servidor si no se documenta bien de cara al
  consumidor de la API.
- Sin la limpieza periódica de registros expirados, la tabla de idempotencia crece sin límite —
  mitigado por el job de limpieza ya existente, pero requiere supervisión operativa continua.

## Referencias

- `docs/architecture/idempotency.md`
- `app/modules/platform/application/idempotency.py`

## ADRs relacionados

Depende de [[ADR-001-multi-tenancy]] (la identidad de operación incluye `tenant_id`). Se combina
con [[ADR-003-event-envelope]] en el mismo commit transaccional.

## Reemplaza o es reemplazado por

Ninguno.
