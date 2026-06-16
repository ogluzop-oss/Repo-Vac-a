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

## Multiempresa / SaaS
- Config y **cadena hash por empresa** (aislamiento verificado por tests).
- Certificados (C3.5) se custodiarán cifrados por empresa (infra C1) con interfaz HSM.
- En escritorio: registro/firma local + envío diferido (cola). En SaaS: envío server-side.

## Pendiente antes de C3.2 (auditoría del núcleo)
Encadenado hash (formato legal), estrategia de QR, modelo de evidencias,
compatibilidad Verifactu/Facturae, impacto en rendimiento/almacenamiento, y
estrategia offline/reenvíos. (Auditoría específica solicitada antes de implementar C3.2.)
