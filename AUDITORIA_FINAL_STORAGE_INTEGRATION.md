# AUDITORÍA FINAL — STORAGE INTEGRATION (Fase 12)

Fecha 2026-07-27. Auditoría del repositorio tras el cierre de H1. Clasificación de todos los accesos a
filesystem: qué es persistencia empresarial (debe usar StorageProvider) vs. qué está permitido (temp/cache/
logs/assets/config/tests).

## 1. Persistencia empresarial → StorageProvider (🟢)

Los documentos empresariales persistentes convergen en el **chokepoint único** `db.documentos.
registrar_documento` (18 ficheros lo invocan). Todos, por tanto, pasan por el write-through a `StorageProvider`
y guardan `storage_key`. Lectura/descarga/borrado se realizan por la **capa segura** `services/storage/
documentos` (tenant + RBAC). El visor materializa desde StorageProvider cuando el fichero local no existe.

| Camino | Punto único | StorageProvider | Tenant guard | Estado |
|---|---|---|---|---|
| CREATE | `registrar_documento` → `persistir_fichero` | ✅ | ✅ | 🟢 |
| READ | `abrir_documento` | ✅ | ✅ + RBAC | 🟢 |
| DOWNLOAD | `url_descarga` (presigned) | ✅ | ✅ + RBAC + autorización | 🟢 |
| DELETE | `eliminar_documento` | ✅ | ✅ + RBAC | 🟢 |
| LEGACY | `migrar_registro_legacy` / on-read | ✅ | ✅ | 🟢 |
| VISOR | `centro_documental._ruta_existente` | ✅ (fallback) | ✅ (vía abrir_documento) | 🟢 |

## 2. Accesos a filesystem PERMITIDOS (no migran, por diseño)

| Tipo | Ejemplos | Justificación |
|---|---|---|
| Temporales | `logistics_pdf_service.py` (`os.remove(qr_doc_tmp)`), buffers de generación | fichero efímero de proceso |
| Caché | `documentos/ai_translate_cache.json`, citas/avisos JSON | derivado/recomputable |
| Assets | fuentes, logo, iconos SVG | estáticos de la app |
| Config | `.env`, ficheros de configuración | configuración |
| Preview/gráficas | `matplotlib.savefig`, barcode/QR PNG temporales | render efímero |
| Logs | stdout / ficheros de log | observabilidad |
| Tests/fixtures | `tests/` | pruebas |

## 3. Verificación (Objetivo 10)

- `grep os.remove/unlink` en negocio → única coincidencia relevante = **temporal QR** (permitido).
- `grep registrar_documento` → 18 ficheros, todos por el chokepoint con write-through.
- Tests de aislamiento y flujo: `test_aws_fase12.py` (8) + `test_aws_readiness_fase10.py` (14) +
  `test_aws_fase11.py` (9).

## 4. Caveat honesto

La **generación** aún produce un fichero temporal local antes del write-through (los 17 renderers no se
convirtieron a `BytesIO`, por la regla de no tocarlos). Es tolerante a filesystem efímero (durabilidad en S3).
No afecta a CREATE/READ/DOWNLOAD/DELETE (que ya pasan por StorageProvider).

## 5. Veredicto

Integración de storage **cerrada** en CREATE/READ/DOWNLOAD/DELETE/LEGACY/VISOR con aislamiento multi-tenant y
RBAC. 🟢 H1 cerrado (con el caveat menor de generación-a-temporal documentado).
