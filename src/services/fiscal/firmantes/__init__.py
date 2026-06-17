"""
Firmantes electrónicos para fiscalidad (C3.5.3).

`FirmanteXAdES` (signxml) firma documentos XML con XAdES; es REUTILIZABLE por:
- registros NO-VERIFACTU (firma de los registros de facturación), y
- Facturae (C3.4), que aportará su política de firma concreta (XAdES-EPES).

Usa el `ProveedorClaves` de la custodia (clave/cert en memoria), sin ficheros.
"""

from src.services.fiscal.firmantes.xades import FirmanteXAdES, politica_epes

__all__ = ["FirmanteXAdES", "politica_epes"]
