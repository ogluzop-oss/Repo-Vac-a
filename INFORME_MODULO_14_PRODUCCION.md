# Informe Técnico — Módulo 14: Producción

**Auditoría (ya existía, `services/mrp/*`):** órdenes de fabricación con ciclo completo (crear →
planificar → liberar → iniciar → pausar → consumir materiales → registrar producción → finalizar →
costes, integradas al **kárdex real** vía tipos ENTRADA/SALIDA_PRODUCCION), centros de trabajo con
**capacidad/calendarios/turnos** (`capacidad_diaria`), y rutas con operaciones.

**Gaps implementados (migr 0114 + `src/services/mrp/produccion_pro.py`):**
- **Partes de trabajo / control de planta** (`partes_trabajo_prod`): `registrar_parte` (operación
  ejecutada por centro con cantidad, tiempo real, operario), `partes_de_orden`.
- **Avance de OF** (`avance_orden`): operaciones con parte vs total de la ruta (**reutiliza la ruta
  del artículo existente**), cantidad y tiempo acumulados.
- **CRP — carga vs capacidad** (`carga_centro`): horas de partes frente a la capacidad teórica del
  centro **reutilizando `centros.capacidad_diaria`/`capacidades_prod`**; marca sobrecarga.

**Reutilización:** ciclo de OF, centros/rutas/capacidad y kárdex intactos; auditoría; multiempresa.

**Pruebas:** migr 0114; 2 partes (210 min) en OF, avance por operación, CRP 3,5 h / capacidad →
ocupación 43,8 %. **smoke 5 passed.**

**Mejoras futuras:** captura de tiempos en tiempo real (inicio/fin por operación); eficiencia
OEE por centro; secuenciación finita de capacidad (APS).
