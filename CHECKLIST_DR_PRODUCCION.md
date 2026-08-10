# CHECKLIST — RECUPERACIÓN ANTE DESASTRES (DR)

Motor: `services/dr/backup_operacional` + `saas/backup_tenant` + `platform/cloud/failover`.

## Backups
- 🟢 Backup por tenant a JSON (`exportar_tenant`) — validado localmente (`test_saas_deployment`).
- 🟢 Restore por tenant (`restaurar_tenant`) y parcial por tablas (`restaurar_parcial`) — round-trip probado.
- 🟢 Simulacros (`backup_operacional.simulacro`: verify diario / consistency mensual / restore semanal).
- 🟣 Backups de BD completos + retención + cifrado en object storage. [EXTERNO]

## Objetivos (documentados; validación productiva [EXTERNO])
- **RPO** ≤ 24 h (backup programado diario; `planificar(intervalo_horas=…)`).
- **RTO**: restauración de tenant desde export — **medir en el primer simulacro en infra real**.
- ⚠ Un backup **no restaurado** NO se considera validado.

## Escenarios y respuesta
| Escenario | Respuesta |
|---|---|
| Pérdida de aplicación | redeploy imagen versionada → migrar (no destructivo) → readiness → tráfico |
| Pérdida de BD | promover réplica / restaurar último backup → verificar integridad → readiness |
| Pérdida de storage | restaurar documentos desde backup/object storage |
| Pérdida de región 🟣 | failover a región secundaria (`platform/cloud/failover`) → restore → readiness [EXTERNO] |
| Corrupción de datos | restore parcial por tablas (`restaurar_parcial`) del backup íntegro previo |

## Failover
- 🟣 `PRIMARY → SECONDARY` real requiere 2ª región/BD desplegadas. [EXTERNO] — modelado, no activado.
- 🟢 Procedimiento documentado paso a paso en `RUNBOOK_PRODUCCION.md §7`.
