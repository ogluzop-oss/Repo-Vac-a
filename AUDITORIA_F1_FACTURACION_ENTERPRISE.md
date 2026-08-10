# AUDITORÍA FORENSE — FASE 1

## Bloque: Facturación Profesional Avanzada (Enterprise)

> **Naturaleza de este documento:** entregable de la FASE 1. Es **solo diagnóstico**.
> No se ha modificado ni una línea de código ni de esquema. Cumple el mandato
> *"No modificar nada antes de completar esta auditoría"*.
>
> **Fecha:** 2026-06-28 · **Alcance:** subsistema de facturación de cliente (TPV) y su
> relación con el núcleo fiscal (Verifactu/Facturae), Centro Documental, contabilidad y tesorería.
> **Método:** lectura estática del código y del esquema de migraciones (no se ejecutó la app).

---

## 1. Resumen ejecutivo

El sistema tiene **DOS subsistemas de "factura" paralelos y hoy DESCONECTADOS entre sí**:

1. **Factura COMERCIAL de cliente** (la que emite el botón *Factura* del TPV).
   Documento de gestión/rentabilidad. Numeración `FC######` derivada del autoincrement,
   PDF simple, **IVA de un único tipo**, **sin hash, sin QR, sin firma, sin numeración fiscal**.
   Capa: [factura_window.py](src/gui/factura_window.py) → [facturas_cliente.py](src/db/facturas_cliente.py) + [factura_pdf.py](src/utils/factura_pdf.py) → Centro Documental.

