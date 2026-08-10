# RUNBOOK — IA PREDICTIVA TRANSVERSAL (Fase 8)

## Dónde ve el usuario la IA

- **Smart Stock**: tarjetas de previsión de demanda + riesgo de rotura (si hay ≥ 7 obs; si no, no se pintan).
- **Hub BI → pestaña Predicción**: KPIs del motor real (riesgo alto/medio, demanda 7d + tendencia + calidad,
  modelos activos + MAE/WAPE) además de las predicciones por dominio existentes.
- **SOMA/Copilot**: preguntas conversacionales (ver abajo).
- **Reposición IA** (Fase 7): tarjeta de previsión.

## Preguntas que responde SOMA (datos reales)

| Pregunta | Intent | Fuente |
|---|---|---|
| "¿Qué productos tienen mayor riesgo de rotura?" / "¿qué revisar para reponer?" | riesgo | `articulos_bajo_umbral` |
| "¿Qué artículos tienen demanda creciente?" / "tendencia de ventas" | tendencia | `forecasting` + rotación |
| "¿Qué modelo se está utilizando?" / "modelos que necesitan reentrenamiento" | modelos | `modelos.listar` |
| "¿Cuánto venderemos el próximo mes?" | previsión | `forecasting.predecir_ventas` |

Sin histórico suficiente → "No hay datos suficientes para responder con fiabilidad." Nunca inventa.

## Servicios (uso programático)

```python
from src.services.prediccion import panel, recomendaciones, consulta
panel.kpis_predictivos(id_empresa)                       # KPIs del dashboard
recomendaciones.recomendaciones_reposicion(id_empresa)   # lista para Compras/Informes (asiste, no pide)
consulta.responder("previsión de ventas", id_empresa)    # enrutador conversacional
```

## Tiempo real (SSE → UI)

```python
from src.gui.realtime_qt import RealtimePrediccionBridge
puente = RealtimePrediccionBridge(base_url, token_provider)   # base_url del API; token JWT vigente
puente.prediccion_generada.connect(pantalla.recargar)
puente.modelo_degradado.connect(pantalla.avisar)
puente.reentrenamiento_requerido.connect(pantalla.avisar_retrain)
puente.iniciar()   # requiere el API REST con /realtime/stream accesible
```

- Requiere el **servidor REST corriendo** (endpoint `/api/v1/realtime/stream`). Sin servidor, el puente
  reintenta con backoff y no emite (comportamiento honesto, no simula eventos).

## Retraining (controlado)

Igual que Fase 7: `retraining.retrain(id_empresa, wape_reciente=)` — entrena candidato, activa sólo si mejora;
`retraining.rollback(...)`. **No auto-registrado** en scheduler (manual/programable).

## Diagnóstico

| Síntoma | Causa | Acción |
|---|---|---|
| No hay tarjeta en Smart Stock | < 7 obs de ventas | Comportamiento honesto; cargar histórico |
| KPIs "sin datos"/"sin_datos" | Tenant sin histórico | Correcto |
| SOMA "no hay datos suficientes" | Histórico insuficiente | Correcto |
| Puente Qt no refresca | API REST no accesible | Levantar el API; revisar token/tenant |
| "Modelos degradados" no aparece como contador | No hay estado persistente | Evaluar con `modelos.evaluar_degradacion` |
