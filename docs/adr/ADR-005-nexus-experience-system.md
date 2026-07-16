# ADR-005 — Nexus Experience System (NXS) como capa de UI compartida y obligatoria

## Estado

Aprobado (decisión metodológica; implementación de fundación — MX.0 — todavía no iniciada)

## Fecha

2026-07-16

## Contexto

Hasta M3.1, cada pantalla del admin (por ejemplo `/catalog/options`) se construyó con HTML/CSS
suelto por módulo, sin componentes compartidos. Ese patrón es exactamente el que llevó a
PrestaShop y Magento a tener un Back Office inconsistente que terminó forzando una reescritura
completa del admin en ambas plataformas.

## Problema

Cómo evitar que cada módulo de negocio futuro (Attributes, Collections, Content, Builder, etc.)
construya su propia interfaz de forma aislada, sin repetir el error histórico de PrestaShop y
Magento, sin frenar indefinidamente el roadmap comercial mientras se construye la base visual.

## Alternativas consideradas

- **Sin sistema de diseño, cada módulo construye su UI libremente**: es lo que ya generó
  inconsistencia visible en `/catalog/options` de M3.1 — descartado explícitamente.
- **Adoptar un Design System de terceros tal cual** (Shopify Polaris, VTEX IO): resolvería la
  consistencia rápido, pero acopla la identidad visual de Nexus a la de un competidor y viola la
  restricción explícita de no copiar componentes ni código de otras plataformas.
- **Especificar por adelantado un catálogo completo de ~40 componentes y 9 capas de producto
  antes de tener un segundo consumidor real**: riesgo de sobre-ingeniería — construir
  componentes sin un caso de uso real que valide su contrato, con alto riesgo de tener que
  rehacerlos de todas formas ante el primer uso real (ver discusión de la propuesta original en
  el historial de decisión de este ADR).
- **Sistema de diseño propio (NXS), con una fundación mínima obligatoria y el resto del catálogo
  creciendo por promoción desde consumidores reales** (opción elegida): consistencia garantizada
  desde el día uno para lo que todo módulo necesita siempre (shell, navegación, tokens,
  componentes base), sin comprometerse a construir especulativamente lo que ningún módulo ha
  necesitado todavía.

## Decisión

Nexus construye un sistema de diseño propio, NXS, no un módulo de negocio: fundamentos visuales
(Design Tokens), componentes reutilizables, patrones de interacción y accesibilidad, obligatorio
para toda interfaz administrativa futura. Su fundación (MX.0) se limita a tokens, shell
administrativo, navegación, temas y un núcleo mínimo de ~12 componentes, validada reconstruyendo
la pantalla real `/catalog/options`. El resto del catálogo (~40 componentes y patrones) crece por
regla de promoción: nace local en un módulo, se extrae a NXS cuando un segundo módulo real lo
necesita.

## Justificación

Fijar solo la fundación mínima ahora, y crecer el resto por promoción desde uso real, evita las
dos formas de fracaso conocidas: construir sin sistema de diseño (inconsistencia, como
PrestaShop/Magento) y construir un sistema de diseño completo sin validación real (componentes
que no encajan con el primer uso real y se rehacen de todas formas). Validar MX.0 reconstruyendo
una pantalla real existente, en vez de una pantalla de ejemplo, ancla la fundación a un caso de
uso verificable, no hipotético.

## Consecuencias

- Ningún módulo de negocio nuevo puede construir pantallas sin pasar primero por las "Reglas
  antes de crear una pantalla" de NXS (`CLAUDE.md`).
- El roadmap comercial (M3.2 en adelante) queda bloqueado hasta que MX.0 entregue al menos la
  fundación mínima — decisión explícita, no un efecto secundario no deseado.
- Cualquier componente local no promovido a NXS debe documentar explícitamente por qué no
  pertenece todavía al sistema compartido.
- Accesibilidad (WCAG AA) y preparación para internacionalización (sin implementarla) son
  no negociables desde el primer componente de MX.0, no una fase posterior.

## Riesgos

- MX.0 puede sufrir el mismo riesgo de alcance no acotado que ya se vio en la persecución de
  cobertura de M3.1 — mitigado por un criterio de aceptación único y verificable (reconstruir
  `/catalog/options`), no una lista abierta de entregables.
- La regla de promoción depende de que los módulos futuros documenten honestamente sus
  componentes locales candidatos; sin esa disciplina, NXS se estanca y el problema original
  (inconsistencia) reaparece de todas formas.

## Referencias

- `CLAUDE.md`, sección "Nexus Experience System (NXS)"
- `frontend/app/catalog/options/page.tsx` (pantalla piloto de validación de MX.0)

## ADRs relacionados

Ninguno todavía — es la primera decisión de la capa Nexus Experience System listada en
"Arquitectura de capas" de `CLAUDE.md`.

## Reemplaza o es reemplazado por

Ninguno.
