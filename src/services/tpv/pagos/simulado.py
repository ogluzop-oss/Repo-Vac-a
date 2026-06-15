"""Pasarela simulada: no cobra de verdad, permite probar el flujo de extremo a
extremo (genera una referencia y un enlace local; verificar_pago devuelve 'pagado').
Útil en demo/desarrollo y como respaldo cuando no hay proveedor configurado."""

import logging
import uuid

from src.services.tpv.pagos.base import PasarelaPago
from src.services.tpv.pagos.registry import registrar

logger = logging.getLogger("pagos.simulado")


@registrar("simulado", "Simulado (pruebas)", orden=90)
class PasarelaSimulada(PasarelaPago):
    nombre = "simulado"

    def configurado(self) -> bool:
        return True

    def crear_cobro(self, pedido: dict) -> dict:
        ref = "SIM-" + uuid.uuid4().hex[:12]
        url = f"https://pago.simulado.local/checkout/{ref}"
        logger.info("[SIMULADO] Cobro creado %s por %.2f %s", ref,
                    float(pedido.get("total") or 0), self.moneda())
        return {"ok": True, "url": url, "referencia": ref, "estado": "pendiente",
                "mensaje": "(Modo simulado) Enlace de pago generado."}

    def verificar_pago(self, referencia: str) -> str:
        # En simulado damos el cobro por pagado para poder cerrar el flujo.
        return "pagado"
