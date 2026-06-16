# Núcleo fiscal — Smart Manager AI (C3)

Capa neutra y extensible para el cumplimiento fiscal (Verifactu/Facturae/TicketBAI…),
construida con el mismo patrón **registry + adaptadores** del resto del sistema.

## C3.1 — Base (hecho)

- **Modelo de datos** (migración C4 `0002_fiscal`):
  - `fiscal_config` — configuración fiscal POR EMPRESA (territorio, modo
    `verifactu`/`no_verifactu`, proveedor, integrador, serie, activo).
  - `fiscal_registros` — registros de facturación con **ENCADENADO HASH** por
    empresa+serie (numeración + `hash`/`hash_anterior` + QR + payload + estado).
  - `fiscal_cola` — cola de envío/reenvío (reintentos, idempotente).
- **Capa DB** `src/db/fiscal.py`: config; `insertar_registro` (numeración y
  encadenado **atómicos** con `FOR UPDATE`); `cadena_valida()` (verifica integridad);
  cola (`encolar`/`listar_cola`/`actualizar_cola`).
- **Interfaces cerradas** (`src/services/fiscal/base.py`): `RegistroFiscal`,
  `Firmante` (local cifrado/HSM futuro), `Emisor` (envío/integradores), `ProveedorFiscal`.
- **Registry + factory**: `proveedor_fiscal_actual()` resuelve el proveedor por la
  config de la empresa (nombre o territorio). Añadir Verifactu/Facturae/TicketBAI =
  un módulo nuevo con `@registrar_proveedor(...)`, **sin tocar el núcleo**.
- **Proveedor `simulado`**: funcional para pruebas (encadenado real + QR de
  marcador), **sin lógica legal**.

### NO incluido en C3.1 (siguientes fases)
Envíos reales a AEAT, integradores externos, firma XAdES real, Facturae real,
TicketBAI, y la lógica legal definitiva de Verifactu.

## Cómo añadir un proveedor fiscal (futuro)

```python
# src/services/fiscal/verifactu.py
from src.services.fiscal.base import ProveedorFiscal
from src.services.fiscal.registry import registrar_proveedor

@registrar_proveedor("verifactu", territorios=("comun",))
class ProveedorVerifactu(ProveedorFiscal):
    def registrar(self, tipo, referencia=None, total=0.0, payload=None): ...
```
…y añadirlo a `MODULOS` en `src/services/fiscal/__init__.py`.

## C3.2 — Núcleo robusto (hecho)

Endurece el núcleo sin lógica legal ni integraciones externas todavía.

### Estrategia de serie configurable (migración C4 `0003`)
- `fiscal_config.serie_por` ∈ `empresa | tienda | caja` (**por defecto `tienda`**).
- `fiscal.serie_efectiva(config, id_tienda, id_caja)` resuelve la serie:
  `empresa→"A"`, `tienda→"A-T<tienda>"`, `caja→"A-C<caja>"`. **Cada serie efectiva
  mantiene su PROPIA cadena hash y numeración** (cajas independientes, sin contención).
- Degradación segura: si falta el ámbito (tienda única sin `id_tienda`), cae a la
  serie base → no rompe numeraciones existentes.

### Hash por proveedor
- `ProveedorFiscal.campos_hash(serie, numero, tipo, referencia, total)` define el
  conjunto de campos de la huella (Verifactu/TicketBAI fijarán el formato legal).
- `insertar_registro(campos_hash=…)` acepta dict **o callable** (el número se
  resuelve atómicamente dentro de la transacción). `cadena_valida` re-deriva con
  el `campos_hash` del proveedor de cada registro.

### Evidencias = centro documental + fichero
- `evidencias.guardar_evidencia(registro, clase, contenido)` escribe el artefacto
  (`xml`/`firma`/`acuse`/`qr`) en `documentos/fiscal/<empresa>/` y lo **indexa en el
  centro documental** (`documentos_registro`). La **BD fiscal NO guarda binarios**:
  solo referencias/metadatos/hash/estado. Válido para Verifactu y Facturae.
