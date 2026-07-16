# Estrategia de producto y diseño de Nexus

> Este documento define cómo debe abordarse el diseño de **cualquier módulo nuevo** de Nexus.
> Aplica a Claude Code y a cualquier colaborador humano. No es negociable por conveniencia de
> una tarea puntual — si una tarea parece justificar saltarse el proceso, es señal de que hay que
> preguntar antes, no de que el proceso no aplica.

## Objetivo de producto

Nexus toma **PrestaShop, VTEX, Shopify, BigCommerce y Adobe Commerce** como referencia funcional y
de experiencia de usuario — nunca como código, nombres internos, SQL o componentes a reutilizar.
Solo se analiza cómo resuelven un problema; el diseño de Nexus se construye después, propio,
respetando la arquitectura listada abajo. Ninguna de las cinco es un límite del análisis ni un
techo de ambición: son el punto de partida, no el destino.

**Nexus no debe parecer un proyecto hecho desde cero.** Debe sentirse como una plataforma madura
y comercial, comparable con esas cinco, con una arquitectura moderna propia por debajo. El
objetivo funcional es que alguien que ya administra PrestaShop, VTEX o Shopify diga *"ya sé usar
Nexus"* al entrar al Back Office; el objetivo técnico es que un desarrollador que mire el código
vea una arquitectura completamente moderna, sin rastro de PHP/Symfony ni de ningún stack ajeno.
La ambición es competir con VTEX y Shopify en capacidad y experiencia de administración, y sumar
capacidades nativas de IA que ninguna de las cinco ofrece hoy de forma integrada.

### Enterprise First (no negociable)

No se construyen MVPs, demos, ejemplos ni "después lo mejoramos". Cada módulo debe entregarse
listo para venderse a un cliente enterprise. Antes de dar un módulo por terminado, la pregunta
obligatoria es: **¿esto se siente como una plataforma enterprise?** Si la respuesta es no, se
rediseña antes de continuar — no se documenta como pendiente y se avanza.

Esto no reemplaza el estándar técnico ya vigente (arquitectura, dominio, seguridad, RLS, eventos,
pruebas, calidad) — se suma a él. Un módulo con RLS perfecto y RBAC completo pero con una UI que
parece un CRUD generado automáticamente **no está terminado**.

### Evolución paralela obligatoria

El roadmap ya no mide cierre únicamente por incremento de backend. Cada incremento debe entregar
algo visible y usable por un administrador real. No se continúa desarrollando solo backend en un
incremento y solo frontend en el siguiente: backend, frontend, UX y NXS avanzan juntos dentro del
mismo incremento.

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

## Arquitectura de capas: visión de largo plazo

Nexus evoluciona mediante grandes capas independientes que comparten contratos, principios
arquitectónicos y el Nexus Experience System:

- Platform
- Nexus Experience System
- Commerce
- Content
- Builder
- AI
- Marketplace
- Developer Platform
- Infrastructure

Esta clasificación representa una visión de producto y roadmap, **no una estructura de carpetas
obligatoria desde el inicio**. Una capa solo se formaliza en código, contratos y documentación
cuando comienza su primer módulo real. Actualmente tienen trabajo activo: **Platform** (Identidad
y Platform Kernel, Módulos 1 y 2), **Commerce** (inicialmente mediante Catalog) y **Nexus
Experience System**. No deben crearse carpetas, abstracciones ni contratos para capas que todavía
no tengan consumidores reales (Content, Builder, AI, Marketplace, Developer Platform).

## Proceso obligatorio antes de diseñar un módulo nuevo

No se implementa nada sin entregar primero estos 10 puntos, en orden, con el usuario dando el
visto bueno explícito antes de escribir código:

1. **Comparación de plataformas**: cómo resuelve el problema PrestaShop 9.x, luego VTEX, luego
   Shopify, luego BigCommerce, y Adobe Commerce cuando aporte valor. Ir a la fuente real
   (repo/docs de cada plataforma), no a memoria de entrenamiento sin verificar. Para cada una:
   modelo, UX, ventajas, desventajas, limitaciones conocidas.
2. **Decisiones de arquitectura**: cómo encaja en Nexus respetando FastAPI/Next.js/PostgreSQL/
   RLS/RBAC/event-driven+outbox/idempotencia/optimistic concurrency/API-first/modular.
