"""
Canal Web · Dominios · Registrador SIMULADO (por defecto, degradable).

Proveedor por defecto cuando no hay un registrador real conectado (patrón ya usado en email/pagos/
fiscal simulado). Permite que TODO el flujo (buscar / precio / comprar / DNS / HTTPS / publicar) sea
funcional y demostrable ahora; al conectar Cloudflare/Namecheap/Porkbun/OVH/IONOS/GoDaddy, la misma
arquitectura opera sin rediseño. NO realiza compras reales.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from src.services.comercio_digital.dominios.adaptador import (
    TLDS_DEFECTO, RegistrarAdapter, RegistrarContext,
)

# Precio determinista por TLD (simulado).
_PRECIOS = {".com": 11.99, ".es": 9.99, ".net": 12.99, ".shop": 24.99, ".store": 21.99,
            ".online": 19.99, ".tienda": 14.99}


def _slug(nombre: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", str(nombre or "empresa").lower()).strip("-")
    return s or "empresa"


class SimuladoRegistrar(RegistrarAdapter):
    codigo = "simulado"
    nombre = "Registrador simulado"

    def _disponible(self, dominio: str) -> bool:
        # Disponibilidad determinista (algunos dominios "ocupados" para ejercitar el flujo).
        h = int(hashlib.md5(dominio.encode()).hexdigest(), 16)
        return h % 5 != 0

    def buscar(self, nombre, *, tlds=None, contexto: RegistrarContext | None = None) -> list:
        base = _slug(nombre)
        out = []
        for tld in (tlds or TLDS_DEFECTO):
            dominio = f"{base}{tld}"
            out.append({"dominio": dominio, "tld": tld, "disponible": self._disponible(dominio),
                        "precio": _PRECIOS.get(tld, 15.99), "moneda": "EUR"})
        return out

    def precio(self, dominio, *, contexto: RegistrarContext | None = None) -> dict:
        tld = "." + dominio.rsplit(".", 1)[-1] if "." in dominio else ".com"
        p = _PRECIOS.get(tld, 15.99)
        return {"dominio": dominio, "precio": p, "renovacion": p, "moneda": "EUR"}

    def comprar(self, dominio, *, titular, contexto: RegistrarContext | None = None) -> dict:
        if not self._disponible(dominio):
            return {"ok": False, "dominio": dominio, "error": "no disponible"}
        ref = "SIM-" + hashlib.md5(dominio.encode()).hexdigest()[:12].upper()
        return {"ok": True, "dominio": dominio, "referencia": ref,
                "fecha_expiracion": (datetime.now() + timedelta(days=365)).isoformat(),
                "precio": self.precio(dominio)["precio"], "moneda": "EUR", "proveedor": self.codigo}

    def estado(self, dominio, *, contexto: RegistrarContext | None = None) -> dict:
        return {"dominio": dominio, "estado": "registrado",
                "fecha_expiracion": (datetime.now() + timedelta(days=365)).isoformat()}

    def renovar(self, dominio, *, contexto: RegistrarContext | None = None) -> dict:
        return {"ok": True, "dominio": dominio,
                "fecha_expiracion": (datetime.now() + timedelta(days=730)).isoformat()}

    def cancelar(self, dominio, *, contexto: RegistrarContext | None = None) -> dict:
        return {"ok": True, "dominio": dominio}

    def configurar_dns(self, dominio, registros, *, contexto: RegistrarContext | None = None) -> dict:
        # El simulado "aplica" los registros (sin red real).
        return {"ok": True, "aplicado": True, "registros": list(registros or [])}

    def activar_https(self, dominio, *, contexto: RegistrarContext | None = None) -> dict:
        return {"ok": True, "aplicado": True, "certificado": "simulado"}


__all__ = ["SimuladoRegistrar"]
