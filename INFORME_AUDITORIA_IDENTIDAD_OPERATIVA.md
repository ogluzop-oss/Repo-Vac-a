# INFORME DE AUDITORÍA — IDENTIDAD OPERATIVA DE CENTROS
## Fase 1 — Auditoría completa de la función «Asignar referencia»

> **Naturaleza de este documento:** análisis exclusivamente. No se ha modificado, refactorizado,
> eliminado ni añadido nada al sistema. El proyecto queda exactamente igual que al comenzar.
> Todas las afirmaciones están respaldadas por evidencia (fichero:línea).

---

## 0. Resumen ejecutivo

La función **«Asignar referencia»** (Configuración → pestaña *ASIGNAR REFERENCIA*) es, en su estado
actual, un **par de campos de texto libre globales** (`ref_tienda`, `ref_almacen`) almacenados en una
**única fila** de la tabla `configuraciones`. Su único efecto real es **cosmético**: pintar una
etiqueta tipo `T-<valor> · A-<valor>` en el chip del menú principal (solo para perfiles
GERENTE/OPERARIO) y servir de *fallback* textual para la etiqueta de la tienda activa.

**No** interviene en documentos, facturación, series fiscales, VeriFactu/Facturae, TPV, stock,
pedidos, RBAC, SOMA, jobs, workflow ni integraciones. **No** es única, **no** se valida, **no**
respeta multiempresa (ignora `id_empresa` pese a que la columna existe) y **no** tiene relación 1:1
con ninguna entidad real (`tiendas`, `almacen`, `centros_trabajo`).

Coexiste — sin integrarse — con **dos** conceptos de identidad mucho más sólidos y ya funcionales:
`tiendas.codigo_tienda` (+ TenantContext / selector multitienda) y `centros_trabajo.codigo_centro`
(CDT-NNN, multiempresa, con datos fiscales). Es, por tanto, el eslabón **más primitivo y más
desconectado** de la identidad operativa.

---

## 1. Estado actual

