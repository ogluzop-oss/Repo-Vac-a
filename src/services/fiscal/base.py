"""
Interfaces del NÚCLEO FISCAL (C3.1) — contratos estables y neutros.

Cierran la arquitectura para que los proveedores reales (Verifactu, Facturae,
TicketBAI) y los adaptadores de envío/firma se enchufen SIN tocar el núcleo:

- `RegistroFiscal`  : modelo neutro de un registro de facturación encadenado.
- `Firmante`        : firma electrónica (impl local cifrada en C3.5; HSM futuro).
- `Emisor`          : envío a la hacienda/integrador (adaptadores en C3.3/C3.4).
- `ProveedorFiscal` : construye el registro (numeración, hash, QR, payload) según
                      el régimen/territorio. El `simulado` da una implementación
                      funcional para pruebas, sin lógica legal.
"""

from dataclasses import dataclass, field


@dataclass
class RegistroFiscal:
    """Modelo neutro de un registro de facturación (compartido por todos los
    regímenes). El formato/firma concretos los aporta cada proveedor."""
    tipo: str                       # ticket | factura | rectificativa | anulacion
    referencia: str | None = None   # venta_id / factura_id / pedido…
    total: float = 0.0
    serie: str | None = None
    id: int | None = None
    numero: int | None = None
    hash: str | None = None
    hash_anterior: str | None = None
    qr: str | None = None
    payload: dict = field(default_factory=dict)
    proveedor: str = "simulado"
    estado: str = "generado"        # generado | firmado | enviado | rechazado | anulado

    @classmethod
    def desde_fila(cls, d: dict) -> "RegistroFiscal":
        return cls(tipo=d.get("tipo"), referencia=d.get("referencia"),
                   total=float(d.get("total") or 0), serie=d.get("serie"),
                   id=d.get("id"), numero=d.get("numero"), hash=d.get("hash"),
                   hash_anterior=d.get("hash_anterior"), qr=d.get("qr"),
                   proveedor=d.get("proveedor", "simulado"),
                   estado=d.get("estado", "generado"))


class Firmante:
    """Firma electrónica de un registro/documento. Implementaciones: certificado
    local cifrado (C3.5) o HSM/servicio externo (futuro). Por defecto, no firma."""

    nombre = "ninguno"

    def disponible(self) -> bool:
        return False

    def firmar(self, datos: bytes) -> bytes | None:
        return None


class Emisor:
    """Envía un registro a la hacienda/integrador. Adaptadores enchufables
    (Verifactu/AEAT, Facturae/FACe, integradores). Por defecto, no envía."""

    nombre = "ninguno"

    def disponible(self) -> bool:
        return False

    def enviar(self, registro: RegistroFiscal, config: dict) -> dict:
        return {"ok": False, "estado": "pendiente", "mensaje": "Emisor no configurado."}


class ProveedorFiscal:
    """Contrato de un régimen fiscal. `registrar` construye y PERSISTE el registro
    (numeración + encadenado hash + QR + payload). `anular` genera el registro de
    anulación. La firma/envío reales se delegan en `Firmante`/`Emisor`."""

    nombre = "base"
    territorios = ()                 # territorios que cubre ("comun", "araba", …)

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def campos_hash(self, serie, numero, tipo, referencia, total) -> dict:
        """Conjunto de campos que entran en la HUELLA encadenada. Cada régimen lo
        define (Verifactu/TicketBAI fijan campos y orden legales); el conjunto
        neutro por defecto sirve al núcleo y al `simulado`."""
        return {"serie": serie, "numero": numero, "tipo": tipo,
                "referencia": referencia, "total": round(float(total or 0), 2)}

    def registrar(self, tipo: str, referencia=None, total=0.0, payload=None,
                  id_caja=None) -> RegistroFiscal:
        raise NotImplementedError

    def anular(self, registro: RegistroFiscal) -> RegistroFiscal:
        raise NotImplementedError
