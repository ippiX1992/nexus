# ADR-007 — Fingerprint SHA-256 para combinaciones únicas de Variant

## Estado

Aprobado (implementado como RC local de M3.1, ver `docs/modules/03-1-catalog-options.md`)

## Fecha

2026-07-16

## Contexto

M3.1 introduce Options y Option Values (por ejemplo Color: Rojo/Negro, Talla: S/M) y necesita
garantizar que un Product nunca tenga dos Variants con exactamente la misma combinación de
valores — incluso bajo escritura concurrente.

## Problema

Cómo detectar y prevenir combinaciones de Option Values duplicadas para el mismo Product, de
forma que la garantía se sostenga bajo concurrencia real (dos requests creando la misma
combinación al mismo tiempo), no solo en el camino feliz de una sola escritura.

## Alternativas consideradas

- **Verificación solo a nivel de aplicación** (leer combinaciones existentes antes de insertar):
  vulnerable a condición de carrera — dos requests concurrentes pueden leer "no existe" al mismo
  tiempo y ambas insertar, duplicando la combinación.
- **Constraint único sobre las columnas de combinación directamente** (una fila por cada par
  Option/Value con un unique compuesto): no captura "el conjunto completo de pares es igual" de
  forma nativa en PostgreSQL sin normalizar primero esos pares a un valor comparable.
- **Fingerprint determinístico (hash) de la combinación completa + índice único parcial sobre esa
  columna** (opción elegida): normaliza el conjunto de pares Option/Value a un único valor
  comparable, y usa el motor de base de datos — no la aplicación — para rechazar duplicados bajo
  cualquier concurrencia.

## Decisión

Cada Variant con combinación de Options almacena un `combination_fingerprint`: SHA-256 sobre la
cadena canónica `<option_id>:<option_value_id>|...`, con los pares **ordenados por `option_id`**
para que el mismo conjunto de valores siempre produzca el mismo hash sin importar el orden de
envío. El valor es `NULL` para Variants sin combinación de Options (no un hash de cadena vacía).
Se protege con un índice único parcial sobre `(tenant_id, product_id, combination_fingerprint)
WHERE archived_at IS NULL AND combination_fingerprint IS NOT NULL`, y el fingerprint se calcula y
persiste dentro de la misma transacción que escribe la combinación — nunca de forma diferida.

## Justificación

Ordenar los pares antes de hashear garantiza que la comparación de combinaciones sea correcta
independientemente del orden en que el cliente envíe los Option Values. Usar un índice único
parcial de PostgreSQL, en vez de solo una verificación de aplicación, mueve la garantía de
unicidad al motor de base de datos — la misma decisión de fondo que [[ADR-002-row-level-security]]
aplica al aislamiento de tenant: no confiar en que el código de aplicación gane siempre la
carrera contra la concurrencia real.

## Consecuencias

- Cualquier cambio en la combinación de un Variant recalcula el fingerprint dentro de la misma
  transacción, nunca en un paso posterior o asíncrono.
- Dos requests HTTP concurrentes creando la misma combinación para el mismo Product resuelven a
  exactamente un ganador (`201`) y un perdedor (`409`), decidido por PostgreSQL, no por el orden
  de llegada al servidor de aplicación.
- Retirar una Product Option mientras existen Variants activas que la usan queda bloqueado — no
  hay forma de invalidar en silencio un fingerprint ya persistido y dejar una combinación
  "huérfana" sin decisión explícita.
- El índice único parcial excluye filas archivadas, permitiendo que una combinación archivada y
  una activa con los mismos valores coexistan sin conflicto — decisión intencional, no un
  descuido del `WHERE`.

## Riesgos

- Un cambio futuro en la forma de serializar los pares (por ejemplo, cambiar el separador o el
  orden) invalidaría todos los fingerprints ya calculados, requiriendo una migración de datos
  explícita — cualquier cambio a la función de fingerprint es, en la práctica, un cambio de
  contrato de datos, no solo de código.
- SHA-256 sobre un conjunto pequeño de pares (Options por Product tiene un límite de cuota
  explícito) no representa riesgo de colisión práctico, pero la función asume que ese límite se
  mantiene — un cambio futuro que permita combinaciones arbitrariamente grandes debería
  revisitarse.

## Referencias

- `docs/architecture/catalog-option-combinations.md`
- `alembic/versions/0004_catalog_options.py`
- `app/modules/catalog/domain/values.py` (`combination_fingerprint`)
- `docs/modules/03-1-catalog-options.md` sección 6 (verificación de concurrencia real)

## ADRs relacionados

Depende de [[ADR-006-catalog-ownership]] (las combinaciones viven dentro del Product tenant-owned)
y de [[ADR-002-row-level-security]] (mismo principio de garantía a nivel de motor de base de
datos, no de aplicación).

## Reemplaza o es reemplazado por

Ninguno.
