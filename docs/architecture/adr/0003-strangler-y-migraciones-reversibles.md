# ADR-0003: Patrón Strangler + migraciones numeradas reversibles

- **Estado**: Aceptado
- **Fecha**: 2026-07-18

## Contexto

El sistema evoluciona de forma continua sobre una base grande y en producción. Reescribir módulos
completos es arriesgado y rompe compatibilidad.

## Decisión

- **Strangler Pattern**: se sustituye lo existente de forma **incremental**, creando infraestructura
  nueva y migrando gradualmente; se conservan `v_id`/rutas/firmas públicas por compatibilidad; lo
  sustituido se marca `@deprecated` un ciclo antes de eliminarse.
- **Migraciones numeradas y reversibles**: ficheros `NNNN_*.py` en `src/database/migraciones/`,
  registrados en `MODULOS`, con `VERSION/DESCRIPCION/REVERSIBLE/aplicar(cur)/revertir(cur)` e
  idempotentes (`CREATE TABLE IF NOT EXISTS`). Se aplican con el migrador; los cambios son aditivos.

## Consecuencias

- (+) Cero (o mínimas) regresiones; despliegues reversibles.
- (+) Compatibilidad hacia atrás garantizada durante la transición.
- (−) Convivencia temporal de lo viejo y lo nuevo; requiere limpieza posterior.

## Alternativas consideradas

- Big-bang rewrite: descartado por riesgo y rotura de contratos.
