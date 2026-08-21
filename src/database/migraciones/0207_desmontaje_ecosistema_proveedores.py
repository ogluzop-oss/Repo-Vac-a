"""
Migración 0207 — Desmontaje del ecosistema OBSOLETO de Proveedores (portal externo + lonja + pagos
marketplace). Limpieza idempotente y reversible-nula (los datos efímeros se descartan por diseño).

Retira las tablas efímeras creadas por las migraciones 0198–0206 (excepto 0201 Cancelaciones, que es núcleo
permanente y se conserva) y las columnas que aquellas añadieron a tablas base:
- Portal de proveedor externo: portal_proveedor_cuentas, portal_pedido_estado, portal_proveedor_stock,
  portal_rfq, portal_rfq_ofertas, portal_mensajes.
- Lonja B2B / subastas: lonja_vendedores, lonja_listados, lonja_pujas, lonja_transacciones, lonja_tipos_cambio.
- Cobro del servicio / PSP / escrow: servicio_cobros, psp_cuentas_conectadas, pagos_eventos.
- Columnas efímeras en `proveedores` (IBAN cifrado del cobro del servicio, migr 0203).

NO toca el núcleo permanente (proveedores, compras_pedidos/recepciones/facturas, proveedor_precios_negociados,
compras_cancelaciones) ni el módulo genérico de correo/SMTP ni el storefront (portal_web / WEB-04).
"""

VERSION = "0207"
DESCRIPCION = "Desmontaje del portal externo + lonja + pagos marketplace (limpieza de tablas efímeras)"
REVERSIBLE = False
REQUIERE_BACKUP = True

_TABLAS_A_ELIMINAR = [
    # Lonja / subastas (hijas antes que padres, aunque son DROP directos)
    "lonja_pujas", "lonja_transacciones", "lonja_listados", "lonja_vendedores", "lonja_tipos_cambio",
    # Portal de proveedor externo
    "portal_rfq_ofertas", "portal_rfq", "portal_mensajes", "portal_pedido_estado",
    "portal_proveedor_stock", "portal_proveedor_cuentas",
    # Cobro del servicio / PSP / escrow
    "servicio_cobros", "psp_cuentas_conectadas", "pagos_eventos",
]

# Columnas efímeras del cobro del servicio en la tabla base `proveedores` (añadidas por 0203).
_COLS_PROVEEDORES = ("iban_cifrado", "iban_mascara", "titular_cuenta")


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for tabla in _TABLAS_A_ELIMINAR:
        cur.execute(f"DROP TABLE IF EXISTS {tabla}")
    for col in _COLS_PROVEEDORES:
        if _tiene_columna(cur, "proveedores", col):
            cur.execute(f"ALTER TABLE proveedores DROP COLUMN {col}")


def revertir(cur):
    # Desmontaje intencionado: no se recrean las estructuras efímeras. Las tablas base quedan intactas.
    pass
