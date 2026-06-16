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

## Multiempresa / SaaS
- Config y **cadena hash por empresa** (aislamiento verificado por tests).
- Certificados (C3.5) se custodiarán cifrados por empresa (infra C1) con interfaz HSM.
- En escritorio: registro/firma local + envío diferido (cola). En SaaS: envío server-side.
