# Idempotencia HTTP

Las creaciones de Store, Site, Channel, Environment y Market aceptan `Idempotency-Key`.

La identidad de una operación es `(tenant_id, actor_id, method, endpoint, key)`. Se almacena un fingerprint SHA-256 de método, endpoint y JSON canónico.

- Misma clave y fingerprint completado: devuelve status y body originales.
- Misma clave con otro fingerprint: `409`.
- Registro todavía en proceso: `409` con respuesta segura.
- Dos solicitudes concurrentes se serializan por constraint único y bloqueo de fila.
- El aggregate, outbox y respuesta idempotente se confirman en la misma transacción.

Los registros expiran y podrán limpiarse mediante un job durable. Nunca se persisten headers de autorización, cookies o secretos.
