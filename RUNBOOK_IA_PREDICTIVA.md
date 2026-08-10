# RUNBOOK — IA PREDICTIVA

## Uso (API de servicio)
```python
from src.services.prediccion import servicio, forecasting

# Previsión de ventas de un tenant (serie diaria real; aislado por id_empresa):
r = servicio().forecast_ventas("EMP-001", horizonte=7)

# Previsión de una serie arbitraria (con fechas para habilitar Prophet):
r = forecasting.forecast(valores, fechas=fechas, horizonte=14, id_empresa="EMP-001", entidad="ventas")

print(r["modelo"], r["tipo"], r["es_ml"], r["confianza"])   # p.ej. prophet / ml / True / alta
print(r["explicacion"])
print(r["prediccion"], r["intervalo_inferior"], r["intervalo_superior"])
print(r["metricas"])   # {holdout, mae, rmse, wape}
```

## Interpretar el resultado
- `tipo`: **heuristica** (media móvil) · **estadistica** (tendencia lineal) · **ml** (Prophet). `es_ml`
  True SOLO con Prophet. **No etiquetar en la UI/SOMA como "IA" si `es_ml` es False.**
- `calidad_datos`: GOOD/WARNING/INSUFFICIENT/INVALID. Influye en la selección y en la confianza.
- `metricas`: backtesting temporal (MAE/RMSE/WAPE). `estado_modelo`=VALIDATED si hubo backtesting.
- `model_not_applicable`: motivo si Prophet no se pudo usar (p.ej. <60 observaciones).

## Selección de modelo (automática)
`<14 obs` → media móvil · `14–59` → tendencia lineal · `≥60 + Prophet + fechas` → Prophet. Sin datos
suficientes o inválidos → NUNCA Prophet.

## Tiempo real
Cada `forecast(..., emitir=True, id_empresa=…)` publica `prediccion.generada` en el Event Bus → llega por
SSE al canal `prediccion` (Fase 4). Un cliente `RealtimeClient(canales=["prediccion"])` la recibe sin polling.

## SOMA / IA empresarial
SOMA debe consultar `PredictionService.forecast_ventas` (o `forecasting.forecast`) y responder citando
**modelo, tipo, confianza y fecha**; nunca inventar cifras. Si `es_ml` es False, dejar claro que es
estimación heurística/estadística.

## Operación / rendimiento
- Prophet tarda ~1–3 s por ajuste (incluye un ajuste extra en el backtesting). Para dashboards, cachear el
  resultado por (tenant, entidad, día) y recalcular en un job (`scheduler`) fuera de la petición de UI.
- Prophet es **degradable**: si no está instalado o falla, el motor cae a estadística/heurística sin romper.

## Monitorización de modelo (drift)
El backtesting expone MAE/RMSE/WAPE por ejecución. Un WAPE creciente o calidad WARNING/INSUFFICIENT indica
degradación → conviene revisar datos / reentrenar. El reentrenamiento automático NO se activa por defecto
(debe ser controlado, auditable y validado antes de activar un modelo nuevo).

## Seguridad
Predicción por tenant (nunca cross-tenant); RBAC/auditoría existentes; nunca se registran secretos. Los
eventos y el SSE heredan la autenticación/aislamiento de las fases previas.
