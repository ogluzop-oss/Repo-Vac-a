# Informe Técnico — Módulo 9: Contratos

**Auditoría (ya existía):** contratos laborales (`rrhh_contratos`, con renovaciones/modificaciones/
anexos vía `src/rrhh/db/contratos.py`) y contratos de servicio con cliente + SLA
(`contratos_servicio`, gestionados por SAT `services/sat/contratos_sla.py`). No existía repositorio
general de contratos ni gestión transversal de obligaciones/cláusulas/vencimientos.

**Gaps implementados (migr 0109 + `src/services/contratos/contratos_pro.py`):**
- **Repositorio central** `contratos` (tipos proveedor/alquiler/seguro/licencia/servicio/otro):
  `crear_contrato`, `cambiar_estado`, `renovar_contrato` (cierra RENOVADO + crea VIGENTE nuevo),
  `listar_contratos`.
- **Obligaciones/hitos genéricos** (por `origen_tipo`+`origen_id`, válido para CUALQUIER contrato):
  `registrar_obligacion`, `cumplir_obligacion`, `obligaciones`.
- **Cláusulas** `contrato_clausulas`: `anadir_clausula`, `clausulas`.
- **Alertas de vencimiento/renovación**: `proximos_vencimientos` **unifica los 3 repositorios**
  (central + `contratos_servicio` + `rrhh_contratos`) + job `contratos_alertas_vencimiento`
  registrado en el JobRegistry/Scheduler (notifica a ADMINISTRADOR/GERENTE por comunicaciones).

**Reutilización:** referencia (no reescribe) `rrhh_contratos` y `contratos_servicio`; notificaciones;
scheduler; auditoría; multiempresa. Renovaciones con aprobación pueden enrutarse por Workflow.

**Pruebas:** migr 0109; contrato proveedor + cláusula + obligación (pago) + cumplir + vencimientos
unificados + renovación; job en `CATALOGO`. **smoke 5 passed.**

**Mejoras futuras:** vincular obligaciones de pago a vencimientos de tesorería; plantillas de contrato
(reusar el render de RRHH); firma digital de contratos no laborales (reusar `firma_servicio`).
