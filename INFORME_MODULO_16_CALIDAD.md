# Informe Técnico — Módulo 16: Calidad

**Auditoría (ya existía, `services/calidad/*`):** planes de inspección por fase/criterios e
inspecciones (`inspecciones.py`), no conformidades (`no_conformidades.py`), CAPA correctivas/
preventivas con eficacia (`capa.py`), auditorías con hallazgos → NC (`auditorias.py`), trazabilidad
de lote/artículo (`trazabilidad.py`) y analítica (KPIs, detección de anomalías, tendencia de rechazo).

**Gaps implementados (migr 0116 + `src/services/calidad/calidad_pro.py`):**
- **Metrología / calibración** (`calidad_equipos_medida`, `calidad_calibraciones`): `alta_equipo`,
  `registrar_calibracion` (recalcula próxima según frecuencia; si NO conforme → **abre una NC
  reutilizando `no_conformidades.abrir`** y pone el equipo FUERA_SERVICIO), `equipos_a_calibrar` +
  job `calidad_calibraciones_alerta` (JobRegistry).
- **Certificados de análisis** (`calidad_certificados`): `emitir_certificado` (conforme automático
  comparando cada parámetro con sus límites min/max), `certificados_de_lote`.
- **SPC — capacidad de proceso** (`cp_cpk`): Cp/Cpk, media, σ y veredicto de capacidad (≥1,33) a
  partir de una serie de mediciones y los límites de especificación.

**Reutilización:** módulo NC existente para la no conformidad de calibración; Comunicaciones para la
alerta; Scheduler/JobRegistry; auditoría; multiempresa.

**Pruebas:** migr 0116; equipo + calibración (próxima 2027), certificado que detecta parámetro fuera
de límite (conforme=0), SPC Cp=Cpk=1,26. **smoke 5 passed.**

**Mejoras futuras:** cartas de control (X̄-R) con detección de tendencias; muestreo por AQL en los
planes de inspección; vinculación del certificado de análisis al centro documental y al envío al
cliente.
