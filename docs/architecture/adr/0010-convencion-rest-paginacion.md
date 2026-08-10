# ADR-0010: Convención REST de paginación/orden/filtrado (E1)

- **Estado**: Aceptado
- **Fecha**: 2026-07-18 (Etapa E · Fase E1)

## Contexto

Los endpoints de colección de `src/api/` devolvían listas sin una convención uniforme de paginación,
orden y filtrado, y solo aceptaban `limite` (legacy).

## Decisión

Se implanta una convención **uniforme, opcional y retrocompatible** (`src/api/paginacion.py`): parámetros
`limit`, `offset`, `cursor`, `page`, `page_size`, `sort`, `order`, `filters`. Si el cliente **no** los
usa, la respuesta es idéntica (lista simple); si los usa, se devuelve un sobre estándar
`{data, total, count, limit, offset, page, page_size, sort, order, next_cursor}`. El parámetro `limite`
(castellano) se conserva y **no** activa el sobre. Reutiliza `requiere_auth`/OpenAPI/JWT/API Keys/RBAC.

## Consecuencias

- (+) Paginación/orden/filtrado coherentes en toda la API; documentados en OpenAPI.
- (+) Cero rotura de contratos (opt-in).
- (−) El filtrado/orden se aplica sobre la página devuelta por el servicio (mejora futura: server-side).
