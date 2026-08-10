# AUDITORÍA — INTEGRACIÓN DE StorageProvider (Fase 11, post-corrección H1)

Fecha 2026-07-27. Actualiza la auditoría de Fase 10 tras la corrección parcial de H1.

## Estado en Fase 10 (previo)

- `services/storage` implementado y unit-tested, pero **0% de adopción**; ~96 coincidencias de escritura a
  filesystem.

## Análisis refinado (Fase 11)

- La búsqueda inicial (~96) incluía **temporales, caché, preview, barcode, matplotlib, assets, config** — que
  **NO deben migrarse** (por diseño del propio prompt).
- La superficie **real de documentos empresariales persistentes** son **17 ficheros** que ya convergen en el
  **chokepoint único** `db.documentos.registrar_documento` (índice `documentos_registro`).

## Corrección implementada (write-through en el chokepoint)

- Nueva fachada `services/storage/documentos.persistir_fichero(id_empresa, tipo, ruta_local, nombre=)`:
  saneo de nombre, clave `tenant/{id_empresa}/{tipo}/{nombre}`, subida vía `obtener_storage()`, bulletproof y
  con auditoría de error explícita en fallo (S3).
- Cableado en `registrar_documento`: **todo** documento registrado se persiste durablemente en el
  StorageProvider (S3 en AWS; copia tenant-aware en local) — en UN punto, sin tocar los 17 generadores (N7).

## Tabla de estado (superficie real)

| Flujo | Chokepoint | Persistencia durable (write) | Read/Delete vía Storage | Estado |
|---|---|---|---|---|
| RRHH (nóminas/contratos/docs) | `registrar_documento` | ✅ write-through | ❌ pendiente | 🟡 |
| Fiscal/AEAT (documento/evidencias) | idem | ✅ | ❌ | 🟡 |
| Ventas/TPV (ticket/factura/cierre Z) | idem | ✅ | ❌ | 🟡 |
| Etiquetas / informes / export BI | idem | ✅ | ❌ | 🟡 |
| Cámaras (grabaciones) | idem | ✅ | ❌ | 🟡 |

## Lo que queda pendiente (honesto — impide el 🟢 limpio)

1. **Generación**: los renderers siguen escribiendo primero en ruta local temporal (luego se persiste durable).
   El criterio estricto "no escribir directamente en filesystem" no se cumple del todo.
2. **Lectura/descarga/borrado** desde S3 y **almacenamiento de la clave S3** en `documentos_registro` (requiere
   migración + retoque del visor) — para que, en Fargate, el documento se recupere desde S3 tras reciclar la
   tarea.

## Valoración

- **Durabilidad (riesgo de pérdida en Fargate)**: **resuelta** para el write path de los 17 flujos (mejora
  material respecto a Fase 10). 🟢 en durabilidad de escritura.
- **Integración estricta (write+read+delete por StorageProvider)**: 🟡 **parcial**. H1 no se declara cerrado.

Recomendación: completar lectura/borrado + clave en registro (migración) en la siguiente iteración; priorizar
RRHH/fiscal/facturación.