2. **Núcleo FISCAL** (Verifactu/Facturae, rama C3).
   Infraestructura legal sólida: **encadenado hash por empresa+serie**, QR, estados AEAT/CSV,
   cola asíncrona de firma/envío, XAdES, Facturae+FACe, multiempresa/tienda/caja.
   Se dispara en la **VENTA/ticket** (no en la factura comercial) y solo si `fiscal_config.activo=1`.
   Capa: [src/services/fiscal/](src/services/fiscal/) + [fiscal.py](src/db/fiscal.py), hook en [conexion.py:1657](src/db/conexion.py#L1657).

**Conclusión central:** existe una base fiscal de calidad, pero la **factura comercial que ve
el usuario NO es una factura fiscal** y **no está enlazada** con el registro fiscal de su venta.
El bloque Enterprise debe **tender el puente** entre ambos mundos (snapshot documental,
multi-IVA, QR fiscal, eventos de auditoría) **sin romper** ninguno de los dos.

---

## 2. Mapa de arquitectura (estado real)

```
            ┌──────────────────────── TPV (venta) ────────────────────────┐
            │  conexion.registrar_venta_con_items()                        │
            │     ├─ ventas / venta_items / kárdex / lotes / stock         │
            │     ├─ cola contable (posting ventas)                        │
            │     └─ gancho_venta()  ──►  NÚCLEO FISCAL (si activo=1)       │
            │            fiscal_registros (hash chain) + fiscal_cola       │
            │            → worker: XAdES, Verifactu XML, AEAT, QR/CSV      │
            └──────────────────────────────────────────────────────────────┘
                                   │  (NO hay enlace)
                                   ▼
            ┌──────────────── Botón "Factura" del TPV ────────────────┐
            │  factura_window._generar_factura()                       │
            │     ├─ exige cliente REGISTRADO (regla de negocio)       │
            │     ├─ fiscalidad.desglose_iva(total)  ← UN solo tipo    │
            │     ├─ FC.crear_factura()  → facturas_cliente(+lineas)   │
            │     │        numero = "FC{autoincrement:06d}"            │
            │     └─ factura_pdf.generar_y_registrar()                 │
            │              PDF A4 simple  +  Centro Documental          │
            └──────────────────────────────────────────────────────────┘
```

Los dos caminos comparten la **venta** (`id_venta`) como dato, pero la factura comercial
**no referencia** el `fiscal_registros.id` de esa venta, ni hereda su serie/numero/hash/QR.

---

## 3. Inventario de componentes

| Capa | Fichero | Responsabilidad | Estado |
|---|---|---|---|
| GUI | [factura_window.py](src/gui/factura_window.py) | Buscar ventas, ver ticket, asignar cliente, generar/ver/eliminar factura | Funcional (comercial) |
| GUI | [tpv.py](src/gui/tpv.py) | Lanza `FacturaWindow`; ticket fiscal en impresión | Funcional |
| Util | [factura_pdf.py](src/utils/factura_pdf.py) | PDF de factura + alta documental | Simple, sin QR/firma |
| Util | [fiscalidad.py](src/utils/fiscalidad.py) | IVA por país; `desglose_iva` y `desglose_iva_lineas` (multi-IVA **ya existe**) | Multi-IVA infrautilizado |
| Util | [divisas.py](src/utils/divisas.py) | Formato/redondeo por divisa | OK |
| DB | [facturas_cliente.py](src/db/facturas_cliente.py) | CRUD factura comercial, estados, cobros, márgenes | Comercial, no fiscal |
| DB | [fiscal.py](src/db/fiscal.py) | Config + registros encadenados + cola | Robusto |
| DB | [ventas_busqueda.py](src/db/ventas_busqueda.py) | Buscar/obtener venta, asignar cliente, ocultar | OK |
| DB | [documentos.py](src/db/documentos.py) | Centro Documental unificado | OK |
| DB | [empresa.py](src/db/empresa.py) | Emisor (razón social, CIF, domicilio fiscal, país) | OK |
| Svc | [src/services/fiscal/](src/services/fiscal/) | Verifactu XML/legal, XAdES, Facturae, FACe, worker, certificados | Robusto |
| Svc | hook [hooks.py](src/services/fiscal/hooks.py) | `gancho_venta` best-effort tras la venta | OK |

---

## 4. Modelo de datos actual

### 4.1 `facturas_cliente` (migr. [0042](src/database/migraciones/0042_facturas_cliente.py))
```
id_factura PK · id_empresa CHAR(36) · id_cliente · id_venta · id_tienda INT
numero VARCHAR(20) · serie VARCHAR(10) · estado · base/iva/total DEC(12,2)
cobrado · fecha_emision · fecha_vencimiento · observaciones · fecha
```
`facturas_cliente_lineas`: `codigo_articulo · descripcion · cantidad INT · precio_unitario ·
coste_unitario · subtotal` — **sin IVA por línea, sin descuento por línea**.

### 4.2 Núcleo fiscal (migr. [0002](src/database/migraciones/0002_fiscal.py) + 0003–0007)
```
fiscal_config(id_empresa PK, territorio, modo, proveedor, serie, serie_por, entorno, activo)
fiscal_registros(id, id_empresa, id_tienda, serie, numero, tipo, referencia, total,
                 hash, hash_anterior, qr, payload, proveedor, estado, estado_aeat, csv_aeat)
                 UNIQUE(id_empresa, serie, numero)
fiscal_cola(id, id_registro, accion, estado, intentos, ultimo_error, proximo_intento)
```

### 4.3 Tablas que el plan Enterprise propone (verificado: **NINGUNA existe aún**)
`factura_auditoria`, `factura_fiscal`, `factura_impuestos`, `factura_eventos`, `factura_qr`
→ son nuevas. La próxima migración disponible es **0071** (última aplicada: 0070).

---

## 5. Hallazgos (clasificados por severidad)

### 🔴 Críticos (integridad fiscal/legal)
- **F-01 · La factura comercial no es factura fiscal.** No genera registro encadenado, ni
  QR, ni firma, ni numeración fiscal por serie. Si la empresa opera con Verifactu, el
  documento que recibe el cliente (`FC######`) **no es el documento legal**.
- **F-02 · Borrado REAL de facturas con hueco de numeración.**
  [facturas_cliente.eliminar_factura](src/db/facturas_cliente.py#L96) hace `DELETE` físico y
  `factura_window` borra también el PDF. Una factura legal **no puede eliminarse** (solo
  rectificarse/anularse) ni dejar huecos. `numero=FC{autoincrement}` ⇒ saltos al borrar.
- **F-03 · Sin enlace factura ↔ registro fiscal.** `facturas_cliente` no tiene columna que
  apunte a `fiscal_registros.id` de su venta. Imposible auditar correspondencia legal.

### 🟠 Altos (correctitud contable / multiempresa)
- **F-04 · IVA de un solo tipo.** `_generar_factura` usa `desglose_iva(total)` (tipo único de
  empresa). Si la venta mezcla tipos (21/10/4/0), el desglose es incorrecto. **La función
  multi-IVA `desglose_iva_lineas` ya existe** pero no se usa, y `venta_items` **no guarda IVA
  por línea** ([ventas_busqueda.py:180](src/db/ventas_busqueda.py#L180)) → falta el dato origen.
- **F-05 · `cantidad INT` en líneas.** Las ventas a granel/báscula (peso decimal) se
  truncan a entero al crear la factura ([facturas_cliente.py:51](src/db/facturas_cliente.py#L51)).
- **F-06 · Sin snapshot documental.** El PDF se regenera de datos vivos (emisor, cliente,
  precios). Si cambian los *Datos de empresa* o el cliente, una factura ya emitida cambiaría
  su contenido al re-renderizar. No hay congelado inmutable del documento.

### 🟡 Medios (UX / robustez / trazabilidad)
- **F-07 · Sin eventos de auditoría.** No hay traza de quién/cuándo generó, vio, descargó o
  anuló una factura (el plan pide `factura_eventos`).
- **F-08 · Estados desaprovechados.** `facturas_cliente` define
  `borrador/emitida/cobrada/parcial/vencida/anulada`, pero `_generar_factura` deja la factura
  en `borrador` y nunca llama a `emitir()`. El PDF se marca `estado='generado'` en documental.
- **F-09 · Numeración no configurable.** `FC######` global por empresa; no respeta
  `serie`/`serie_por` (empresa/tienda/caja) que el núcleo fiscal sí soporta.
- **F-10 · Emisor con doble fuente.** `_emisor()` lee `empresas` y cae a `configuracion`;
  posible incoherencia si ambas difieren.

### 🟢 Fortalezas (reutilizables — no rehacer)
- Núcleo de **encadenado hash atómico** (`FOR UPDATE`) e **idempotente** por referencia
  ([fiscal.py:139](src/db/fiscal.py#L139), [hooks.py:39](src/services/fiscal/hooks.py#L39)).
- **Verifactu** (XML/XSD/WSDL, XAdES, mTLS) y **Facturae+FACe/FACeB2B** ya implementados.
- **Multi-IVA aritmético** disponible (`desglose_iva_lineas`).
- **IVA por país** y **multidivisa** centralizados y reutilizables.
- **Centro Documental** unificado para alta/baja de PDFs.
- Patrón de **migraciones aditivas/reversibles/idempotentes** consolidado (hasta 0070).

---

## 6. Superficie de regresión (lo que NO se puede romper)

Cualquier cambio del bloque Enterprise debe preservar:
1. **Kárdex / lotes / stock** y **cola contable** de la venta ([conexion.registrar_venta_con_items](src/db/conexion.py)).
2. **Encadenado hash fiscal** y su **idempotencia** (no re-registrar, no romper cadena).
3. **Ticket fiscal** (QR/leyenda/CSV) en impresión ([impresion.py:437](src/utils/impresion.py#L437)).
4. **Verifactu/Facturae/AEAT** y la **cola asíncrona** (worker).
5. **Tesorería** (vencimientos/cobros) y **márgenes** (`informe_margenes`).
6. **Multiempresa/tienda** (coerción `id_tienda` INT ya resuelta) y **multidivisa**.
7. **Reimpresión de tickets** del TPV (usa `buscar_ventas` sin `excluir_ocultas`).

---

## 7. Lectura de preparación por fase (plan Enterprise 1–19)

| Tema del plan | ¿Base existe? | Acción esperada en fases siguientes |
|---|---|---|
| `factura_fiscal` (enlace legal) | Parcial (núcleo fiscal) | Tabla puente factura↔`fiscal_registros` |
| `factura_impuestos` (multi-IVA) | Aritmética sí; dato origen no | Persistir IVA por línea en venta→factura |
| `factura_qr` | QR en `fiscal_registros.qr` | Reutilizar/derivar QR a la factura comercial |
| `factura_auditoria`/`factura_eventos` | No | Tablas nuevas + ganchos de evento |
| Snapshot documental | No | Congelar emisor/receptor/líneas/totales al emitir |
| Verifactu prep | Sí (robusto) | Conectar factura comercial al flujo legal |
| Multiempresa/tienda/almacén | Sí | Respetar serie_por en numeración de factura |
| Anulación/rectificativa | No (hoy borra) | Sustituir borrado por anulación/abono |

---

## 8. Decisiones de diseño (resueltas)

FASE 1 (diagnóstico) **completada**. Decisiones tomadas para condicionar la FASE 2:

- **D1 · ENLAZAR.** La factura comercial se mantiene y se **enlaza** con `fiscal_registros`
  mediante una tabla puente `factura_fiscal`. (resuelve F-03; mitiga F-01 sin reescribir el flujo)
- **D2 · SERIE FISCAL.** Se adopta `serie`/`serie_por` (empresa/tienda/caja) del núcleo fiscal,
  con numeración **secuencial sin huecos por serie**, sustituyendo `FC######`. (resuelve F-09)
- **D3 · ANULAR/RECTIFICAR.** Se retira el `DELETE` físico; se pasa a **anulación**
  (`estado='anulada'`) y **factura rectificativa/abono**. (resuelve F-02)

## 9. Roadmap FASE 2 — COMPLETADO ✅

Todos los pasos ejecutados, verificados (instanciación offscreen + tests) y **sin commitear**.
Migraciones nuevas **0071–0075** (aditivas, idempotentes y reversibles). Sin tocar la lógica
validada (§6).

| # | Paso | Estado | Migr. | Hallazgo |
|---|---|---|---|---|
| 1 | Tablas base (`factura_fiscal/impuestos/eventos/qr` + snapshot) | ✅ | 0071 | infraestructura |
| 2 | Multi-IVA por línea (`articulos.iva`→`factura_impuestos`) | ✅ | 0072 | **F-04** |
| 3 | Numeración por serie fiscal (`serie_efectiva`, sin huecos) | ✅ | 0073 | **F-09** |
| 4 | Anulación + rectificativa (sin borrado físico) | ✅ | 0074 | **F-02** |
| 5 | Enlace fiscal (`factura_fiscal` + QR/hash del registro) | ✅ | — | **F-03/F-01** |
| 6 | Snapshot documental inmutable y reproducible | ✅ | — | **F-06** |
| 7 | Eventos de auditoría (`factura_eventos` + usuario) | ✅ | — | **F-07** |
| 8 | Cantidad decimal (granel sin truncar, subtotal real) | ✅ | 0075 | **F-05** |

### Ajustes de presentación del documento/UX (posteriores a la validación visual)
- Título de la factura: **"FACTURA PAGADA"** (sin nº en el título; el nº va en su bloque).
- **Logo corporativo** (`documentos/logo_corporativo.png`) en la esquina superior derecha.
- Helpers unificados en `catalogo_gestion`: `_btn_x` (X roja, igual que *Devolución de ticket*)
  y `_btn_salir_sidebar` (SALIR AL MENÚ rojo al fondo del sidebar).
- Botón superior derecho **VOLVER AL MENÚ → X roja** en 17 ventanas (Correo, Compras avanzado,
  Clientes CRM, Tesorería, BI, AEAT, Seguridad, Workflow, Notificaciones, SaaS, RRHH, Portal
  empleado, Kárdex, Inventario físico, Lotes, Stock por almacén, Gestión de almacenes).
- **SALIR AL MENÚ** rojo al fondo del sidebar en Catálogo, Compras y Contabilidad.
- TPV: botón **SALIR → solo "X"**.

### Funciones nuevas de la capa de datos (reutilizables)
`facturas_cliente`: `anular_factura`, `vincular_fiscal`, `obtener_fiscal`, `obtener_impuestos`,
`guardar_snapshot`/`obtener_snapshot`, `registrar_evento`/`listar_eventos`, `_serie_factura`.
`factura_pdf`: `construir_snapshot`, `generar_pdf_desde_snapshot`, `emisor`, `_logo_corp`,
`_qr_imagen`, multi-IVA + bloque fiscal + cantidad granel.

> Pendiente (fuera de alcance de esta FASE): integración del fichero telemático oficial de
> Verifactu/Facturae en la factura comercial (el núcleo legal ya existe y queda enlazado).
