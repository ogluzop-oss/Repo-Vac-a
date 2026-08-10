# AUDITORÍA RPO / RTO — FASE 15

Fecha 2026-07-27. **BLOQUEADO: no medible sin incidente real sobre infraestructura AWS.**

## Software (verificado)

🟢 `dr/backup_operacional.estado` y `dr/dr_pitr` **instrumentan** RPO/RTO (edad del último backup, simulacros).
Base documentada en `CHECKLIST_DR_PRODUCCION.md`.

## Medición en AWS (Fase 15.12)

🟣 **BLOQUEADA / NO MEDIDO**. No hay incidente ni recuperación reales que medir. **No se usan valores teóricos
como si fueran medidos.** Sin registro real de: hora de fallo, detección, recuperación, datos perdidos,
servicios afectados.

## Resume

Tras el despliegue: ejecutar un simulacro controlado, medir RPO (datos perdidos) y RTO (tiempo de
recuperación) reales y compararlos con los objetivos SLA (a fijar con la frecuencia de snapshots RDS +
Multi-AZ). Estado: 🟢 instrumentación software / 🟣 medición real externa.
