# INFORME DE REGRESIÓN FINAL — Auditoría Maestra 8 Fases

Fecha 2026-07-27. Entorno: `QT_QPA_PLATFORM=offscreen`, `DB_NAME=smart_manager_test`, migraciones aplicadas
automáticamente por el fixture `db`.

## Resultados

| Suite | Resultado | Notas |
|---|---|---|
| `tests/unit` (scope histórico de las certificaciones) | **638 passed, 1 skipped, 0 failed** | Coincide con la progresión 607→610→617→624→629→638 |
| `tests/unit` + `tests/integration` | **1426 passed, 31 failed, 1 skipped** | Las 31 fallas son PRE-EXISTENTES y fuera del alcance de las 8 fases (ver abajo) |
| Scope IA/infra de las 8 fases (37 tests dirigidos) | **37 passed** | `test_forecasting`, `test_prediccion_modelos`, `test_ia_ui`, `test_ia_fase8`, `test_realtime`, `test_cloud_infra`, `test_capacidades_avanzadas` |

## Evolución del nº de tests unitarios (explicada)

| Hito | Unit passed | Δ | Motivo |
|---|---|---|---|
| Fase cloud infra | 603 | — | `test_cloud_infra` |
| Deployment SaaS | 607 | +4 | `test_saas_deployment` |
| Tiempo real SSE | 610 | +3 | `test_realtime` |
| IA predictiva | 617 | +7 | `test_forecasting` |
| IA empresarial/modelos | 624 | +7 | `test_prediccion_modelos` |
| IA UI (Fase 7) | 629 | +5 | `test_ia_ui` (5) |
| + test pantalla reposición | +1 → 630 base | +1 | instanciación offscreen |
| IA transversal (Fase 8) | 638 | +8 | `test_ia_fase8` |

**0 regresiones** introducidas por las 8 fases en el scope unit.

## Las 31 fallas de integración — análisis honesto (NO son regresiones de esta auditoría)

- **Dominios**: `test_rrhh_pdf_decomp` (×10, golden-PDF hash), `test_ventas_vta`, `test_tesoreria_gui`,
  `test_tesoreria_endurecimiento`, `test_rrhh_control_horario`, `test_prod_h1_h7` (backup), y otros de
  RRHH/tesorería/ventas.
- **Causa raíz observada**: (a) hashes golden de PDFs RRHH desactualizados tras cambios en
  `assets/estilo_global.py` y `src/rrhh/documents/render/*`; (b) expectativa de IVA (`121.0` vs `100.0`) por
  cambios en `src/utils/fiscalidad.py`/`divisas.py`.
- **Prueba de que NO las causó esta auditoría**: todos esos ficheros fuente aparecen como **`M` (modificados)
  en el árbol de trabajo ANTES de esta sesión** (trabajo previo sin commitear). Las 8 fases auditadas sólo
  añadieron/​tocaron `src/services/prediccion/*`, `src/services/copilot/motor.py`, `src/gui/realtime_qt.py`,
  `src/gui/prediccion_card.py`, `src/gui/mostrar_stock.py`, `src/gui/informe_reposicion.py`,
  `src/gui/paneles/panel_prediccion.py` — **ninguno** en los dominios que fallan.
- **Verificación cruzada**: los 37 tests del scope IA/infra pasan; el scope unit (638) no tiene fallas.

## Conclusión

- **Dentro del alcance de las 8 fases: 0 regresiones.** ✅
- **Fuera de alcance: 31 fallas pre-existentes** (RRHH/tesorería/ventas/fiscalidad) heredadas del árbol de
  trabajo, a resolver por el propietario en un ciclo normal de producto (regenerar golden PDFs, revisar la
  expectativa de IVA). NO se corrigen aquí para no exceder el alcance ni tocar módulos estables no relacionados.