3. **Wireframes**: layout textual o esquemático de cada pantalla nueva (lista, detalle, drawers,
   modales) — suficiente para validar la UX antes de construirla. Antes de dibujar nada, pasar por
   las "Reglas antes de crear una pantalla" de la sección Nexus Experience System.
4. **UX**: navegación, breadcrumbs, filtros, acciones masivas, buscador, estados, badges, paneles,
   drawers, modales, preview, tabs, paginación, empty states, skeleton loaders, notificaciones,
   auditoría visible — cuáles aplican a este módulo y cómo, usando componentes y patrones NXS.
5. **Modelo de datos**: tablas, columnas, constraints, RLS.
6. **Eventos**: qué emite, payload, consumers previstos.
7. **API**: endpoints, convención de errores, idempotencia, concurrencia.
8. **Permisos**: catálogo de permisos y asignación por rol.
9. **RLS**: políticas por tabla y por operación.
10. **Pruebas**: qué se va a probar (RLS ofensivo, concurrencia real, migraciones up/down, RBAC,
    y — a partir de ahora — verificación manual de la UI en navegador, no solo del API).

**Producir la tabla de comparación obligatoria** (ver formato abajo) como parte del punto 1.
Sin ella no hay propuesta completa. Después de los 10 puntos:

11. **Esperar aprobación explícita del usuario.** Nunca se implementa directamente después del
    análisis, sin importar cuán obvio parezca el diseño.
12. Implementar — backend y frontend en paralelo, nunca uno sin el otro dentro del mismo
    incremento (ver "Evolución paralela obligatoria" arriba).
13. Probar (estándar técnico vigente) y verificar la experiencia real en navegador.
14. Documentar (siguiendo el formato ya usado en `docs/modules/`).

### Formato de la tabla de comparación

| Aspecto | PrestaShop | VTEX | Shopify | BigCommerce | Nexus |
|---|---|---|---|---|---|
| Modelo | | | | | |
| UX | | | | | |
| Ventaja | | | | | |
| Limitación | | | | | |
| Mejora propuesta | | | | | |

Adobe Commerce se agrega como columna extra solo cuando aporte valor real al problema concreto —
no por completitud.

## Qué tomar de PrestaShop

Catálogo, Variantes, Opciones, Features (atributos descriptivos), Categorías, Marcas, Fabricantes,
SEO, Productos, Imágenes, Importaciones, Stock, Precios, Reglas de precios, Clientes, Pedidos,
Carritos, CMS, Temas, Módulos, Back Office, Multitienda.

## Qué mejorar respecto a PrestaShop

Arquitectura, escalabilidad, API, UI, rendimiento, IA, automatización, integraciones, Marketplace,
Builder visual, observabilidad, seguridad, auditoría, multi-tenant real, event sourcing parcial
donde tenga sentido.

## Qué tomar de otras plataformas

- **VTEX**: Stores, Sales Channels, Markets, Sellers, Fulfillment, Marketplace, OMS, Trade Policies.
- **Shopify**: simplicidad, editor, experiencia administrativa, navegación.
- **Builder.io** (plataforma externa, no confundir con la capa Nexus **Builder** de
  "Arquitectura de capas"): editor visual, bloques, componentes reutilizables.

Esta lista no es exhaustiva respecto a las cinco plataformas de referencia de "Objetivo de
producto"; se amplía a medida que cada módulo nuevo lo requiera, siguiendo el proceso de
comparación obligatorio.

## Nexus Experience System (NXS)

NXS es la base visual y de experiencia de usuario de toda la plataforma. No es un módulo de
negocio y no implementa reglas comerciales. Su responsabilidad es proporcionar fundamentos
visuales, componentes reutilizables, patrones de interacción, criterios de accesibilidad,
consistencia entre módulos y contratos estables para la interfaz administrativa.

NXS evita que cada módulo construya interfaces con HTML, CSS y comportamientos aislados,
reduciendo el riesgo de terminar con un Back Office inconsistente que requiera una reescritura
completa (el error histórico de PrestaShop y Magento).

Se inspira funcionalmente en VTEX Admin, Shopify Polaris, PrestaShop Back Office, Linear y Figma.
No copia componentes, código, estilos, marcas ni estructuras internas — Nexus mantiene identidad
visual propia.

