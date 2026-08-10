# RUNBOOK — IA PREDICTIVA EMPRESARIAL

## Previsión (con persistencia de modelo)
```python
from src.services.prediccion import servicio
r = servicio().forecast_ventas("EMP-001", horizonte=30)   # calcula, registra el modelo (VALIDATED) y emite evento
```

## Ciclo de vida de modelos
```python
from src.services.prediccion import modelos as M
M.listar("EMP-001", entidad="ventas")                 # historial de modelos del tenant
M.obtener_activo("EMP-001", "ventas")                 # modelo ACTIVE actual
res = M.activar(model_id, id_empresa="EMP-001", usuario=uid)   # activa SOLO si mejora (menor MAE) → audita+evento
# res = {ok, activado, comparacion:{mejor, criterio, mejora_pct}}
M.desactivar(model_id, id_empresa="EMP-001")          # → DEPRECATED
M.rechazar(model_id, id_empresa="EMP-001", motivo=...) # → FAILED
```

## Degradación / retraining
```python
d = M.evaluar_degradacion("EMP-001", "ventas", wape_reciente)
# d["estado"] ∈ MODEL_HEALTHY / MODEL_WARNING / MODEL_DEGRADED / MODEL_RETRAIN_REQUIRED
```
- DEGRADED/RETRAIN emiten `prediccion.modelo_degradado` / `prediccion.reentrenamiento_requerido` (Event Bus → SSE).
- **Retraining controlado:** recalcular con `forecast_ventas` (nuevo modelo VALIDATED) y `activar` solo si mejora.
  Programable con el scheduler existente. Nunca sustituye al activo sin validación+comparación.

## SOMA / Copiloto
```python
from src.services.prediccion import consulta
r = consulta.responder("¿cuánto venderemos el próximo mes?", "EMP-001")
# r["texto"] cita modelo/tipo/nº obs/calidad/confianza; si no hay datos → "No hay datos suficientes…"
```
SOMA debe usar SIEMPRE `consulta.responder`/`forecast_ventas` (nunca reglas paralelas ni cifras inventadas)
y distinguir heurística / estadística / ML.

## UI (tarjetas de previsión)
```python
from src.services.prediccion import consulta, forecasting
ui = consulta.resumen_ui(forecasting.predecir_ventas("EMP-001", horizonte=30, emitir=False))
# {titulo, horizonte_dias, total_previsto, modelo, tipo_modelo, es_ml, confianza, calidad_datos, explicacion, fecha_calculo}
```
Pintar en las pantallas EXISTENTES (Smart Stock, Reabastecimiento, Compras, Ventas). Actualización en vivo:
suscribirse al canal `prediccion` del SSE (Fase 4) → refrescar la tarjeta sin polling.

## Tiempo real
`prediccion.generada` / `modelo_activado` / `modelo_degradado` llegan por SSE (canal `prediccion`). Un
`RealtimeClient(canales=["prediccion"])` los recibe.

## Seguridad / RBAC
Permisos `prediccion.ver/entrenar/activar/gestionar`. Toda activación/rechazo/degradación se audita
(`PRED_MODELO_*`). Aislamiento estricto por tenant (activar de otro tenant se rechaza). Nunca secretos en logs.

## Rendimiento
Prophet ~1–3 s/ajuste → cachear la previsión por (tenant, entidad, día) y recalcular en job. Prophet degradable.
