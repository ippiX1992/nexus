# Estrategia de producto y diseño de Nexus

> Este documento define cómo debe abordarse el diseño de **cualquier módulo nuevo** de Nexus.
> Aplica a Claude Code y a cualquier colaborador humano. No es negociable por conveniencia de
> una tarea puntual — si una tarea parece justificar saltarse el proceso, es señal de que hay que
> preguntar antes, no de que el proceso no aplica.

## Objetivo de producto

Nexus toma **PrestaShop** como referencia funcional y arquitectónica principal — no como código a
reutilizar, y no como dependencia exclusiva: el proceso obligatorio de abajo exige contrastar cada
módulo también contra VTEX, Shopify, BigCommerce y Adobe Commerce antes de diseñar nada propio.
PrestaShop marca el punto de partida funcional (UX y cobertura de dominio), no el límite del
análisis. El objetivo es que alguien que ya sabe usar PrestaShop diga *"ya sé usar Nexus"* al
entrar al Back Office, mientras que un desarrollador que mire el código vea una arquitectura
completamente moderna, sin rastro de PHP/Symfony. La ambición funcional es competir con VTEX y
Shopify en capacidad, y sumar capacidades nativas de IA que ninguna de las tres ofrece hoy de forma
integrada.

**Nunca** se adapta Nexus para parecerse técnicamente a PHP, Symfony, o al modelo de datos de
PrestaShop. La arquitectura de Nexus es la arquitectura de Nexus:

- FastAPI (backend) + Next.js (frontend)
- PostgreSQL, siempre con Row Level Security forzada (`FORCE ROW LEVEL SECURITY`)
- Multi-tenant real, aislamiento por `tenant_id` en cada tabla
- RBAC explícito por permiso, sin grants automáticos a roles personalizados
- Event-driven con Transactional Outbox
- Idempotencia obligatoria en comandos de creación (`Idempotency-Key`)
- Optimistic concurrency (`If-Match`/`version`) en updates
- API-first, arquitectura modular con boundaries explícitos entre módulos (ver
  `docs/modules/03-catalog-foundation.md` sección 2 como ejemplo del patrón
  `api/ application/ domain/ infrastructure/ contracts/`)

## Proceso obligatorio antes de diseñar un módulo nuevo

No se implementa nada sin pasar por estos pasos, en orden, con el usuario dando el visto bueno
explícito entre el paso 4 y el 5:

1. **Analizar PrestaShop 9.x**: modelo de datos, entidades, relaciones, reglas de negocio, flujo
   administrativo, UX, APIs, formularios, permisos, traducciones, hooks, limitaciones conocidas.
   Ir a la fuente real (repo/docs de PrestaShop), no a memoria de entrenamiento sin verificar.
   Documentar qué problema resuelve y cómo.
2. **Analizar cómo resuelven el mismo problema otras plataformas**: VTEX, Shopify, BigCommerce,
   Adobe Commerce (Magento). No se copian implementaciones — se extraen únicamente los conceptos
   que mejor resuelven el problema.
3. **Diseñar la solución propia de Nexus**, respetando siempre las restricciones de arquitectura
   listadas arriba.
4. **Producir la tabla de comparación obligatoria** (ver formato abajo) y presentarla junto con la
   propuesta de diseño. Sin esta tabla no hay propuesta completa.
5. **Esperar aprobación explícita del usuario.** Nunca se implementa directamente después del
   análisis, sin importar cuán obvio parezca el diseño.
6. Implementar.
7. Probar (según el estándar de calidad ya vigente en el proyecto: RLS ofensivo, idempotencia,
   concurrencia real contra PostgreSQL, migraciones up/down, RBAC).
8. Documentar (siguiendo el formato ya usado en `docs/modules/`).

### Formato de la tabla de comparación

| Aspecto | PrestaShop | Nexus |
|---|---|---|
| Modelo | | |
| UX | | |
| Limitación | | |
| Mejora propuesta | | |

## Qué tomar de PrestaShop (referencia funcional principal)

Catálogo, Variantes, Opciones, Features (atributos descriptivos), Categorías, Marcas, Fabricantes,
SEO, Productos, Imágenes, Importaciones, Stock, Precios, Reglas de precios, Clientes, Pedidos,
Carritos, CMS, Temas, Módulos, Back Office, Multitienda.

## Qué mejorar respecto a PrestaShop

Arquitectura, escalabilidad, API, UI, rendimiento, IA, automatización, integraciones, marketplace,
builder visual, observabilidad, seguridad, auditoría, multi-tenant real, event sourcing parcial
donde tenga sentido.

## Qué tomar de otras plataformas

- **VTEX**: Stores, Sales Channels, Markets, Sellers, Fulfillment, Marketplace, OMS, Trade Policies.
- **Shopify**: simplicidad, editor, experiencia administrativa, navegación.
- **Builder.io**: editor visual, bloques, componentes reutilizables.

## Qué nunca hacer

No copiar directamente: tablas SQL, clases PHP, código Symfony, nombres internos, estructura de
proyecto, migraciones, licencias, implementaciones propietarias. Solo se usa PrestaShop (u otra
plataforma) como referencia de diseño — se analiza, se comprende, se rediseña.

## Contexto del proyecto

Nexus es una plataforma SaaS multi-tenant (identidad, platform kernel, catálogo — ver
`docs/architecture/MASTER_ARCHITECTURE.md` y `docs/modules/`). El desarrollo avanza por
incrementos numerados con cierre formal (PR, CI verde, merge a `main`, tag). Antes de empezar
un incremento nuevo hay que verificar el estado real del incremento anterior contra GitHub (no
confiar en el README sin verificar) — ver `docs/architecture/catalog-options-attributes-prestashop-mapping.md`
para un ejemplo de esa verificación.
