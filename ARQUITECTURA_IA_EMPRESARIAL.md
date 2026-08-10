# ARQUITECTURA — IA PREDICTIVA EMPRESARIAL (UI + SOMA + ciclo de vida)

Extiende el motor de la Fase 5 con persistencia/ciclo de vida de modelos e integración con SOMA y UI.
Reutiliza Event Bus, SSE, tenant, RBAC y auditoría (N7). Única tabla nueva: `prediccion_modelos` (migr 0163).

## Flujo

```
forecast_ventas(id_empresa)  ──►  forecasting (calidad→selección→backtest→Prophet/estadística/heurística)
        │                                     │ persistir=True
        │                                     ▼
        │                        modelos.registrar()  ──►  tabla prediccion_modelos (VALIDATED, métricas, hash)
        │                                     │
        │                                     ▼
        │                        CICLO DE VIDA (modelos.py):
        │                          activar(model_id) → comparar(MAE) vs ACTIVE → activa si mejora → depreca anterior
        │                          rechazar / desactivar / evaluar_degradacion(WAPE) → eventos + auditoría
        ▼
Event Bus  (prediccion.generada / modelo_activado / modelo_degradado / reentrenamiento_requerido)
        ▼
Realtime Hub → SSE (canal 'prediccion')  ──►  UI (tarjetas) / SOMA
        ▲
SOMA (consulta.responder)  ──►  forecasting real  ──►  respuesta EXPLICABLE (modelo/tipo/confianza/calidad)
UI  (consulta.resumen_ui)  ──►  contrato compacto para pintar la previsión en las pantallas existentes
```

## Ciclo de vida del modelo
`TRAINING → VALIDATED → ACTIVE → DEPRECATED` (o `FAILED`). Reglas:
- Se persiste como VALIDATED tras el backtesting (métricas reales).
- `activar` exige VALIDATED y **solo activa si mejora** (menor MAE) o no hay activo; deprecia el anterior;
  audita (`PRED_MODELO_ACTIVADO`) y emite `prediccion.modelo_activado`. **Nunca activa por defecto ni un
  modelo no validado.**
- `evaluar_degradacion` compara el WAPE reciente con el del modelo activo → HEALTHY/WARNING/DEGRADED/
  RETRAIN_REQUIRED; emite `prediccion.modelo_degradado` y, si procede, `prediccion.reentrenamiento_requerido`.

## Multi-tenant / seguridad
Todo por `id_empresa` (el `activar`/`rechazar`/`desactivar` rechazan modelos de otro tenant). Permisos RBAC
`prediccion.ver/entrenar/activar/gestionar`. Auditoría en cada acción sensible. Nunca secretos.

## Honestidad
`tipo_modelo` ∈ {heuristica, estadistica, ml}; SOMA y UI etiquetan el origen SIN llamar IA a una heurística.

## Componentes
| Componente | Rol |
|---|---|
| `prediccion/modelos.py` | ciclo de vida/versionado/comparación/degradación (nuevo) |
| migr `0163_prediccion_modelos` | tabla de registro (nueva, justificada) |
| `prediccion/consulta.py` | integración SOMA (respuesta explicable) + `resumen_ui` (contrato UI) (nuevo) |
| `prediccion/forecasting.py` | motor (Fase 5) + `persistir=True` → registra modelo |
| Event Bus / SSE / RBAC / auditoría | reutilizados |
