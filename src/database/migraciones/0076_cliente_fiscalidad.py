"""
Migracion 0076 — Atributos fiscales del CLIENTE (FASE 3.1). ADITIVA, reversible, idempotente.

Convierte al cliente CRM en el ORIGEN ÚNICO de decisión fiscal de la factura (régimen IVA,
recargo de equivalencia, ISP, exención intracomunitaria, retención IRPF, condiciones de pago).
Reutiliza columnas ya existentes (nif_iva, es_intracomunitario, pais_fiscal de AEAT-6); aquí
solo se añaden las que faltan. Todas NULLABLE/con defecto neutro → no alteran clientes existentes
ni el CRM, y una factura sin estos datos se comporta EXACTAMENTE igual que hoy.
"""

VERSION = "0076"
DESCRIPCION = "Atributos fiscales del cliente (regimen, recargo, ISP, intracom, IRPF, cond. pago)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = [
    # régimen fiscal del cliente: general | recargo | exento | intracomunitario | extranjero | isp
    ("regimen_fiscal", "VARCHAR(20) NOT NULL DEFAULT 'general'"),
    # tipo de operación habitual: nacional | intracomunitaria | exportacion | isp
    ("tipo_operacion", "VARCHAR(20) DEFAULT NULL"),
    ("aplica_recargo_equivalencia", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("aplica_retencion_irpf", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("porcentaje_retencion", "DECIMAL(5,2) DEFAULT NULL"),
    # estado VIES: NULL | pendiente | valido | invalido (nif_iva ya existe y se reutiliza)
    ("validacion_vies", "VARCHAR(12) DEFAULT NULL"),
    ("es_extranjero", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("aplica_isp", "TINYINT(1) NOT NULL DEFAULT 0"),
    # condiciones de pago: contado | 15 | 30 | 60 | 30-60-90 ...
    ("condiciones_pago", "VARCHAR(40) DEFAULT NULL"),
]


def aplicar(cur):
    for nombre, definicion in _COLS:
        cur.execute(f"ALTER TABLE clientes ADD COLUMN IF NOT EXISTS {nombre} {definicion}")


def revertir(cur):
    for nombre, _ in reversed(_COLS):
        cur.execute(f"ALTER TABLE clientes DROP COLUMN IF EXISTS {nombre}")