- `render.qr_png(texto)` genera el PNG del QR (degrada a `None` si falta `qrcode`).

### Integración TPV (detrás de `activo`)
- `hooks.gancho_venta(...)` se llama tras registrar venta/factura. Si
  `fiscal_config.activo=0` (**por defecto**) retorna de inmediato (lectura por PK)
  → impacto prácticamente nulo y **cero cambio de flujo** en instalaciones actuales.
  Si está activo: genera el registro fiscal (hash síncrono) y lo **encola** para
  firma/envío asíncronos. **Best-effort**: nunca lanza ni revierte la venta.

### Worker de cola
- `worker.procesar_cola()` — esqueleto **idempotente** con **backoff exponencial**
  (respeta `proximo_intento`; cierra entradas ya enviadas/anuladas sin reenviar).
- `factory.firmante_para/emisor_para` devuelven implementaciones **no-op** (firma y
  envío reales en C3.3/C3.4/C3.5 como adaptadores, sin tocar el núcleo).

### NO incluido en C3.2 (siguientes fases)
Lógica legal Verifactu, XAdES real, Facturae, TicketBAI, envíos AEAT/FACe e
integradores. La atomicidad/bloqueo legal del registro respecto a la venta se
concreta en C3.3.

## C3.3 — Verifactu real (hecho, sobre el núcleo C3.2 congelado)

Régimen Verifactu como **adaptador**, sin tocar la arquitectura base. Todo el
formato legal está aislado para poder cotejarlo con el XSD/WSDL oficial de AEAT.

> ⚠️ Antes de envíos reales, **contrastar** `verifactu_legal.py` (campos/orden de la
> huella, formato de fechas, URL del QR), `verifactu_xml.py` (elementos/namespaces)
> y los endpoints del emisor con el **XSD/WSDL oficial** y el validador de
> preproducción. Está todo concentrado en esos módulos para que el ajuste sea local.

### Puntos de extensión añadidos al núcleo (aditivos, retrocompatibles)
- `insertar_registro(huella_fn=…)`: serializador de huella por régimen (default = núcleo).
- `ProveedorFiscal.recalcular_huella(fila, prev)`: verificación por proveedor;
  `cadena_valida` la usa → valida igual el formato neutro y el legal.
- `fiscal.actualizar_aeat()` / `obtener_por_referencia()`: trazabilidad y lectura.
- Config `entorno` (preproduccion/produccion) y migración C4 `0004`
  (`fiscal_config.entorno`, `fiscal_registros.estado_aeat`/`csv_aeat`).

### C3.3.1 — Formato legal
`verifactu_legal.py`: `huella_alta`/`huella_anulacion` (SHA-256 de `clave=valor&…`
en orden legal, hex MAYÚS, encadenada), `num_serie`, `contenido_qr` (cotejo AEAT),
leyenda. Proveedor `verifactu` (`@registrar_proveedor("verifactu", ("comun",))`):
NIF de `empresa.info_documento`, IVA de `utils.fiscalidad`; el `payload` guarda los
datos legales para XML/verificación; QR legal en el registro.

### C3.3.2 — XML
`verifactu_xml.py`: `RegistroAlta`/`RegistroAnulacion` + lote
`RegFactuSistemaFacturacion`, construido **en el worker** desde el payload + huella.

### C3.3.3 — Envío AEAT (sin tocar el worker)
`emisores/verifactu_aeat.py` (`EmisorVerifactu`): encapsula sobre SOAP, POST, parseo
de acuse y **persiste estado_aeat/csv + evidencias** (XML y acuse). **Transporte
inyectable** (tests sin red). `disponible()=False` sin transporte/certificado →
el worker deja el registro **en espera** (no envía a ciegas). `factory.emisor_para`
lo devuelve cuando `proveedor='verifactu'`. Certificado real y **producción → C3.5**.

### C3.3.4 — Ticket
`services/fiscal/ticket.info_ticket()` aporta **QR de cotejo + leyenda “VERI\*FACTU”**
(+ CSV) al ticket **solo** si el módulo está activo en modo Verifactu; en otro caso
el ticket se imprime exactamente igual que siempre.

