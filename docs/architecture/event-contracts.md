# Event contracts

Los eventos públicos del Platform Kernel usan un envelope estable:

```json
{
  "event_id": "uuid",
  "event_type": "platform.store.created.v1",
  "event_version": 1,
  "occurred_at": "RFC3339 UTC",
  "tenant_id": "uuid",
  "store_id": "uuid|null",
  "aggregate_type": "store",
  "aggregate_id": "uuid",
  "correlation_id": "uuid",
  "causation_id": "uuid|null",
  "actor": {"user_id": "uuid|null", "session_id": "uuid|null"},
  "data": {}
}
```

La versión forma parte del tipo y del campo `event_version`. Dentro de v1 solo se permiten cambios aditivos. No se incluyen tokens, cookies, secretos, contraseñas, códigos 2FA ni PII innecesaria.

Eventos iniciales: created/updated/archived para Store, Site, Channel, Environment y Market; además Store emite activated y suspended.

La entrega es at-least-once. Los consumidores deben registrar `(consumer_name, event_id)` en inbox antes de producir efectos. `correlation_id` se propaga desde HTTP; `causation_id` enlaza eventos derivados.