### Foundation obligatoria

Toda interfaz usa Design Tokens para representar los valores fundamentales y semánticos de color,
tipografía, espaciado, radios, elevación, sombras, movimiento, grid, breakpoints, tamaños, estados
interactivos e iconografía. No se permiten valores visuales arbitrarios o repetidos directamente
en pantallas cuando exista un token equivalente.

Un valor local puede usarse cuando representa una necesidad única y justificada. Si empieza a
repetirse o adquiere significado semántico, debe promoverse a token.

### MX.0 — Nexus Experience System Foundation

Fase previa a M3.2. No modifica el backend, no cambia reglas de Catalog y no introduce nuevas
capacidades comerciales. Su alcance es exclusivamente visual y estructural.

**Entregables:**

- Tokens fundamentales: colores base y semánticos, tipografía, espaciado, radios, sombras y
  elevación, movimiento, breakpoints, estados de foco/error/advertencia/éxito/deshabilitado.
- Estructura administrativa: Admin Shell, Sidebar, Top Navigation, área principal de contenido,
  navegación responsive, selector de tema, soporte Light/Dark/Auto.
- Componentes mínimos: Button, IconButton, Input, Select, Table, Badge, Tabs, Drawer, Modal,
  Toast, Empty State, Skeleton.
- Patrones UX iniciales: CRUD básico, estados vacíos, loading, error handling, confirmaciones,
  feedback de acciones, permisos insuficientes.

**Criterio de aceptación**: MX.0 solo se considera terminado cuando la pantalla real
`/catalog/options` haya sido reconstruida usando exclusivamente tokens NXS, componentes NXS,
patrones NXS y layout administrativo NXS. La validación comprueba: consistencia visual;
funcionamiento en Light, Dark y Auto; navegación por teclado; foco visible; accesibilidad WCAG AA
en los flujos principales; comportamiento responsive en Desktop, Tablet y Mobile; estados de
loading, error, vacío y éxito; ausencia de estilos visuales ad hoc injustificados; pruebas de
componentes; prueba E2E en navegador real; build de producción correcto. Si la pantalla no puede
reconstruirse correctamente con los elementos entregados, MX.0 no está terminado.

**No objetivos de MX.0** (no se construyen especulativamente, se incorporan cuando exista un
consumidor real y un caso de uso aprobado): DatePicker, File Upload, Rich Text Editor, Data Grid
avanzado, Charts, Timeline, Activity Feed, Command Palette, Tree View, Version History,
Marketplace Cards, soporte RTL completo, múltiples idiomas activos, y las capas Content, Builder,
AI, Marketplace, Developer Platform.

### Catálogo de componentes y crecimiento por promoción

El catálogo completo de NXS es una dirección de largo plazo, no el alcance inicial. Puede incluir
en el futuro: Textarea, Checkbox, Radio, MultiSelect, Switch, DatePicker, File Upload, Rich Text
Editor, Data Grid, Metric Cards, Charts, Dialog, Sheet, Tooltip, Breadcrumb, Command Palette,
Search Bar, Pagination, Progress, Filters, Tree View, Cards, Timeline, Activity Feed — y patrones
como Wizards, Bulk Actions, Imports, Exports, Preview, Version History, Audit Timeline, Settings,
Marketplace Cards, Search Experience, Notifications.

**Regla de promoción**: un componente puede nacer dentro de un módulo cuando ese módulo sea su
primer consumidor real. Debe extraerse, estabilizarse y documentarse dentro de NXS cuando: un
segundo módulo necesite el mismo patrón; el componente represente una interacción transversal; la
duplicación afecte consistencia o accesibilidad; o exista evidencia de que su contrato puede
generalizarse. No se crean componentes genéricos sin consumidores reales.

Un módulo puede mantener un componente local si documenta expresamente por qué no pertenece
todavía a NXS, qué condición provocaría su promoción, y qué dependencias específicas impiden
generalizarlo. No existe una prohibición absoluta de componentes locales; existe un proceso
controlado de promoción.

### Versionado

Cuando dos o más módulos dependan de un mismo componente NXS, su contrato se considera estable.
Todo cambio incompatible incluye: impacto identificado, ruta de migración, actualización de
consumidores, pruebas de regresión y documentación del cambio. Cuando la madurez del proyecto lo
requiera, NXS puede adoptar versionado semántico independiente.

