# Informe Técnico — Módulo 6: Logística

**Auditoría (ya existía):** incidencias logísticas (`incidencias_logisticas`), recepciones
(`recepciones_logisticas`), documentos/albaranes (`documentos_logisticos(_lineas/_pales)`), estado de
envío en pedidos online.

**Gaps implementados (migr 0106 + `src/services/logistica/logistica_pro.py`):**
- **transportistas**: `logistica_transportistas` + `crear_transportista` · `transportistas`.
- **expediciones + entregas parciales/programadas**: `logistica_expediciones` + `crear_expedicion`
  (parcial, fecha_programada).
- **seguimiento/tracking**: `actualizar_seguimiento` (estado PREPARACION→ENVIADA→EN_TRANSITO→ENTREGADA,
  tracking, tiempos de envío/entrega).
- **incidencias de expedición**: `registrar_incidencia_expedicion` (reutiliza `incidencias_logisticas`).
- **costes logísticos**: campo `coste` + `coste_logistico(desde,hasta)`.

**Reutilización:** pedidos/picking (M5) como origen; `incidencias_logisticas` existente; auditoría;
multiempresa. Rutas de reparto pueden reutilizar el optimizador de rutas del M1.

**Pruebas:** migr 0106; transportista + expedición (parcial/programada) + seguimiento/tracking +
incidencia + coste total. **smoke 5 passed.**

**Mejoras futuras:** integración con APIs de transportistas (tracking real vía conectores del Bloque 2);
planificación de rutas de reparto multi-parada; costes por peso/volumen.
