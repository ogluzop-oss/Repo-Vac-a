# AUDITORÍA — IA PREDICTIVA VISIBLE Y OPERATIVA (Fase 7)

Auditoría de cierre de la integración VISIBLE + conversacional del motor predictivo real en la experiencia
empresarial. Metodología: lectura del código real + tests runtime (sin mocks del flujo). Fecha 2026-06-30.

## 1. Alcance verificado

| Área | Verificación | Resultado |
|---|---|---|
| Tarjeta reutilizable | Instanciación offscreen, reutiliza `EnterpriseCard` | ✅ |
| Riesgo de rotura | Niveles BAJO/MEDIO/ALTO/INSUFICIENTE (función pura) | ✅ |
| Hook SOMA/Copilot | Delega en `consulta.responder`; None si no es predictiva | ✅ |
| Honestidad sin datos | Respuesta "No hay datos suficientes" | ✅ |
| Retraining controlado | Candidato entrenado + activación sólo si mejora | ✅ |
| Pantalla real (Reposición IA) | Instanciación offscreen con card cableada | ✅ |
| Regresión global | `629 passed, 1 skipped` | ✅ 0 regresiones |

## 2. Cumplimiento de reglas permanentes

- **N7 — un solo motor**: ✅ toda predicción pasa por `forecasting`. `riesgo_rotura`, `retraining`, `consulta`
  y la tarjeta lo consumen; no hay motor/tabla/RBAC/auditoría/Event-Bus/SSE paralelos.
- **Sin mocks**: ✅ el motor usa series reales (`adaptadores.ventas_por_dia`), backtesting real y Prophet real.
- **SOMA no calcula**: ✅ `_responder_prediccion` delega; no contiene matemática de predicción.
- **Honestidad de origen**: ✅ heurística/estadística/ML se distinguen extremo a extremo (`es_ml` sólo Prophet).
- **Multi-tenant**: ✅ `id_empresa` en todas las rutas; sin cruce entre empresas.
- **Aditivo/compatibilidad**: ✅ 0 tablas nuevas, 0 dependencias nuevas; el cableado en `informe_reposicion`
  es degradable (try/except, nunca rompe la pantalla).

## 3. Honestidad — lo que NO se declara operativo

- 🟡 Colocación de la tarjeta en Smart Stock / Compras / Ventas: el componente está listo y probado, pero su
  ubicación en esas 3 pantallas concretas no se ha cableado ni verificado → NO se declara 🟢.
- 🟡 Retraining automático por scheduler: `retrain` es invocable/registrable, pero NO auto-registrado (para no
  introducir reentrenos no supervisados) → estado MANUAL/PROGRAMABLE.
- 🟡 Refresco visual en vivo por SSE: el canal `prediccion` emite (Fase 4), pero el repintado en caliente de la
  tarjeta no está cableado.
- 🟣 Modelos globales multi-tenant y ML avanzado (xgboost/sklearn): bloqueo de diseño / dependencias externas;
  no se simula.

## 4. Evidencia de tests

`tests/unit/test_ia_ui.py` (6): `test_riesgo_rotura_niveles`, `test_copilot_hook_prediccion_sin_datos`,
`test_copilot_hook_no_predictivo_devuelve_none`, `test_retraining_controlado`,
`test_tarjeta_prevision_offscreen`, `test_reposicion_page_instancia_con_card_offscreen`.

## 5. Conclusión

La IA predictiva es **real, honesta y operativa** en su núcleo y en su primera superficie visible/conversacional.
Los elementos de despliegue visual amplio quedan documentados como 🟡 sin falsear su estado. Programa Fase 7
apto para cierre.