### Accesibilidad

Obligatoria desde el primer componente, no se pospone como etapa posterior: WCAG AA como mínimo,
navegación completa mediante teclado, foco visible, semántica HTML correcta, ARIA únicamente
cuando corresponda, contraste suficiente, labels asociados, mensajes de error comprensibles,
soporte para tecnologías de asistencia, y respeto por `prefers-reduced-motion`.

### Responsive

Cada componente y patrón contempla Desktop, Tablet y Mobile. Desktop puede ser la superficie
administrativa principal, pero no se asume como el único entorno disponible. Las tablas complejas
adaptan su comportamiento mediante scroll controlado, ocultación priorizada, vistas resumidas,
drawers, cards o acciones contextuales — nunca se comprimen indiscriminadamente hasta volverse
inutilizables.

### Internacionalización

NXS evita decisiones que impidan internacionalización futura: propiedades lógicas de CSS cuando
corresponda, sin concatenar textos traducibles, contenido separado de presentación, expansión de
texto contemplada, formatos regionales respetados, sin asumir permanentemente una dirección LTR.

MX.0 no implementa todavía RTL completo, múltiples idiomas activos, traducciones de NXS, ni
validación exhaustiva en escrituras no latinas — se implementan cuando exista una necesidad
comercial real.

### Reglas antes de crear una pantalla

Antes de desarrollar una nueva pantalla se responde:

1. ¿Existe un componente NXS equivalente?
2. ¿Existe un patrón UX reutilizable?
3. ¿La necesidad puede resolverse mediante NXS?
4. ¿La experiencia será consistente con el resto de Nexus?
5. ¿El componente ya tiene más de un consumidor?
6. ¿Cumple accesibilidad, responsive y temas?

Cuando no exista una solución NXS: si hay un solo consumidor real, el componente puede nacer
localmente y documentarse como candidato; si existen dos o más consumidores, se evoluciona NXS
antes de duplicar la solución; si el patrón es transversal por naturaleza, se incorpora
directamente a NXS. No se abstrae anticipadamente una necesidad todavía incierta.

### Relación con los módulos de negocio

NXS no debe detener indefinidamente el roadmap comercial. Después de MX.0, los módulos
funcionales continúan avanzando; cada incremento incorpora frontend, UX y componentes reales; NXS
evoluciona a partir de necesidades demostradas; no se construye una biblioteca visual completa
antes de continuar Commerce. El siguiente incremento funcional después de MX.0 se define mediante
la metodología general de Nexus (proceso obligatorio de 10+4 puntos arriba), manteniendo la
evolución paralela de backend, frontend, UX, NXS, pruebas y documentación.

## IA nativa

La IA es una característica nativa de Nexus, no un plugin ni un módulo aparte — corresponde a la
capa AI de "Arquitectura de capas: visión de largo plazo", que se formaliza cuando tenga su primer
módulo real. Hasta entonces, cada módulo nuevo evalúa explícitamente, como parte del punto 4 del
proceso obligatorio (UX), si aplica: generación automática de contenido, autocompletado,
sugerencias, optimización, traducciones asistidas, SEO asistido, procesamiento de imágenes,
sugerencias de variantes/categorías, generación de descripciones. No es obligatorio que cada
módulo implemente IA — es obligatorio que cada módulo se pregunte si debería.

## Regla rectora

Cuando exista una diferencia entre una solución técnicamente correcta y la experiencia utilizada
por plataformas líderes:

1. se analizan ambas alternativas;
2. se estudia el motivo por el que las plataformas líderes adoptaron su enfoque;
3. se identifican sus limitaciones;
4. se diseña una solución propia para Nexus;
5. se elige la opción que maximice claridad, consistencia, mantenibilidad y valor para el usuario.

**Nunca se copia literalmente una implementación externa.** Nexus aprende de las plataformas
maduras y mejora sus decisiones dentro de su propia arquitectura. Este es el principio rector de
todo el desarrollo de Nexus, por encima de cualquier atajo de conveniencia puntual.

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

El siguiente incremento planificado es **MX.0 — Nexus Experience System Foundation**, previo a
M3.2, según la sección "Nexus Experience System (NXS)" arriba.
