# AUDITORÍA — Object Storage / Amazon S3 (Fase 9)

Objetivo: inventariar el almacenamiento de ficheros actual y su migración futura a S3 preservando el
aislamiento por tenant. **No implementar nada ahora.**

## Estado actual (real)

Todo el almacenamiento de ficheros es **filesystem local** bajo `documentos/` (ruta relativa al repo),
resuelto con `os.path.join(os.path.dirname(__file__), "..", "..", "documentos")`.

| Contenido | Ubicación | Sensibilidad |
|---|---|---|
| PDFs (tickets, facturas, albaranes, nóminas, contratos, informes reposición, etiquetas, QR) | `documentos/<subcarpeta>/` | Privado (algunos con datos personales/fiscales) |
| Registro de documentos | tabla `documentos_registro` (ruta + metadatos) | Privado (referencia al fichero) |
| Clave de cifrado de correo | `documentos/.correo_key` | **SECRETO** (no debe ir a S3 estándar → Secrets Manager/KMS) |
| Cachés/JSON (traducción IA, citas, avisos) | `documentos/*.json` | Config/derivado |
| Backups/export tenant | `dr/backup_operacional.exportar_tenant` (filesystem) | Privado por tenant |

## Problema en Fargate

El filesystem de una tarea Fargate es **efímero**: al reciclar la tarea se pierden los ficheros. Por tanto,
**todo lo que hoy se escribe en `documentos/` debe pasar a S3** (o Secrets Manager para la clave).

## Diseño S3 (objetivo)

| Aspecto | Decisión |
|---|---|
| Privacidad | **Bucket privado** (Block Public Access ON); nunca objetos públicos |
| Aislamiento tenant | Clave por objeto `s3://<bucket>/<id_empresa>/<tipo>/<fichero>`; políticas IAM con condición de prefijo |
| Acceso a documentos | **URLs prefirmadas** (caducidad corta) generadas por la API tras verificar RBAC+tenant |
| CDN de documentos | CloudFront con **OAC** al bucket (no exponer el bucket); firma en el borde si aplica |
| Clave de correo (`.correo_key`) | **NO a S3**: a Secrets Manager + KMS |
| Cifrado en reposo | SSE-KMS (clave gestionada por KMS) |
| Versionado / lifecycle | Versioning ON + lifecycle (transición a IA/Glacier para históricos, expiración de temporales) |
| Exportaciones/backups | Prefijo `backups/<id_empresa>/...` con Object Lock opcional |

## Cambios de código (siguiente fase)

1. Introducir una **capa de almacenamiento** (`storage`) con dos backends: `filesystem` (dev) y `s3` (prod),
   detrás de una interfaz única — sin duplicar la lógica de generación de PDFs (ésta sigue igual, sólo cambia
   dónde se persiste/lee el binario).
2. `documentos_registro` guarda **clave S3** en vez de ruta local (compatibilidad hacia atrás: aceptar ambas).
3. Servir descargas con URL prefirmada + verificación RBAC/tenant.

**Veredicto: 🟡 REQUIERE ADAPTACIÓN (mayor alcance) / 🟣 bucket externo.** El aislamiento por tenant se
preserva por prefijo + IAM + URLs firmadas. Riesgo principal: exposición cross-tenant si se firma sin validar
tenant → mitigado por el guard existente.
