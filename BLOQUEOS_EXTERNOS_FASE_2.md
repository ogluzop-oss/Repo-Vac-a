# BLOQUEOS EXTERNOS — FASE 2 (provisionado real requerido)

Todo lo listado depende de recursos externos que NO existen en este entorno. **No se simulan.** El software
ya tiene los puntos de integración/adaptadores listos: al proveer estos recursos, el despliegue NO requiere
rediseño. Para cada uno: recurso · motivo · proveedor sugerido · pasos del propietario · qué necesitará
Claude Code después.

## 1. Proveedor cloud + cuenta
- **Motivo:** ejecutar la aplicación, la BD y el resto de servicios en producción.
- **Sugerido:** AWS / GCP / Azure / Hetzner / DigitalOcean.
- **Pasos del propietario:** crear cuenta/proyecto, presupuesto/alertas de coste, IAM con mínimos privilegios.
- **Después Claude Code necesitará:** IDs de proyecto/región y credenciales de despliegue (en secret store).

## 2. Base de datos productiva (MariaDB) + replicación
- **Motivo:** persistencia real con HA/backups; hoy solo hay instancia local/compose.
- **Sugerido:** MariaDB/MySQL gestionado (RDS/Cloud SQL/Azure DB) con réplica.
- **Pasos:** provisionar instancia, réplica en 2ª región, backups automáticos, usuario de app.
- **Después:** `DB_HOST/DB_USER/DB_PASSWORD/DB_NAME` (secret store) + endpoint de la réplica.

## 3. Object storage privado + CDN
- **Motivo:** documentos RRHH/PDFs/backups (privados) y assets públicos (CDN).
- **Sugerido:** S3/GCS/Azure Blob + CloudFront/Cloud CDN.
- **Pasos:** crear bucket privado, política de acceso, CDN para público.
- **Después:** `SM_OBJECT_STORAGE_URL` + credenciales de firma (URLs firmadas).

## 4. DNS + dominios
- **Motivo:** `app./api./admin.` públicos.
- **Sugerido:** registrador + DNS gestionado (Route53/Cloud DNS/Cloudflare).
- **Pasos:** registrar dominio, crear registros A/CNAME hacia el balanceador.
- **Después:** dominios finales + acceso a la zona DNS (o delegación al adaptador de Canal Web).

## 5. Certificados TLS
- **Motivo:** HTTPS y renovación automática.
- **Sugerido:** ACME/Let's Encrypt o el gestor del proveedor.
- **Pasos:** emisión por dominio/wildcard, renovación automática.
- **Después:** confirmación de emisión (o delegar al balanceador/proveedor).

## 6. Runner de CD (despliegue automatizado)
- **Motivo:** promover build → staging → producción con aprobación.
- **Sugerido:** GitHub Actions self-hosted / GitLab CI / runner del proveedor.
- **Pasos:** registrar runner con credenciales de despliegue, definir gates/approvals.
- **Después:** confirmación del runner + secretos de despliegue en el store del CI.

## 7. Credenciales OAuth de terceros (conectores)
- **Motivo:** conexiones reales (Gmail/M365/Stripe/PayPal/marketplaces) — hoy AUTH_REQUIRED.
- **Pasos:** crear apps OAuth en cada proveedor, obtener client_id/secret, configurar redirect URIs.
- **Después:** client_id/secret por proveedor (secret store); NUNCA en Git.

## 8. Validación real de RPO/RTO y failover
- **Motivo:** medir tiempos reales de restore/failover en infra productiva.
- **Pasos:** ejecutar `simulacro` sobre la BD/región reales; cronometrar RTO; verificar RPO.
- **Después:** métricas reales para actualizar la certificación (pasar 🟡→🟢).

---

**Regla de detención (Fase 20):** ante cualquiera de estos, Claude Code NO improvisa, NO simula, NO marca
operativo. Este documento es el hand-off para el propietario.
