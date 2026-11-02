"""
Datos fiscales para el TICKET (C3.3.4 / C3.4-TBAI) — QR de cotejo + leyenda legal.

`info_ticket` devuelve los elementos fiscales a imprimir SOLO si la empresa tiene
el módulo activo y un proveedor con QR legal (Verifactu o TicketBAI); en cualquier
otro caso devuelve None y el ticket se imprime EXACTAMENTE igual que siempre (cero
impacto en instalaciones existentes). No genera nada: lee el registro ya creado
por el hook de venta.

Verifactu y TicketBAI son MUTUAMENTE EXCLUSIVOS por factura: una empresa está en
régimen común (Verifactu/AEAT) o en territorio foral (TicketBAI/Diputación Foral),
nunca ambos — el `proveedor` configurado en `fiscal_config` decide cuál de los dos
badges/QR se muestra, reutilizando este MISMO camino de render (sin duplicar)."""

import logging

logger = logging.getLogger("fiscal.ticket")

_PROVEEDORES_CON_QR = ("verifactu", "ticketbai")


def info_ticket(referencia, id_empresa=None, tipo="ticket") -> dict | None:
    """{qr, leyenda, huella, csv, numserie} del registro fiscal de la venta, o None.
    `csv`/`numserie` quedan None para TicketBAI cuando no aplican (TicketBAI no usa
    CSV de acuse; su identificador visible va dentro de `numserie`)."""
    try:
        from src.db import fiscal as F
        cfg = F.obtener_config(id_empresa)
        proveedor = cfg.get("proveedor")
        if not cfg.get("activo") or proveedor not in _PROVEEDORES_CON_QR:
            return None
        reg = F.obtener_por_referencia(referencia, id_empresa=id_empresa, tipo=tipo)
        if not reg or not reg.get("qr"):
            return None
        if proveedor == "ticketbai":
            return _info_ticketbai(reg)
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


def _info_ticketbai(reg: dict) -> dict:
    """Variante TicketBAI de `info_ticket`: mismo dict shape, identificador TBAI
    (en vez de CSV) honesto — si el registro quedó sin certificado activo, el QR
    lleva el marcador `SIN-CERTIFICADO` (nunca un identificador inventado). El
    identificador visible vive DENTRO del QR (parámetro `id`, única fuente real
    de verdad — ver `ticketbai_legal.contenido_qr`), no en un campo aparte."""
    from src.services.fiscal import ticketbai_legal as legal
    qr = reg.get("qr") or ""
    ident = None
    if qr and not qr.startswith(legal.MARCADOR_SIN_CERTIFICADO):
        try:
            from urllib.parse import parse_qs, urlparse
            ident = (parse_qs(urlparse(qr).query).get("id") or [None])[0]
        except Exception:
            ident = None
    return {
        "qr": reg.get("qr"),
        "leyenda": legal.LEYENDA,
        "huella": reg.get("hash"),
        "csv": None,
        "numserie": ident or legal.num_factura(reg.get("serie"), reg.get("numero")),
    }
