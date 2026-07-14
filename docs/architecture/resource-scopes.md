# Resource scopes

Platform Kernel define una jerarquía común para que los módulos futuros no inventen su propio aislamiento:

```text
tenant
└── store
    ├── site
    ├── channel
    ├── environment
    └── market
```

Cada scope contiene `tenant_id`, `scope_type`, `resource_id`, `parent_scope_id`, estado y timestamps. Un recurso solo puede tener un scope y el parent debe pertenecer al mismo tenant. Los scopes `store` son hijos lógicos del tenant; el resto es hijo del scope del store.

La resolución segura recibe el principal revalidado por el Módulo 1, establece `app.current_tenant_id` en la transacción y consulta el recurso por `(tenant_id, id)`. Los IDs enviados por el cliente nunca determinan por sí solos el tenant. Para operaciones store-scoped también se establece `app.current_store_id`.

Toda tabla tenant-aware nueva usa `tenant_id NOT NULL`, FK a `tenants`, índice cuyo primer campo es `tenant_id`, constraints tenant-aware y RLS forzado. Los workers aplican exactamente el mismo contexto que HTTP.

Los permisos se evalúan en dos pasos: permiso RBAC persistente y pertenencia/estado del scope. Un store archivado no admite hijos nuevos ni configuraciones activas.
