"""
Migracion 0107 — Enriquecimiento de TPV (Módulo 7). ADITIVA, idempotente, reversible.
Auditoría: promociones (descuento_pct/importe_fijo/2x1/pack/regalo), fidelización, devoluciones,
cierre Z con cadena hash, reservas/pedidos (ventas_comercial) y sesión/arqueo de caja YA existen.
Se añade solo lo ausente: aparcar/recuperar tickets en curso y arqueo por denominación (recuento
físico de billetes/monedas). Las promos escalonadas (nxm/segunda_unidad) se añaden en el evaluador
existente (db/promociones.py), sin nueva tabla. No duplica.
"""

VERSION = "0107"
DESCRIPCION = "TPV: tickets aparcados + arqueo por denominación"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("tpv_tickets_aparcados", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_tienda VARCHAR(40) DEFAULT NULL,
        caja INT DEFAULT 1,
        referencia VARCHAR(40) DEFAULT NULL,
        cliente VARCHAR(120) DEFAULT NULL,
        lineas MEDIUMTEXT DEFAULT NULL,
        total DECIMAL(12,2) DEFAULT 0,
        estado VARCHAR(20) NOT NULL DEFAULT 'APARCADO',
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        recuperado DATETIME DEFAULT NULL,
        INDEX idx_aparcado (id_empresa, id_tienda, estado)"""),
    ("tpv_arqueo_denominaciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_sesion INT DEFAULT NULL,
        valor_unidad DECIMAL(10,2) NOT NULL,
        tipo VARCHAR(10) NOT NULL DEFAULT 'billete',
        unidades INT NOT NULL DEFAULT 0,
        subtotal DECIMAL(12,2) NOT NULL DEFAULT 0,
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_arqueo_denom (id_sesion)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
