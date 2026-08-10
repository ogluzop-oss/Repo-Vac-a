# Informe Técnico — Módulo 8: RRHH

**Auditoría (ya existía, paquete `src/rrhh`):** empleados, ausencias, control horario
(fichajes/jornadas/pausas), nómina (motor + servicio + parámetros de cotización), vacaciones,
contratos, documentos (contrato/finiquito/nómina/certificado/vacaciones con render y firma), portal
del empleado.

**Gaps implementados (migr 0108 + `src/services/rrhh/rrhh_pro.py`):**
- **Evaluación de desempeño**: `rrhh_evaluaciones` + `crear_evaluacion` · `cerrar_evaluacion`
  (puntuación media de competencias) · `evaluaciones`.
- **Formación/capacitación**: `rrhh_formacion(_asistentes)` + `crear_formacion` ·
  `inscribir_formacion` · `registrar_aprovechamiento` · `formaciones`.
- **Selección/candidatos (ATS ligero)**: `rrhh_seleccion_candidatos` + `registrar_candidato` ·
  `mover_fase_candidato` (RECIBIDO→CRIBADO→ENTREVISTA→OFERTA→CONTRATADO/DESCARTADO) · `candidatos`.
- **Planificación de turnos de personal**: `rrhh_turnos_plan` + `planificar_turno` · `cuadrante`.

**Reutilización:** vinculación por `id_empleado` a los empleados existentes; auditoría; multiempresa.
El servicio nuevo NO toca nómina, ausencias, fichajes ni contratos (que ya existían). La aprobación
de contrataciones puede enrutarse por el Workflow existente en fases futuras.

**Pruebas:** migr 0108; evaluación (media 80) + formación + aprovechamiento + ATS (fase ENTREVISTA) +
cuadrante de turnos. **smoke 5 passed.**

**Mejoras futuras:** integrar planificación de turnos con fichajes reales (desviación planificado vs
real); portal del empleado mostrando sus evaluaciones/formaciones; publicación de vacantes en la web
(reutilizar módulo venta online/comunicaciones); conversión candidato CONTRATADO→alta de empleado.
