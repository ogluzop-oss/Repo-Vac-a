"""
FASE 4.6/4.7/4.8 — Internacionalización, estructura multipaís y autofacturación.

- 4.6 Internacional: divisa + tipo de cambio + importe en divisa/EUR + idioma del documento
  (reutiliza el sistema de divisas existente; no se duplica).
- 4.7 Multipaís: SOLO estructura (pais_fiscal / regimen_fiscal_pais / configuracion_iva_pais)
  para futuras fiscalidades (IVA UE / GST / Sales Tax / VAT). No implementa fiscalidad nueva.
- 4.8 Autofacturación: marca de factura emitida por tercero autorizado (auditada, sin alterar
  numeración).
"""

import datetime as _dt
import logging

logger = logging.getLogger("facturacion.internacional")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.facturacion.identidad_facturacion import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()


# ── 4.6 Internacional ────────────────────────────────────────────────────────
def aplicar_divisa(id_factura, divisa, tipo_cambio=None, idioma=None, id_empresa=None) -> bool:
    """Fija divisa/tipo de cambio/idioma de la factura y calcula importe_divisa/importe_eur."""
    id_empresa = _emp(id_empresa)
    from src.db import facturas_cliente as FC
    from src.db.conexion import obtener_conexion
    f = FC.obtener_factura(id_factura, id_empresa)
    if not f:
        return False
    total = float(f.get("total") or 0)
    tc = float(tipo_cambio) if tipo_cambio else 1.0
    importe_divisa = round(total, 2)
    importe_eur = round(total / tc, 2) if tc else total
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE facturas_cliente SET tipo_cambio=%s, fecha_tipo_cambio=%s, "
                        "importe_divisa=%s, importe_eur=%s, idioma=%s WHERE id_factura=%s "
                        "AND id_empresa=%s",
                        (tc, _dt.date.today().isoformat(), importe_divisa, importe_eur,
                         (idioma or None), id_factura, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("aplicar_divisa(%s): %s", id_factura, e); return False


# ── 4.8 Autofacturación ──────────────────────────────────────────────────────
def marcar_autofactura(id_factura, emisor_nif, emisor_nombre, usuario=None, id_empresa=None) -> bool:
    """Marca la factura como autofactura (emitida por tercero autorizado). Auditada; no toca
    la numeración."""
    id_empresa = _emp(id_empresa)
    from src.db import facturas_cliente as FC
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE facturas_cliente SET autofactura=1, emisor_tercero_nif=%s, "
                        "emisor_tercero_nombre=%s WHERE id_factura=%s AND id_empresa=%s",
                        (emisor_nif, emisor_nombre, id_factura, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
        if ok:
            FC.registrar_evento(id_factura, "AUTOFACTURA", detalle=f"{emisor_nombre} ({emisor_nif})",
                                usuario=usuario, id_empresa=id_empresa)
        return ok
    except Exception as e:
        logger.error("marcar_autofactura(%s): %s", id_factura, e); return False


# ── 4.7 Multipaís (estructura) ───────────────────────────────────────────────
def registrar_pais_fiscal(codigo, nombre=None, zona=None, sistema_impuesto="IVA", divisa=None) -> bool:
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pais_fiscal (codigo, nombre, zona, sistema_impuesto, divisa) "
                        "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), "
                        "zona=VALUES(zona), sistema_impuesto=VALUES(sistema_impuesto), divisa=VALUES(divisa)",
                        (codigo, nombre, zona, sistema_impuesto, divisa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("registrar_pais_fiscal: %s", e); return False


def registrar_iva_pais(pais, tipo, porcentaje, etiqueta=None) -> bool:
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO configuracion_iva_pais (pais, tipo, porcentaje, etiqueta) "
                        "VALUES (%s,%s,%s,%s)", (pais, tipo, round(float(porcentaje or 0), 2), etiqueta))
            conn.commit()
        return True
    except Exception as e:
        logger.error("registrar_iva_pais: %s", e); return False


def seed_minimo() -> None:
    """Carga una estructura mínima de países/zonas (idempotente). Estructura, no fiscalidad activa."""
    base = [("ES", "España", "UE", "IVA", "EUR"), ("FR", "Francia", "UE", "IVA", "EUR"),
            ("DE", "Alemania", "UE", "IVA", "EUR"), ("GB", "Reino Unido", "EXTRA_UE", "VAT", "GBP"),
            ("US", "Estados Unidos", "EXTRA_UE", "SALES_TAX", "USD"),
            ("CH", "Suiza", "EXTRA_UE", "VAT", "CHF"), ("AE", "EAU", "EXTRA_UE", "VAT", "AED"),
            ("MA", "Marruecos", "EXTRA_UE", "IVA", "MAD")]
    for c, n, z, s, d in base:
        registrar_pais_fiscal(c, n, z, s, d)
