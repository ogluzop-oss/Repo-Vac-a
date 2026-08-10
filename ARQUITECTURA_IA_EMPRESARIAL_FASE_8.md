# ARQUITECTURA — IA PREDICTIVA TRANSVERSAL (Fase 8)

## Un solo motor, muchos consumidores (N7)

```
        Smart Stock ─┐     Compras/Informes ─┐    Hub BI (PanelPrediccion) ─┐    SOMA/Copilot
                     │                        │                              │        │
              prediccion_card          recomendaciones.py               panel.py   consulta.responder
                     │                        │                              │        │ (enrutador)
                     └──────────────┬─────────┴──────────────┬───────────────┘        │
                                    ▼                         ▼                        ▼
                          services/prediccion/forecasting.py  (MOTOR ÚNICO real)
                                    │            │            │
                    modelos.py (ciclo vida)  riesgo_rotura.py  adaptadores/stock.py
                                    │
                    Event Bus → canal 'prediccion' → SSE (Fase 4) → gui/realtime_qt (señales Qt) → pantallas
```

## Componentes por punto del prompt

| Punto | Componente | Reutiliza |
|---|---|---|
| 1 Smart Stock | `mostrar_stock._StockTiendaPage._cargar_ia_predictiva` | `prediccion_card`, `consulta`, `riesgo_rotura` |
| 2/4 Compras/Informes | `services/prediccion/recomendaciones.py` | `adaptadores.articulos_bajo_umbral`, `forecasting` |
| 3 Ventas | (previsión/tendencia vía `consulta`/`panel`; tarjeta reutilizable disponible) | `prediccion_card`, `consulta` |
| 5 Tiempo real | `gui/realtime_qt.RealtimePrediccionBridge` | `eventbus.realtime_client.RealtimeClient` |
| 6 Retraining | `retraining.py` (Fase 7) | `modelos`, `forecasting` |
| 7 Dashboard | `services/prediccion/panel.py` + `PanelPrediccion.grid_ia` | `stock`, `modelos`, `forecasting` |
| 8 SOMA | `consulta.responder` (enrutador) + `motor._responder_prediccion` | `forecasting`, `stock`, `modelos` |
| 9 RBAC | permisos `prediccion.*` existentes | `services.autorizacion`, `seguridad.catalogo` |
| 10 Multi-tenant | `id_empresa` en todo el flujo | `db.empresa`, adaptadores |

## Principios

- **SOMA no calcula**: el copiloto → `consulta.responder` → servicios reales. Enrutador de intents único.
- **La UI no recalcula**: consume `consulta.resumen_ui`, `panel.kpis_predictivos`, `recomendaciones`.
- **Tiempo real sin polling**: el puente Qt sólo re-emite lo que el transporte SSE entrega (nunca inventa).
- **Asistencia, no automatización**: `recomendaciones` no crea pedidos; el retraining sólo activa si mejora.
- **Honestidad de origen y de datos**: tipo de IA y calidad de datos viajan hasta la etiqueta final.

## Mapa RBAC (sin sistema paralelo)

Los permisos existentes cubren las responsabilidades del prompt: `prediccion.ver` = consultar/ver KPIs;
`prediccion.entrenar` = generar/reentrenar; `prediccion.activar` = activar modelo; `prediccion.gestionar` =
administración (rollback/config). **No se crean 5 permisos nuevos** para no duplicar el catálogo.
