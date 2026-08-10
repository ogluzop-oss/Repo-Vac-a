# Informe Técnico — Módulo 19: Documentación

**Auditoría (ya existía):** centro documental unificado (`documentos_registro`: tipo, nombre,
referencia, ruta, hash_documental, estado, fecha) con visor; documentos por dominio
(`rrhh_documentos`, `documentos_logisticos`, `activos_documentos`); firma documental.

**Gaps implementados (migr 0119 + `src/services/documental/dms_pro.py`):**
- **Versionado** (`documento_versiones`): `nueva_version` (autoincrementa nº de versión con ruta/hash/
  nota/usuario), `versiones`.
- **Retención / caducidad documental** (`documento_retencion`): `fijar_retencion` (políticas fiscal
  6a / laboral 4a / mercantil 6a / general 3a / temporal 1a; calcula caducidad desde fecha base),
  `documentos_caducados` + job `documental_retencion` (archiva los caducados **sin borrar el fichero**;
  la purga física queda a decisión explícita). Registrado en el JobRegistry.
- **Etiquetas / clasificación** (`documento_etiquetas`): `etiquetar`, `buscar_por_etiqueta`,
  `etiquetas_de` (normalizadas, únicas por documento).

**Reutilización:** referencia `documentos_registro` por `id_documento` (no lo reescribe); Scheduler/
JobRegistry; auditoría; multiempresa.

**Pruebas:** migr 0119; 2 versiones de un documento; retención fiscal (caducidad 2025-12-30 para base
2020) → job archiva 1; etiquetado + búsqueda por etiqueta. **smoke 5 passed.**

**Mejoras futuras:** control de acceso por documento (reutilizar `foundation/permissions.py` +
RBAC); workflow de aprobación de documentos (reutilizar Workflow); OCR/búsqueda de texto completo;
purga física auditada tras archivado.
