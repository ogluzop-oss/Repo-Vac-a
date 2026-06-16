"""
Datos fiscales para el TICKET (C3.3.4) — QR de cotejo + leyenda legal.

`info_ticket` devuelve los elementos fiscales a imprimir SOLO si la empresa tiene
el módulo activo y en modo Verifactu; en cualquier otro caso devuelve None y el
ticket se imprime EXACTAMENTE igual que siempre (cero impacto en instalaciones
existentes). No genera nada: lee el registro ya creado por el hook de venta.
"""

import logging

logger = logging.getLogger("fiscal.ticket")


def info_ticket(referencia, id_empresa=None, tipo="ticket") -> dict | None:
    """{qr, leyenda, huella, csv, numserie} del registro fiscal de la venta, o None."""
    try:
        from src.db import fiscal as F
        cfg = F.obtener_config(id_empresa)
        if not cfg.get("activo") or cfg.get("proveedor") != "verifactu":
            return None
        reg = F.obtener_por_referencia(referencia, id_empresa=id_empresa, tipo=tipo)
        if not reg or not reg.get("qr"):
            return None
        from src.services.fiscal import verifactu_legal as legal
        return {
            "qr": reg.get("qr"),
            "leyenda": legal.LEYENDA,
            "huella": reg.get("hash"),
            "csv": reg.get("csv_aeat"),
            "numserie": legal.num_serie(reg.get("serie"), reg.get("numero")),
        }
    except Exception as e:
        logger.debug("info_ticket(%s): %s", referencia, e)
        return None
