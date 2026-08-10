# Pruebas de carga — Etapa F · Fase F7

Pruebas de carga **in-process** de los subsistemas Enterprise. No modifican lógica: invocan operaciones
existentes (mayormente de lectura, con N acotado) y miden latencia (p50/p95/p99) y throughput (ops/s).

## Metodología

- Harness: [`tests/load/harness.py`](../tests/load/harness.py) · Runner: [`tests/load/run_load.py`](../tests/load/run_load.py).
- Ejecución: `QT_QPA_PLATFORM=offscreen DB_NAME=smart_manager_test python tests/load/run_load.py 300`.
- Warmup de 10 llamadas por subsistema; N = 300 iteraciones medidas; latencias en milisegundos.
- Entorno: proceso único, MariaDB local (base `smart_manager_test`), sin red externa. Las cifras son
  **relativas** (comparativa entre subsistemas y detección de regresiones), no un benchmark de producción.

## Resultados (N = 300)

| Subsistema | N | ops/s | p50 (ms) | p95 (ms) | p99 (ms) | errores |
|------------|---|-------|----------|----------|----------|---------|
| API (`/system/version`) | 300 | 2569.2 | 0.322 | 0.647 | 0.849 | 0 |
| Marketplace (`catalogo`) | 300 | 267.7 | 2.535 | 6.500 | 18.689 | 0 |
| SDK (`communications.list`, transporte inyectado) | 300 | 191546.4 | 0.005 | 0.005 | 0.005 | 0 |
| Scheduler (`listar_schedules`) | 300 | 1023.3 | 0.911 | 1.468 | 1.869 | 0 |
| Event Bus (`suscripciones`) | 300 | 1205303.7 | 0.000 | 0.001 | 0.001 | 0 |
| Comercio Digital (`descriptor`) | 300 | 21826.3 | 0.041 | 0.062 | 0.170 | 0 |
| BI / Observabilidad (`operacional.snapshot`) | 300 | 123.5 | 7.821 | 10.304 | 12.209 | 0 |
| IA (`recomendaciones.generar`) | 300 | 69.0 | 13.463 | 20.831 | 24.979 | 0 |

## Lectura de resultados

- **0 errores** en 2 400 operaciones (300 × 8). Todos los subsistemas responden de forma estable bajo
  carga repetida.
- **Muy rápidos** (memoria/descriptor): Event Bus (dispatch en memoria), SDK (transporte inyectado, sin
  red), Comercio Digital (descriptor), API (endpoint público sin BD).
- **Dependientes de BD** (esperado, más lentos): IA (`recomendaciones`, ~69 ops/s) y BI/Observabilidad
  (`snapshot`, ~123 ops/s) — combinan varias consultas por llamada. Marketplace (~268 ops/s) consulta el
  catálogo.
- Ningún subsistema muestra colas de errores ni degradación al repetir; las latencias p95/p99 se mantienen
  próximas a la p50 (sin colas largas), salvo el p99 de Marketplace (18.7 ms) por variación de la BD.

## Notas de alcance

- Las operaciones de **escritura de alto volumen** (p. ej. `eventbus.publish`, creación de schedules o
  transacciones) no se incluyen para no contaminar datos; se miden operaciones representativas de lectura
  y de dispatch. La cadena de escritura ya está cubierta funcionalmente por la suite de pruebas.
- La medición es **in-process** (sin balanceador ni red). Para carga distribuida real se usaría la
  imagen Docker + Kubernetes/HPA (Etapa E · Fase E4) con una herramienta externa (k6/Locust) contra
  `/api/v1`. Documentado como mejora, no implementado en esta fase.

## Reejecución / regresión

Reejecutar tras cambios y comparar ops/s y p95 para detectar regresiones de rendimiento:

```bash
QT_QPA_PLATFORM=offscreen DB_NAME=smart_manager_test python tests/load/run_load.py 300
```
