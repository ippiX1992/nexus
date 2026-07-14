# Transactional outbox e inbox

El outbox pertenece al Platform Kernel. El aggregate y su evento se escriben en la misma transacción PostgreSQL. Un dispatcher reclama filas `pending` o recuperables con `FOR UPDATE SKIP LOCKED`, las entrega mediante una interfaz `EventPublisher` y actualiza `published`, `failed` o `dead_letter`.

No se conecta un broker externo en el Módulo 2. El publicador interno permite pruebas y consumidores locales; un adaptador Kafka/RabbitMQ futuro no cambiará productores.

Inbox garantiza idempotencia por `UNIQUE (consumer_name, event_id)`. El primer consumidor útil crea una operación durable que registra el procesamiento del evento. Reintentos del mismo evento no repiten el efecto.

Outbox e inbox son tenant-aware, usan RLS y no sirven como auditoría permanente. El payload respeta el contrato del envelope y los errores persistidos deben estar sanitizados.
