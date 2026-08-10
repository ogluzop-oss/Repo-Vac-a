"""
Mapeo de cuentas contables (E6.4) — parametrización evento/clave → cuenta.

Resuelve la cuenta a usar para cada concepto (ventas, IVA, formas de pago, compras,
terceros…), con valores POR DEFECTO (PGC) y override por empresa en `contab_mapeo`.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("contab.mapeo")

# Valores por defecto (clave "ambito" o "ambito:clave").
DEFAULTS = {
    "venta": "700", "iva_rep": "477", "cliente": "430",
    "compra": "600", "iva_sop": "472", "proveedor": "400",
    "devolucion_venta": "708", "devolucion_compra": "608",
    "merma": "659", "existencias": "300",
    "consumo_mp": "601",   # consumo de materia prima (obrador/producción) → Compras de materias primas
    "forma_pago:efectivo": "570", "forma_pago:tarjeta": "572",
    "forma_pago:transferencia": "572", "forma_pago:factura": "430",
    # Nómina (F4.5)
    "nomina_sueldos": "640", "nomina_ss_empresa": "642", "nomina_ss_acreedora": "476",
    "nomina_irpf": "4751", "nomina_liquido": "465",
}

# ── Gastos directos (suministros, servicios, dietas…) → cuenta de gasto PGC (grupo 62).
# Entrada de gasto de un clic: cada tipo ya sabe a qué cuenta va y si por defecto lleva IVA.
# (codigo, etiqueta, cuenta, lleva_iva_por_defecto)
TIPOS_GASTO = [
    ("luz",           "Luz / Electricidad",               "628", True),
    ("agua",          "Agua",                             "628", True),
    ("gas",           "Gas",                              "628", True),
    ("internet",      "Internet / Teléfono",              "629", True),
    ("alquiler",      "Alquiler / Arrendamiento",         "621", True),
    ("reparaciones",  "Reparaciones / Mantenimiento",     "622", True),
    ("transporte",    "Transporte / Mensajería",          "624", True),
    ("dietas",        "Dietas / Viajes",                  "629", True),
    ("profesionales", "Servicios profesionales",          "623", True),
    ("seguros",       "Seguros",                          "625", False),
    ("bancarios",     "Servicios / comisiones bancarias", "626", False),
    ("publicidad",    "Publicidad / Marketing",           "627", True),
    ("material",      "Material de oficina",              "629", True),
    ("otros",         "Otros gastos",                     "629", True),
]

# Nombres PGC de las cuentas de gasto (para autocrearlas si la empresa se activó antes).
CUENTAS_GASTO = {
    "621": "Arrendamientos y cánones", "622": "Reparaciones y conservación",
    "623": "Servicios de profesionales independientes", "624": "Transportes",
    "625": "Primas de seguros", "626": "Servicios bancarios y similares",
    "627": "Publicidad, propaganda y relaciones públicas", "628": "Suministros",
    "629": "Otros servicios",
}

# Registra el mapeo por defecto de cada tipo de gasto (clave "gasto:<codigo>").
DEFAULTS.update({f"gasto:{cod}": cta for cod, _et, cta, _iva in TIPOS_GASTO})


def _empresa(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.contabilidad.identidad_contabilidad import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        if id_empresa:
            return id_empresa
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return EMPRESA_DEFAULT_ID


def cuenta(ambito, clave="", id_empresa=None) -> str | None:
    """Cuenta para (ambito, clave): primero `contab_mapeo`, si no, DEFAULTS."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo_cuenta FROM contab_mapeo WHERE id_empresa=%s AND ambito=%s "
                        "AND clave=%s", (id_empresa, ambito, clave or ""))
            r = cur.fetchone()
            if r:
                return r[0] if not isinstance(r, dict) else r["codigo_cuenta"]
    except Exception as e:
        logger.debug("cuenta(%s,%s): %s", ambito, clave, e)
    return DEFAULTS.get(f"{ambito}:{clave}" if clave else ambito) or DEFAULTS.get(ambito)


def set_mapeo(ambito, codigo_cuenta, clave="", id_empresa=None) -> bool:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO contab_mapeo (id_empresa, ambito, clave, codigo_cuenta) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE codigo_cuenta=VALUES(codigo_cuenta)",
                        (id_empresa, ambito, clave or "", codigo_cuenta))
            conn.commit()
        return True
    except Exception as e:
        logger.error("set_mapeo(%s): %s", ambito, e)
        return False


def cuenta_forma_pago(forma_pago, id_empresa=None) -> str:
    fp = (forma_pago or "efectivo").strip().lower()
    return cuenta("forma_pago", fp, id_empresa) or "570"
