# AUDITORÍA — CONTINUIDAD DE NEGOCIO (Backup/Restauración) (Fase 14)

Fecha 2026-07-27. Read-only. Estrategia de backup/restauración y RPO/RTO.

## Software existente (verificado)

| Capacidad | Módulo | Estado |
|---|---|---|
| Backup por tenant | `saas/backup_tenant.exportar_empresa` | 🟢 (round-trip probado) |
| Restauración por tenant | `saas/backup_tenant.restaurar_empresa` / `restaurar_parcial` | 🟢 |
| Backup operacional + estado | `dr/backup_operacional` (`exportar_tenant`, `verificar`, `estado`) | 🟢 |
| PITR (point-in-time) | `dr/dr_pitr` | 🔵 (RDS PITR real 🟣) |
| Replicación | `dr/dr_replicacion` | 🔵 |
| Storage off-site | `dr/dr_storage` | 🔵 (S3 real 🟣) |
| Simulacros (drills) | `dr/dr_drills` | 🔵 (simulacro real sobre AWS 🟣) |
| Dashboard DR | `dr/dr_dashboard` | 🟢 (UI) |

## Mapeo a AWS

| Necesidad | Servicio AWS | Estado |
|---|---|---|
| Backups automáticos BD | RDS automated backups | 🟣 externo |
| Snapshots BD | RDS snapshots | 🟣 externo |
| Backup de documentos | S3 versioning + lifecycle | 🟣 externo |
| Recuperación accidental | S3 versioning / RDS PITR | 🟣 externo |
| Cifrado en reposo | KMS (RDS + S3 SSE-KMS) | 🟣 externo |
| Retención | políticas RDS/S3 lifecycle | 🟣 externo |

## RPO / RTO

- `dr/backup_operacional.estado` y `dr_pitr` **calculan/exponen RPO/RTO** a partir de la edad del último backup
  y los simulacros. Documentados también en `CHECKLIST_DR_PRODUCCION.md`.
- **Valores objetivo definitivos** (RPO/RTO SLA de producción) → dependen de la configuración RDS/S3 real
  (frecuencia de snapshots, Multi-AZ) → 🟡 a fijar en el provisionado.

## Veredicto

🟢 **Software de backup/restauración presente y probado a nivel tenant**; DR operativo mapeado a servicios AWS
(RDS/S3) 🟣 externos. RPO/RTO instrumentados; valores SLA finales 🟡 a fijar con la infra. **No bloqueante de
software.**
