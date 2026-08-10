# RUNBOOK — IA PREDICTIVA EN LA UI (Fase 7)

## Operación diaria

- **Ver previsión en pantalla**: abrir **Reposición IA** → la tarjeta "PREVISIÓN DE DEMANDA" aparece bajo el
  título si el tenant tiene ≥ 7 observaciones de ventas. Si no hay datos, la tarjeta NO se muestra (esperado).
- **Preguntar a SOMA/Copilot**: "¿cuánto venderemos el próximo mes?", "previsión de demanda", "¿cuánto vamos a
  facturar?". Responde con el modelo real, su tipo (heurística/estadística/ML-Prophet), confianza y calidad. Si
  no hay histórico suficiente: "No hay datos suficientes para generar una predicción fiable."
- **Riesgo de rotura de un artículo**: `riesgo_rotura.riesgo_articulo(id_empresa, codigo, stock_minimo=, lead_time=)`.
  Devuelve nivel BAJO/MEDIO/ALTO o INSUFICIENTE + cobertura en días + recomendación.

## Ciclo de vida de modelos

- Cada previsión persistida registra un modelo VALIDATED (`prediccion_modelos`).
- Activar un candidato: `modelos.activar(model_id, id_empresa=)` — sólo si mejora (menor MAE); deprecia el
  anterior; audita `PRED_MODELO_ACTIVADO` y emite `prediccion.modelo_activado`.
- Detectar degradación: `modelos.evaluar_degradacion(id_empresa, "ventas", wape_reciente)` →
  MODEL_HEALTHY/WARNING/DEGRADED/RETRAIN_REQUIRED.

## Retraining controlado

```python
from src.services.prediccion import retraining
retraining.retrain(id_empresa, wape_reciente=<opcional>)   # entrena candidato y activa SÓLO si mejora
retraining.rollback(id_empresa, "ventas", model_id_anterior)  # reactiva un modelo previo válido
```

- **No auto-registrado** en el scheduler por defecto (evita reentrenos no supervisados). Para automatizar:
  registrar `retrain` como job opt-in en `scheduler_registry` con su frecuencia/RBAC/auditoría.
- Un `wape_reciente` "sano" (≤ 1.15× base) → no reentrena (`accion="ninguna"`).

## Diagnóstico

| Síntoma | Causa probable | Acción |
|---|---|---|
| No aparece la tarjeta | < 7 observaciones o motor no disponible | Verificar ventas del tenant; es comportamiento honesto |
| SOMA responde "no hay datos" | Histórico insuficiente/ inválido | Cargar más ventas; no es un fallo |
| Predicción marcada "heurística" | < 14 observaciones | Correcto; NO es ML. No forzar Prophet |
| Prophet no se usa con ≥ 60 obs | Prophet no instalado o fit falló | Fallback estadístico honesto; revisar log `prediccion.forecasting` |
| Candidato "no mejora" al reentrenar | MAE del candidato ≥ activo | Correcto; el activo se conserva |

## Seguridad / multi-tenant

- Todas las llamadas exigen `id_empresa`; los modelos y las series están aislados por tenant.
- RBAC: permisos `prediccion.ver/entrenar/activar/gestionar` (catálogo de seguridad).
- Auditoría: eventos `PRED_MODELO_*` en `log_auditoria`; nunca se registran datos de otro tenant.
