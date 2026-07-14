# Operations y jobs durables

Una operation representa progreso visible al usuario: `queued`, `running`, `succeeded`, `failed` o `cancelled`. Guarda tenant, actor, correlation ID, progreso, resultado seguro y timestamps. Solo puede consultarse dentro del tenant y con `operation.read`.

Un job representa trabajo ejecutable. Los workers reclaman jobs atómicamente con `FOR UPDATE SKIP LOCKED`, asignan owner y lease, y recuperan leases expirados. Los retries usan backoff y respetan `max_attempts`; el error se sanitiza.

Jobs y operations son conceptos distintos: un job puede implementar una operation y una operation puede coordinar varios jobs. El Módulo 2 incluye solo mecanismos y un uso interno de demostración; no incorpora publicación, catálogo ni ecommerce.
