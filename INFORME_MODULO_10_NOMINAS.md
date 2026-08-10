# Informe Técnico — Módulo 10: Nóminas

**Auditoría (ya existía, `src/rrhh/nomina_motor.py` + `nomina_servicio.py` + `parametros_cotizacion.py`):**
motor de nómina enterprise con clasificación explícita de conceptos (DEVENGO_SALARIAL/NO_SALARIAL/
DEDUCCION), prorrateo de pagas extra, bases de cotización con topes por grupo, IRPF (tipo fijo + hook
para tablas), anticipos/embargos como entrada, **cotización del trabajador Y de la empresa**
(`ss_empresa`), y render PDF de nómina/finiquito/certificado.

**Gaps implementados (migr 0110 + `src/services/rrhh/nominas_pro.py`):**
- **Anticipos gestionados**: `rrhh_anticipos` + `solicitar_anticipo` (opcional Workflow) ·
  `aprobar_anticipo` · `cuota_anticipo_pendiente` · `amortizar_anticipos` (por cuotas, LIQUIDADO a 0)
  · `anticipos_empleado`. Antes `anticipos` era solo un número suelto en la entrada.
- **Conceptos recurrentes / retribución flexible por empleado**: `rrhh_conceptos_recurrentes` +
  `set_concepto_recurrente` · `conceptos_para_datos` · `preparar_datos_nomina` (fusiona conceptos +
  cuota de anticipo en los `datos` **sin recalcular** — el motor existente hace el cálculo).
- **Informe coste-empresa**: `coste_empresa` **agrega el `ss_empresa` que el motor YA calcula**
  (devengado + SS patronal + detalle), no reportado hasta ahora. No recalcula cotizaciones.

**Reutilización:** motor de nómina intacto (0 reescritura); `nomina_servicio.calcular_desde_datos`;
Workflow para aprobación de anticipos; auditoría; multiempresa.

**Pruebas:** migr 0110; anticipo 600€/3 cuotas → cuota 200, aprobación, amortización; concepto
recurrente inyectado en datos; coste-empresa ≥ devengado. **smoke 5 passed.**

**Mejoras futuras:** IRPF por tablas progresivas + regularización anual (el motor ya tiene el hook
`irpf_modo`); retribución en especie con valoración; informe agregado de coste-empresa por
centro/período reutilizando `bi_hechos_rrhh`.
