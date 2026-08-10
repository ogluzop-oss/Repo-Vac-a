# ARQUITECTURA — IA PREDICTIVA EN LA UI (Fase 7)

## Capas (reutilización estricta, N7)

```
UI existente (Reposición IA, Smart Stock, Compras, Ventas)
        │  consume (no calcula)
        ▼
gui/prediccion_card.py ──────────────► gui/components/enterprise.EnterpriseCard   (librería única)
        │
        ▼
services/prediccion/consulta.py  (resumen_ui / responder)   ◄── SOMA/Copilot (motor._responder_prediccion)
        │
        ▼
services/prediccion/forecasting.py  (motor ÚNICO: calidad→selección→backtest→Prophet/heurística)
        │                                   │
        ├─ services/prediccion/modelos.py   ├─ services/prediccion/riesgo_rotura.py (demanda→riesgo)
        │  (ciclo de vida/versionado)       └─ services/prediccion/retraining.py (candidato→activar-si-mejora)
        ▼
Event Bus (prediccion.generada / modelo_activado) → SSE canal 'prediccion' (Fase 4)
```

## Principios

- **Un solo motor**: toda predicción pasa por `forecasting.forecast`. SOMA, la UI y el riesgo de rotura lo
  CONSUMEN; ninguno recalcula ni contiene reglas paralelas.
- **SOMA no calcula**: `CopilotService._responder_prediccion` → `consulta.responder` → `forecasting`. SOMA sólo
  formula lenguaje natural sobre el resultado explicable.
- **Honestidad de origen**: `tipo ∈ {heuristica, estadistica, ml}` y `es_ml` (sólo Prophet) viajan desde el
  motor hasta la etiqueta de la tarjeta y la respuesta conversacional.
- **Riesgo de rotura**: función pura `evaluar(stock, demanda_diaria, minimo, pendientes, lead_time)` +
  `riesgo_articulo` que toma la demanda del motor real y el stock de BD (tenant-aislado).
- **Retraining controlado**: detección de degradación (`modelos.evaluar_degradacion`) → entrena candidato
  (persistido VALIDATED) → `modelos.activar` (sólo si menor MAE) → auditoría/evento. Rollback recuperable.
- **Aislamiento multi-tenant**: `id_empresa` en todas las consultas; nunca se cruzan datos entre empresas.
- **Degradable**: la tarjeta y el hook nunca rompen la pantalla ni inventan cifras; si faltan datos, se
  ocultan o responden "no hay datos suficientes".

## Componentes nuevos (aditivos)

| Fichero | Responsabilidad |
|---|---|
| `src/services/prediccion/riesgo_rotura.py` | Riesgo de rotura (pura + por artículo) |
| `src/services/prediccion/retraining.py` | Retraining controlado + rollback |
| `src/gui/prediccion_card.py` | Tarjetas reutilizables (previsión / riesgo) |
| `src/gui/informe_reposicion.py` (cableado) | 1ª pantalla que muestra la tarjeta |
| `src/services/copilot/motor.py` (hook) | Enrutado conversacional a la IA predictiva |