**¿Qué hace exactamente?**
Permite escribir a mano una palabra o número y guardarlo como «referencia de TIENDA» o «referencia
de ALMACÉN». Se elige el tipo en un desplegable (`TIENDA (T-)` / `ALMACÉN (A-)`), se escribe el valor
y se pulsa GUARDAR.
Evidencia: [gestion_usuarios.py:6478-6560](src/gui/gestion_usuarios.py#L6478-L6560).

**¿Qué información almacena?**
Dos cadenas: `configuraciones.ref_tienda` y `configuraciones.ref_almacen`, ambas
`VARCHAR(100) NOT NULL DEFAULT ''`.
Evidencia: [conexion.py:296-301](src/db/conexion.py#L296-L301).

**¿Qué representa realmente?**
Nada estructural. Es una **etiqueta de texto libre** sin semántica forzada. No apunta a un
`id_tienda`, `id_almacen` ni `id_centro`. En la práctica funciona como un «alias visible» del puesto.

**¿Cómo se genera? ¿Manual o automática?**
**Manual** al 100 %. La teclea el usuario. No hay generación automática, ni secuencia, ni prefijo
real (el `T-`/`A-` es solo decorativo, se antepone al pintar, no se almacena).
Evidencia: [gestion_usuarios.py:6544-6551](src/gui/gestion_usuarios.py#L6544-L6551),
[menu_principal.py:1212-1215](src/gui/menu_principal.py#L1212-L1215).

**¿Puede modificarse?**
Sí, libremente y sin restricciones, sobrescribiendo el valor anterior (`UPDATE`).
Evidencia: [conexion.py:1223-1235](src/db/conexion.py#L1223-L1235).

**¿Es única?**
**No.** No hay índice `UNIQUE`, ni validación de duplicados, ni comprobación de formato. La única
validación es «no vacío» en la GUI.
Evidencia: [gestion_usuarios.py:6545-6548](src/gui/gestion_usuarios.py#L6545-L6548); esquema sin
UNIQUE en [conexion.py:296-301](src/db/conexion.py#L296-L301).

---

## 2. Arquitectura encontrada

| Capa | Elemento | Ubicación |
|------|----------|-----------|
| **Ventana/GUI** | Pestaña «ASIGNAR REFERENCIA» dentro de la ventana de Configuración (`GestionUsuariosWindow`) | [gestion_usuarios.py:6477-6560](src/gui/gestion_usuarios.py#L6477) |
| **Widgets** | `combo_ref` (`_PerfilDropdown` TIENDA/ALMACÉN), `input_ref` (`QLineEdit`), botón GUARDAR | [gestion_usuarios.py:6486-6522](src/gui/gestion_usuarios.py#L6486) |
| **Handlers** | `_crear_page_referencia`, `_ref_on_combo_change`, `_guardar_ref` | [gestion_usuarios.py:6478/6535/6544](src/gui/gestion_usuarios.py#L6478) |
| **Registro de pestaña** | Clave `cfg.tab_referencia` en la lista de pestañas de Configuración | [gestion_usuarios.py:3777](src/gui/gestion_usuarios.py#L3777) |
| **Servicio de datos** | `obtener_referencias()` / `guardar_referencia(tipo, valor)` | [conexion.py:1208-1235](src/db/conexion.py#L1208) |
| **Esquema (migración implícita)** | `ALTER TABLE configuraciones ADD COLUMN ref_tienda / ref_almacen` (en `ensure_schema`) | [conexion.py:296-301](src/db/conexion.py#L296) |
| **Consumidor 1 (chip menú)** | `_actualizar_ref_label()` | [menu_principal.py:1203-1222](src/gui/menu_principal.py#L1203) |
| **Consumidor 2 (etiqueta tienda)** | `etiqueta_tienda_actual()` *fallback* | [tiendas.py:83-100](src/db/tiendas.py#L83) |
| **Imports muertos** | RRHH: importa pero **no usa** | [empleados.py:68](src/rrhh/gui/empleados.py#L68), [horarios.py:68](src/rrhh/gui/horarios.py#L68) |
| **Traducciones** | `cfg.tab_referencia`, `cfg.ref_store/warehouse`, `cfg.ref_saved_*`, `cfg.ref_save_err`, `cfg.ref_ph`, `cfg.ref_empty_*` (20 idiomas) | [es.json:1040,1060-1066](assets/lang/es.json#L1040) |

**Clases:** `GestionUsuariosWindow` (host de la pestaña), `_PerfilDropdown` (combo), `MenuPrincipal`
(consumidor del chip). **No existe** una clase/modelo/repositorio propio de «Referencia» ni de
«Identidad operativa»: la lógica está incrustada en la GUI y en dos funciones sueltas de `conexion.py`.

**Servicios / APIs internas:** ninguno específico. No hay entrada en `src/services/**` (grep sin
resultados). No hay endpoint, ni job, ni evento.

---

## 3. Flujo completo de funcionamiento

**Escritura (guardar):**
1. Usuario abre Configuración → pestaña *ASIGNAR REFERENCIA* (`_crear_page_referencia`).
2. Al cargar, `obtener_referencias()` rellena el input según el tipo del combo
   (`_ref_on_combo_change`). [gestion_usuarios.py:6529-6542](src/gui/gestion_usuarios.py#L6529)
3. Usuario escribe valor y pulsa GUARDAR → `_guardar_ref()` valida «no vacío», deduce `tipo`
   (`tienda`/`almacen`) según la etiqueta del combo y llama a `guardar_referencia(tipo, valor)`.
4. `guardar_referencia` mapea a la columna (`ref_tienda`/`ref_almacen`) y ejecuta
   `UPDATE configuraciones SET <col>=%s ORDER BY id ASC LIMIT 1`. [conexion.py:1223-1235](src/db/conexion.py#L1223)

**Lectura (mostrar):**
1. `MenuPrincipal._actualizar_ref_label()` llama a `obtener_referencias()` y compone
   `"T-<ref_tienda> · A-<ref_almacen>"`; **solo** se muestra a GERENTE/OPERARIO (se oculta a
   SUPERADMIN/ADMINISTRADOR). [menu_principal.py:1203-1222](src/gui/menu_principal.py#L1203)
2. `tiendas.etiqueta_tienda_actual()` usa `ref_tienda` **solo como último recurso** si NO hay tienda
   fijada en el TenantContext (selector F1). [tiendas.py:83-100](src/db/tiendas.py#L83)

**Punto crítico del flujo:** tanto lectura como escritura operan sobre `ORDER BY id ASC LIMIT 1`,
es decir, **la primera fila de `configuraciones`, sin filtrar por `id_empresa`**.

---

## 4. Tablas implicadas

**Tabla directa:** `configuraciones`
- Columnas de la feature: `ref_tienda VARCHAR(100) NOT NULL DEFAULT ''`,
  `ref_almacen VARCHAR(100) NOT NULL DEFAULT ''`. [conexion.py:298-299](src/db/conexion.py#L298)
- Columna multi-tenant presente pero **no usada por la feature**:
  `id_empresa CHAR(36) NOT NULL DEFAULT '<EMPRESA_DEFAULT_ID>'`. [conexion.py:385-387](src/db/conexion.py#L385)
- Clave primaria: `id` (fila única de configuración global). Sin índices/UNIQUE/FK sobre las columnas
  de referencia. Sin restricciones de formato.

**Tablas NO implicadas pero relacionadas conceptualmente (identidad real, hoy desconectada):**
- `tiendas` — PK `id`, `codigo_tienda`, `nombre`, `id_empresa`. Identidad de tienda real usada por el
  TenantContext. [tiendas.py:32-64](src/db/tiendas.py#L32)
- `centros_trabajo` — PK `id_centro` (UUID), `codigo_centro` (`CDT-NNN`, secuencial por empresa),
  `id_empresa`, `id_tienda` (opcional, sin 1:1), `es_principal`, dirección fiscal,
  `codigo_cuenta_cotizacion`, `codigo_centro_trabajo`, `estado`. [centros.py:1-42, 94-127](src/db/centros.py#L1)
- `empresas` — raíz multi-tenant. [conexion.py:308-336](src/db/conexion.py#L308)

Ninguna FK conecta `ref_tienda`/`ref_almacen` con `tiendas`, `centros_trabajo` ni `almacen`.

---

## 5. Clases implicadas

- `GestionUsuariosWindow` — contiene toda la pestaña y sus handlers (`_crear_page_referencia`,
  `_ref_on_combo_change`, `_guardar_ref`). No delega en ningún modelo de dominio.
- `_PerfilDropdown` — combo neón reutilizado como selector TIENDA/ALMACÉN.
- `MenuPrincipal` — consume las referencias para el chip (`_actualizar_ref_label`).
- **No hay** clase de dominio `Referencia`/`Centro`/`IdentidadOperativa`. **No hay** repositorio.
  La persistencia son dos funciones de módulo en `conexion.py`.

---

## 6. Servicios implicados

- **Único «servicio»:** funciones de módulo `obtener_referencias()` y `guardar_referencia()` en
  [conexion.py:1208-1235](src/db/conexion.py#L1208) (capa de datos, no capa de servicios).
- **`src/services/**`:** sin ninguna referencia (grep vacío). La feature vive completamente al margen
  de la arquitectura de servicios/dominio del resto del ERP.

---

## 7. Dependencias

**Entrantes (quién depende de la referencia):**
- `menu_principal.py` (chip visual) — dependencia real.
- `db/tiendas.py::etiqueta_tienda_actual` (fallback de etiqueta) — dependencia débil/secundaria.
- `rrhh/gui/empleados.py`, `rrhh/gui/horarios.py` — **import muerto** (importan `guardar_referencia`,
  `obtener_referencias` pero no los invocan en ninguna parte).

**Salientes (de qué depende la referencia):**
- Tabla `configuraciones` (debe existir; la crea/altera `ensure_schema`).
- `ensure_schema()` y `obtener_conexion()` de `conexion.py`.

**Acoplamiento:** bajo en volumen pero **mal ubicado** (lógica en GUI + funciones sueltas en la capa
de conexión, sin servicio ni modelo). Riesgo de dependencia oculta: casi nulo (superficie pequeña y
totalmente rastreada).

---

## 8. Uso transversal por módulos

Resultado del rastreo exhaustivo (`ref_tienda|ref_almacen|obtener_referencias|guardar_referencia`
sobre todo el árbol). El conjunto de consumidores es **cerrado**:

| Módulo | ¿Usa la referencia? | Operación |
|--------|--------------------|-----------|
| Menú principal | **Sí** | Lectura → etiqueta/chip visual (GERENTE/OPERARIO) |
| Tiendas (etiqueta) | **Sí (fallback)** | Lectura → texto de tienda activa si no hay TenantContext |
| Configuración (RRHH GUI) | Import muerto | Ninguna (importan, no llaman) |
| Configuración (pestaña) | **Sí** | Lectura + Escritura (la propia feature) |
| Pedidos, Ventas, **TPV**, Caja, Tickets, Devoluciones, Arqueo | No | — |
| Stock, Logística, Compras, Almacenes | No | — |
| Contratos, RRHH (motor), SAT, Producción, MRP, GMAO, Calidad | No | — |
| Tesorería, **Facturación**, Contabilidad | No | — |
| **Documentación / PDF / Etiquetas / Impresión** | No | — |
| Auditoría, BI, **SOMA**, Copiloto IA | No | — |
| **Jobs, Scheduler, Workflow**, Integraciones, Notificaciones, Correo | No | — |
| Exportaciones / Importaciones / API | No | — |
| Seguridad / RBAC | No | — |

**Conclusión de uso transversal:** la referencia es **puramente presentacional**. No se lee para
filtrar datos, no se escribe en ningún documento ni movimiento, no identifica registros, no participa
en ninguna regla de negocio.

---

## 9. Riesgos detectados

1. **Riesgo multiempresa (alto conceptualmente):** `obtener_referencias`/`guardar_referencia` ignoran
   `id_empresa` y operan sobre la primera fila (`ORDER BY id ASC LIMIT 1`). En un despliegue
   multiempresa **todas las empresas comparten la misma referencia** y una empresa puede sobrescribir
   la de otra. [conexion.py:1214, 1230](src/db/conexion.py#L1214)
2. **Ausencia de unicidad/validación:** dos puestos pueden tener la misma referencia; no hay formato
   ni control de colisiones → inservible como identificador fiable.
3. **Semántica ambigua:** «referencia de tienda» y «de almacén» son globales, no ligadas a la tienda
   ni al almacén concretos con los que trabaja el usuario en cada momento.
4. **Lógica en la GUI:** la deducción de `tipo` depende de comparar el texto del combo; hoy es
   robusto porque se guardan las etiquetas traducidas (`_ref_lbl_*`), pero es lógica de negocio en la
   capa de presentación.
5. **Imports muertos** en RRHH: ruido que sugiere una intención de uso nunca materializada.
6. **Confusión de modelos:** conviven tres conceptos de identidad (referencia global, `codigo_tienda`,
   `codigo_centro`) sin relación explícita → riesgo de decisiones inconsistentes al evolucionar.

**Riesgo de modificar la feature hoy:** **BAJO**. Superficie mínima y totalmente mapeada; solo dos
consumidores reales (ambos visuales). Cualquier evolución puede hacerse sin romper flujos de negocio,
siempre que se preserve la firma de `obtener_referencias`/`guardar_referencia` o se adapten sus 2
llamadores.

---

## 10. Limitaciones

- No es un identificador: es una etiqueta libre.
- No multiempresa (columna presente, uso global).
- No multitienda real (una sola pareja de valores para todo el sistema).
- Sin relación con almacenes reales (`almacen`), ni con `centros_trabajo`, ni con `tiendas`.
- Sin historial, sin auditoría (`log_auditoria` no se invoca aquí), sin versión.
- Sin presencia en documentos, series, fiscalidad ni exportaciones.
- Sin cobertura en la capa de servicios/dominio.

---

## 11. Posibles puntos de ruptura

- **`configuraciones` con >1 fila y multiempresa activa:** el `LIMIT 1` sin `WHERE id_empresa` haría
  que la referencia mostrada dependa del orden físico de filas, no de la empresa activa.
- **Cambio de firma de `obtener_referencias`/`guardar_referencia`:** rompería
  `menu_principal._actualizar_ref_label` y `tiendas.etiqueta_tienda_actual` (y dejaría los imports de
  RRHH aún más huérfanos). Son exactamente **2 puntos** a contemplar.
- **Eliminación de las columnas `ref_*`:** rompería `obtener_referencias` salvo que se migre el
  origen de datos.
- **i18n:** la deducción de `tipo` por comparación de etiqueta seguiría siendo válida porque se
  cachean las etiquetas traducidas, pero cualquier refactor debe mantener ese contrato.

---

## 12. Compatibilidad con Multiempresa

**Parcial / deficiente.** La tabla `configuraciones` **sí** tiene `id_empresa`
([conexion.py:385-387](src/db/conexion.py#L385)), pero las funciones de la feature **no lo usan**. La
infraestructura multi-tenant existe (`empresas`, `empresa_actual_id()`, `TenantContext`) y otros
módulos sí la respetan; la referencia queda como una isla global. Evolucionar hacia identidad
operativa **exige** filtrar por `id_empresa` (y probablemente por `id_tienda`/`id_centro`).

---

## 13. Compatibilidad con Multitienda

**Inexistente en la práctica.** El multitienda real se resuelve por otra vía: el **selector F1 /
TenantContext** (`cambiar_contexto_tienda`, `tienda_actual_id`, `codigo_tienda`) en
[tiendas.py:103-146](src/db/tiendas.py#L103). La referencia solo actúa de **fallback textual** cuando
no hay tienda fijada [tiendas.py:88-99](src/db/tiendas.py#L88). No existe una referencia por tienda:
es un valor único global. Cualquier arquitectura de identidad operativa debería converger con
`tiendas`/`codigo_tienda` en lugar de duplicarlo.

---

## 14. Compatibilidad con SOMA

**Nula.** SOMA / Copiloto / Especialistas IA / Gemelo Digital **no** consumen `ref_tienda`/
`ref_almacen` (grep sin resultados en `src/services/**` ni en `src/soma/**`). SOMA no la usa para
contexto, decisión ni filtrado. Para que la identidad operativa alimente a SOMA habría que exponerla
como estado de dominio (p.ej. vía Gemelo Digital), cosa que hoy no ocurre.

---

## 15. Compatibilidad con Integraciones

**Nula.** No aparece en correo corporativo, notificaciones, webhooks, conectores, Microsoft/Google/
DocuSign ni en ninguna API. No hay riesgo de romper integraciones al evolucionarla, pero tampoco
aporta identidad a los mensajes/documentos salientes (oportunidad de mejora, no dependencia).

---

## 16. Compatibilidad con Fiscalidad

**Nula / desacoplada.** No interviene en series, numeraciones, prefijos, VeriFactu, Facturae,
certificados ni firmas. La identidad fiscal del centro se obtiene hoy por `centros_trabajo` a través
de `empresa.datos_corporativos()` → `centro_codigo`, `codigo_centro_trabajo`,
`codigo_cuenta_cotizacion` [empresa.py:298-378](src/db/empresa.py#L298),
[centros.py:19-25](src/db/centros.py#L19). La «referencia» no toca nada de esto: una futura identidad
operativa con relevancia fiscal debería apoyarse en `centros_trabajo`, no en los campos `ref_*`.

---

## 17. Compatibilidad con Documentación

**Nula.** No se imprime ni se incrusta en facturas, pedidos, albaranes, presupuestos, contratos,
nóminas, informes, PDF ni etiquetas. Los documentos toman los datos del centro desde
`datos_corporativos()`/`centros_trabajo`. La referencia es invisible fuera del chip del menú.

---

## 18. Conclusiones técnicas

1. **«Asignar referencia» es la capa de identidad más primitiva del sistema:** dos cadenas de texto
   libre globales (`configuraciones.ref_tienda`/`ref_almacen`), manuales, no únicas, no validadas,
   con efecto **solo visual** (chip del menú + fallback de etiqueta de tienda).
2. **Está desacoplada de todo el negocio:** cero uso en documentos, fiscalidad, TPV, stock, pedidos,
   RBAC, SOMA, jobs, workflow e integraciones. Superficie total: **1 pestaña de GUI + 2 funciones de
   datos + 2 consumidores visuales + 2 imports muertos**.
3. **No respeta multiempresa** (ignora `id_empresa`) ni **multitienda** (valor único global), pese a
   que ambas infraestructuras existen y son sólidas en el resto del ERP.
4. **Ya existen dos modelos de identidad superiores y funcionales** con los que debería converger, no
   competir:
   - `tiendas` + `codigo_tienda` + TenantContext (multitienda real, selector F1).
   - `centros_trabajo` + `codigo_centro` (CDT-NNN) + `datos_corporativos()` (identidad rica con datos
     fiscales, ya consumida por documentos).
5. **El riesgo de evolucionar esta función es bajo:** su reducida superficie y su nula participación
   en reglas de negocio permiten rediseñarla hacia una verdadera **Identidad Operativa de Centros**
   sin romper flujos, preservando (o adaptando) únicamente los 2 llamadores visuales y limpiando los
   2 imports muertos.
6. **Recomendación para la Fase 2 (solo enunciada, no diseñada aquí):** la nueva identidad operativa
   debería unificar referencia ↔ `tiendas`/`centros_trabajo`/`almacen`, ser multiempresa y
   multitienda por diseño, ser única y validada, quedar disponible como estado de dominio (para SOMA,
   documentos, fiscalidad e integraciones) y sustituir progresivamente los campos `ref_*` mediante el
   patrón *Strangler* (sin eliminarlos de inmediato).

---

### Anexo A — Evidencia (índice de ficheros:línea)

- Persistencia: [conexion.py:296-301](src/db/conexion.py#L296) · [conexion.py:385-387](src/db/conexion.py#L385) · [conexion.py:1208-1235](src/db/conexion.py#L1208)
- GUI Configuración: [gestion_usuarios.py:3777](src/gui/gestion_usuarios.py#L3777) · [gestion_usuarios.py:6477-6560](src/gui/gestion_usuarios.py#L6477)
- Consumidores: [menu_principal.py:1203-1222](src/gui/menu_principal.py#L1203) · [tiendas.py:83-100](src/db/tiendas.py#L83)
- Imports muertos: [empleados.py:68](src/rrhh/gui/empleados.py#L68) · [horarios.py:68](src/rrhh/gui/horarios.py#L68)
- Identidad paralela: [centros.py](src/db/centros.py) · [tiendas.py:32-146](src/db/tiendas.py#L32) · [empresa.py:298-378](src/db/empresa.py#L298)
- i18n: [es.json:1040,1060-1066](assets/lang/es.json#L1040)

### Anexo B — Método de auditoría

Rastreo por patrón sobre todo el árbol (`ref_tienda`, `ref_almacen`, `obtener_referencias`,
`guardar_referencia`, `tab_referencia`, `referencia`, `codigo_centro`, `codigo_tienda`,
`centros_trabajo`, `datos_corporativos`) en `src/**/*.py`, `src/services/**`, `assets/lang/**` y
`bootstrap_mariadb.sql`. El conjunto de consumidores resultante es cerrado y está listado íntegro en
la sección 8. **No se ejecutó ni modificó código**; la auditoría es estática y no ha alterado el
estado del proyecto.