### NO incluido en C3.3 (siguientes fases)
Firma XAdES (NO-VERIFACTU), gestión de certificados (local cifrado/HSM) y operativa
de **producción** → **C3.5**. Facturae → **C3.4**. TicketBAI → posterior.

## C3.3.1.1 — Conformidad legal (hecho)

Fase correctiva para dejar Verifactu conforme al **XSD/WSDL oficiales** (sin tocar el
núcleo C3.2). Recursos en `src/services/fiscal/esquemas/` (ver `PROCEDENCIA.md`).

- **XML conforme** (`verifactu_xml.py`): `RegFactuSistemaFacturacion` (Cabecera +
  RegistroFactura → RegistroAlta/Anulacion) con namespaces `sf`/`sfLR`, `IDFactura`
  anidado, `NombreRazonEmisor`, `DescripcionOperacion`, `Desglose/DetalleDesglose`,
  `Encadenamiento` completo (`PrimerRegistro`/`RegistroAnterior`), `SistemaInformatico`
  completo, `TipoHuella=01`. Generado con stdlib; **validado contra el XSD** con `lxml`.
- **Huella legal**: anclada al **ejemplo oficial de AEAT** (vector dorado en tests).
- **QR**: host de producción oficial `agenciatributaria.es`.
- **Emisor** (`emisores/verifactu_aeat.py`): SOAP document/literal, endpoints del WSDL,
  parseo real de `EstadoEnvio`/`RespuestaLinea`/`CSV`/`TiempoEsperaEnvio` (+ pacing).
- **lxml** es dependencia **solo de dev/build** (validación XSD); el runtime parsea con
  stdlib. XSD/WSDL se empaquetan en el `.exe`.

### Trazabilidad: verificado oficial vs espejo vs pendiente

| Elemento | Estado | Fuente |
|---|---|---|
| Algoritmo y formato de huella (orden, `clave=valor&`, SHA-256) | ✅ **Oficial** | FAQ AEAT + ejemplo literal (vector dorado) |
| Hash en hexadecimal MAYÚSCULAS | ⚠️ Pendiente PDF | práctica estándar; confirmar en *huella v0.1.2* |
| QR: host, parámetros (`nif/numserie/fecha/importe`), fecha `dd-mm-yyyy` | ✅ **Oficial** | especificación QR AEAT |
| QR: importe sin relleno vs 2 decimales | ⚠️ Pendiente PDF | uso `%.2f` (válido por patrón); confirmar canónico |
| Estructura XML RegistroAlta/Anulacion, Cabecera, Desglose, SIF, namespaces | 🟡 **Espejo** (valida XSD) | XSD `hectorsipe/aeat-verifactu` (autoría AEAT) |
| Endpoints SOAP + operación + document/literal | 🟡 **Espejo** | WSDL del espejo |
| Respuesta: EstadoEnvio/RespuestaLinea/CSV/TiempoEsperaEnvio | 🟡 **Espejo** | `RespuestaSuministro.xsd` |
| `TipoFactura`, `CalificacionOperacion=S1`, `ClaveRegimen=01` | ⚠️ Pendiente fiscal | valores por defecto razonables; confirmar por empresa |
| NIF del productor del SIF y versión/instalación declaradas | ⚠️ Pendiente | placeholder en `SIF` |
| Round-trip **live** contra preproducción | ⛔ **Pendiente C3.5** | requiere certificado de pruebas |

> **🟡 Espejo** = validado contra XSD/WSDL del espejo (cabeceras con autoría AEAT) pero
> **pendiente de re-sellado** contra el **ZIP oficial** de AEAT.
> Honrado **exacto** de `TiempoEsperaEnvio` por entrada de cola persistente = posible
> **hook aditivo** al worker (pendiente de decisión; hoy: pacing en memoria + backoff).

## Multiempresa / SaaS
- Config y **cadena hash por empresa** (aislamiento verificado por tests).
- Certificados (C3.5) se custodiarán cifrados por empresa (infra C1) con interfaz HSM.
- En escritorio: registro/firma local + envío diferido (cola). En SaaS: envío server-side.
