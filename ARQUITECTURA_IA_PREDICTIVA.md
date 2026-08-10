# ARQUITECTURA — IA PREDICTIVA (motor de forecasting unificado)

Motor único en `services/prediccion/forecasting.py`, integrado en `PredictionService.forecast_ventas` (no
paralelo). Reutiliza datos reales, Event Bus, SSE y aislamiento por tenant (N7).

## Pipeline

```
DATOS REALES (adaptadores.ventas_por_dia, por id_empresa)
      ▼
CALIDAD DE DATOS  (calidad_datos → GOOD/WARNING/INSUFFICIENT/INVALID)
      ▼
SELECCIÓN AUTOMÁTICA  (por nº obs + calidad + estacionalidad)
      │   <14 obs → media_móvil (heurística)
      │   14–59  → tendencia_lineal (estadística)
      │   ≥60 + Prophet disponible → Prophet (ML)
      ▼
BACKTESTING TEMPORAL  (train/test sin usar el futuro) → MAE · RMSE · WAPE
      ▼
FORECAST + INTERVALO DE CONFIANZA
      │   heurística/estadística: ±1.28σ (80%)
      │   Prophet: yhat_lower / yhat_upper
      ▼
EXPLICABILIDAD  (modelo, tipo, nº obs, calidad, estacionalidad, MAE, confianza)
      ▼
RESULTADO  {modelo, tipo(heuristica|estadistica|ml), es_ml, model_id, version, estado_modelo,
            n_observaciones, calidad_datos, prediccion[], intervalo_inf/sup[], metricas, confianza,
            explicacion, model_not_applicable}
      ▼
EVENT BUS  (publish "prediccion.generada", id_empresa, payload{modelo, tipo, model_id, …})
      ▼
REALTIME HUB → SSE → UI / SOMA / módulos  (Fase 4; canal "prediccion")
```

## Honestidad de origen (obligatoria)
`tipo` ∈ {`heuristica`, `estadistica`, `ml`}; `es_ml` True **solo** con Prophet. La explicación lo dice
literalmente ("Predicción basada en Prophet…" vs "Predicción heurística (media móvil)…"). Nunca se presenta
una heurística como IA/ML. Si Prophet no aplica (datos insuficientes) o falla → **fallback** a estadística/
heurística con `model_not_applicable` y motivo.

## Multi-tenant
Toda previsión se calcula sobre la serie de UN `id_empresa`; nunca mezcla tenants. Los eventos y el SSE
respetan el aislamiento existente. Modelos globales/segmentados = futuro (requieren agregación autorizada).

## Versionado de modelo (metadatos)
Cada resultado lleva `model_id` (hash tenant|entidad|algoritmo|timestamp), `version`, `estado_modelo`
(TRAINING/VALIDATED/ACTIVE/DEPRECATED/FAILED). Persistencia en tabla de registro de modelos = refinamiento
futuro (hoy se emite por Event Bus + auditable); no se crea tabla nueva (N7).

## Componentes
| Componente | Rol |
|---|---|
| `prediccion/forecasting.py` | motor unificado (nuevo) |
| `PredictionService.forecast_ventas` | punto de entrada integrado (motor.py) |
| `prediccion/heuristicas.motor_activo` | etiquetado de origen (reutilizado) |
| `ia/adaptadores`, `prediccion/adaptadores` | datos históricos reales (reutilizados) |
| `eventbus.publish` + `eventbus/realtime` | eventos + tiempo real (reutilizados) |
