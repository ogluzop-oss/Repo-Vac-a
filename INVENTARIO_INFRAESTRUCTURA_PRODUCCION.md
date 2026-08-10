# INVENTARIO DE INFRAESTRUCTURA DE PRODUCCIÓN

Auditoría del entorno REAL disponible (Fase 0, 2026-07-27). Evidencia recogida en modo lectura sobre la
máquina actual. **Conclusión: NO existe infraestructura de producción en este entorno** (es una estación de
desarrollo Windows con MariaDB local). Nada se simula.

**Leyenda:** 🟢 operativo y validado en prod · 🟡 pendiente de validación real · 🔵 preparado (software) ·
🟣 bloqueado por recurso externo (no presente) · 🔴 no implementado.

| Componente | Estado | Evidencia | Acción |
|---|---|---|---|
| Cuenta / proveedor cloud | 🟣 | `aws/gcloud/az/terraform/helm/doctl/flyctl` = NO instalados | Provisionar (BLOQUEOS §1) |
| Región primaria | 🟣 | sin proveedor cloud | Definir al provisionar |
| Región secundaria | 🟣 | sin proveedor cloud | Requiere 2ª región real |
| IAM / VPC / red / firewall | 🟣 | sin cuenta cloud | Provisionar |
| Balanceador de carga | 🟣 | sin cloud | Provisionar (TLS termination) |
| Contenedores (runtime) | 🟣 | **Docker daemon NO corriendo** | Arrancar/host de contenedores |
| Registro de imágenes | 🟣 | sin registry configurado | Provisionar |
| MariaDB **productiva** | 🟣 | actual = `127.0.0.1:3306` (dev local) | BD gestionada real |
| Réplica BD / 2ª región | 🟣 | sin réplica | Provisionar |
| Object Storage (privado) | 🟣 | `SM_OBJECT_STORAGE_URL` vacío | Bucket privado |
| CDN | 🟣 | sin CDN | Provisionar |
| DNS / dominios | 🟣 | sin dominio configurado (`app./api./admin.`) | Registrar + DNS |
| TLS / HTTPS | 🟣 | sin certificados | ACME/proveedor |
| CI (tests/build) | 🔵 | `.github/workflows/{ci,tests,multiplataforma}.yml` presentes | Reutilizable |
| CD a producción | 🟣 | sin runner de despliegue | Runner + approvals |
| Staging | 🟣 | sin host de staging | Provisionar |
| Producción | 🟣 | sin host de producción | Provisionar |
| Secret Manager / Vault | 🔵 | `seguridad/secret_manager` (fernet; backend vault preparado) | KMS/Vault real [EXTERNO] |
| Credenciales OAuth reales | 🟣 | `GOOGLE_OAUTH_*` vacíos; sin Stripe/PayPal/M365 | Apps OAuth de terceros |
| Backups | 🟡 | `dr/backup_operacional` + `saas/backup_tenant` (validado LOCAL) | Validar en infra real |
| RPO | 🟡 | ≤24h documentado (teórico) | Medir en prod |
| RTO | 🟡 | por medir | Cronometrar en simulacro real |
| Failover multi-región | 🟣 | `platform/cloud/failover` modelado (en memoria) | 2ª región real |
| Observabilidad | 🔵 | `observabilidad/{health,metricas,alertas,tracing}` | Backend de métricas externo opcional |
| SaaS licensing / enforcement | 🟢(software) | cableado y verificado por tests | operativo en el software |
| API pública OAuth2 | 🟢(software) | `test_capacidades_avanzadas` | operativo en el software |
| Aislamiento multi-tenant | 🟢(software) | `test_cloud_infra` (418 tablas) | operativo en el software |
| Tiempo real en red (WS/SSE push) | 🔵 | Event Bus in-app real; sin transporte de red | [EXTERNO] |

## Veredicto
El **software** está production-ready (auditado, certificado, 607 tests en verde). **La infraestructura de
producción NO existe en este entorno**: sin cuenta cloud, sin Docker en ejecución, con BD local de
desarrollo, sin storage/DNS/TLS/CD/2ª-región/credenciales-OAuth. Por tanto **NO puede desplegarse aquí** y
**no se simula**. Detalle y hand-off en `BLOQUEOS_EXTERNOS_FASE_3.md`.
