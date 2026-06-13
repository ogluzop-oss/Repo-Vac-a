"""
Constructor ÚNICO del diccionario de datos del ticket de venta.

Lo usan tanto la venta en vivo (TPV) como la REIMPRESIÓN desde búsqueda, para no
duplicar la lógica de cabecera corporativa, IVA centralizado, configuración del
ticket, QR/código de barras y trazabilidad. Devuelve el dict que consume
``impresion.generar_ticket_pdf``.
"""

import hashlib
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LOGO_CORP_PATH = os.path.join(_ROOT, "documentos", "logo_corporativo.png")


def construir_datos_ticket(venta_id, fecha, id_caja, empleado, lineas, pago,
                           copia: bool = False, cliente: dict | None = None) -> dict:
    """Construye el dict de datos del ticket desde la fuente única corporativa.

    - `fecha`: datetime.
    - `lineas`: [{nombre, cantidad, precio, subtotal, descuento_pct,
      modo_venta?, peso?, precio_kg?}].
    - `pago`: {forma_pago, total, entregado?, cambio?, efectivo_neto?, tarjeta?}.
    - `cliente`: {nombre, nif} o None (cliente genérico).
    """
    from src.utils import divisas

    try:
        n_caja = int(str(id_caja).split("-")[-1])
    except Exception:
        n_caja = 1
    ticket_num = f"TCK-{fecha.strftime('%Y%m%d')}-{int(venta_id or 0):05d}"

    empresa, tienda, id_empresa = {}, {}, ""
    try:
        from src.db.empresa import empresa_actual_id, info_documento
        _i = info_documento()
        empresa = {
            "nombre": _i.get("nombre"), "nombre_comercial": _i.get("nombre_comercial"),
            "cif": _i.get("cif"), "direccion_completa": _i.get("direccion_completa"),
            "pais": _i.get("pais"), "telefono": _i.get("telefono"), "email": _i.get("email"),
        }
        tienda = {"nombre": _i.get("centro_nombre"), "codigo": _i.get("centro_codigo")}
        id_empresa = empresa_actual_id() or ""
    except Exception:
        pass

    try:
        from src.db.config_ticket import obtener_config_ticket
        cfg = obtener_config_ticket()
    except Exception:
        cfg = {}

    # IVA automático según el PAÍS FISCAL (fuente única; no toca precios).
    try:
        from src.utils import fiscalidad
        iva_rate = fiscalidad.iva_empresa()
    except Exception:
        iva_rate = 21.0

    items = [
        {"nombre": l.get("nombre"), "cantidad": l.get("cantidad", 1),
         "precio": l.get("precio", 0), "subtotal": l.get("subtotal", 0),
         "descuento_pct": l.get("descuento_pct", 0), "iva": iva_rate,
         "modo_venta": l.get("modo_venta"), "peso": l.get("peso"),
         "precio_kg": l.get("precio_kg"), "granel": l.get("modo_venta") == "PESO"}
        for l in lineas
    ]

    traza = f"{venta_id}|{fecha.isoformat()}|{pago.get('total', 0)}|{len(lineas)}"
    doc_hash = hashlib.sha256(traza.encode()).hexdigest()

    return {
        "logo": _LOGO_CORP_PATH if os.path.exists(_LOGO_CORP_PATH) else None,
        "empresa": empresa,
        "tienda": tienda,
        "cliente": cliente or None,
        "copia": copia,
        "operacion": {
            "ticket_num": ticket_num, "venta_id": venta_id,
            "caja": id_caja, "terminal": f"TPV-{n_caja:02d}",
            "empleado": empleado or "—",
            "fecha": fecha.strftime("%d/%m/%Y  %H:%M:%S"),
        },
        "items": items,
        "pago": {
            "forma_pago": pago.get("forma_pago", ""), "total": pago.get("total", 0),
            "entregado": pago.get("entregado"), "cambio": pago.get("cambio", 0.0),
            "efectivo": pago.get("efectivo_neto"), "tarjeta": pago.get("tarjeta"),
        },
        "moneda": divisas.divisa_actual(),
        "config": cfg,
        "hash": doc_hash,
        "qr": f"SMART|{ticket_num}|{fecha.strftime('%Y-%m-%d %H:%M')}|"
              f"{id_empresa}|{tienda.get('codigo') or ''}|{venta_id}|{pago.get('total', 0)}",
    }


def reimprimir_ticket(venta_id, regalo: bool = False) -> str | None:
    """Reconstruye y regenera el PDF de un ticket existente (marcado COPIA, o
    TICKET REGALO sin precios si regalo=True). Devuelve la ruta del PDF o None."""
    import datetime as _dt

    from src.db.ventas_busqueda import obtener_venta_completa
    from src.utils.impresion import generar_ticket_pdf

    v = obtener_venta_completa(venta_id)
    if not v:
        return None
    fecha = v.get("fecha")
    if isinstance(fecha, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                fecha = _dt.datetime.strptime(fecha[:19], fmt); break
            except ValueError:
                continue
    if not isinstance(fecha, _dt.datetime):
        fecha = _dt.datetime.now()

    lineas = [
        {"nombre": it.get("nombre"), "cantidad": it.get("cantidad", 1),
         "precio": float(it.get("precio_unitario", 0) or 0),
         "subtotal": float(it.get("subtotal", 0) or 0), "descuento_pct": 0}
        for it in v.get("items", [])
    ]
    n_caja = v.get("numero_caja") or 1
    pago = {"forma_pago": v.get("forma_pago", ""), "total": float(v.get("total", 0) or 0)}
    cliente = None
    if v.get("cliente_nombre"):
        cliente = {"id": v.get("cliente_id"), "nombre": v.get("cliente_nombre"),
                   "nif": v.get("cliente_nif")}
    datos = construir_datos_ticket(
        venta_id=v.get("id"), fecha=fecha, id_caja=f"CAJA-{int(n_caja):02d}",
        empleado=v.get("empleado") or "—", lineas=lineas, pago=pago,
        copia=not regalo, cliente=cliente)
    datos["regalo"] = regalo

    carpeta = os.path.join(_ROOT, "documentos", "tickets")
    os.makedirs(carpeta, exist_ok=True)
    pref = "REGALO" if regalo else "COPIA"
    ruta = os.path.join(carpeta, f"ticket_{pref}_{fecha.strftime('%Y%m%d_%H%M%S')}_{v.get('id')}.pdf")
    generar_ticket_pdf(datos, ruta)
    return ruta
