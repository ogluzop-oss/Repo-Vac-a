"""
Migración 0258 — Rappels acumulados / rebates de fin de año (Smart Suppliers B2B, Punto 1).
ADITIVA, idempotente (`CREATE TABLE IF NOT EXISTS`), reversible.

Dos tablas nuevas, ninguna existente se toca:
  - `rappel_tramos`: tramos de rebate retroactivo negociados por la empresa con un suministrador B2B
    concreto (umbral de gasto acumulado → % de rebate), con ventana de vigencia (`fecha_inicio`/
    `fecha_fin`, p.ej. el ejercicio fiscal o la vigencia del acuerdo).
  - `rappel_liquidaciones`: histórico de cada liquidación ya procesada para una ventana
    `(id_empresa, id_suministrador, fecha_inicio, fecha_fin)` — evita liquidar dos veces el mismo
    periodo. `UNIQUE KEY uq_rl_ventana` es la guardia de idempotencia REAL (a nivel de motor, no solo
    un SELECT previo en Python): `services.compras.b2b_rappels.liquidar_rappel` reclama la ventana
    insertando primero un registro "placeholder" en esta tabla — si dos llamadas concurrentes compiten
    por la misma ventana, la segunda falla con un error de clave duplicada antes de poder llamar dos
    veces a `db.compras.registrar_abono` (nunca hay doble abono por carrera).

Nomenclatura deliberadamente NO "rappel"/"escalones" a secas (ver docstring de
`services/compras/b2b_rappels.py`): existen ya `proveedores.condiciones_comerciales` (columna
`rappel` DECIMAL, plana e inerte, migración de proveedores, nunca usada en ningún cálculo) y
`b2b_catalogo_escalones` (descuentos por cantidad EN el pedido, concepto distinto). `rappel_tramos`/
`rappel_liquidaciones` son nombres compuestos explícitos para no colisionar con ninguno de los dos.

Tipos de columna alineados con el resto del ecosistema B2B (migraciones 0218/0221): `id_empresa
CHAR(36)` (mismo tipo que `transaccion_comercial.id_empresa`), `id_suministrador BIGINT` (mismo tipo
que `transaccion_comercial.id_suministrador`/`suministradores.id`).
"""

VERSION = "0258"
DESCRIPCION = ("Rappels B2B: rappel_tramos (tramos de rebate por umbral de gasto acumulado) + "
               "rappel_liquidaciones (histórico de liquidaciones, guardia de idempotencia)")
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("rappel_tramos", """
        id              INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa      CHAR(36)      NOT NULL,
        id_suministrador BIGINT       NOT NULL,
        umbral_desde    DECIMAL(14,2) NOT NULL,
        pct_rebate      DECIMAL(5,2)  NOT NULL,
        fecha_inicio    DATE          NOT NULL,
        fecha_fin       DATE          NOT NULL,
        estado          VARCHAR(20)   NOT NULL DEFAULT 'activo',
        creado_por      VARCHAR(150)  DEFAULT NULL,
        fecha_creacion  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_rt_empresa_sum (id_empresa, id_suministrador),
        INDEX idx_rt_estado (estado),
        INDEX idx_rt_vigencia (fecha_inicio, fecha_fin)"""),
    ("rappel_liquidaciones", """
        id                INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa        CHAR(36)      NOT NULL,
        id_suministrador  BIGINT        NOT NULL,
        fecha_inicio      DATE          NOT NULL,
        fecha_fin         DATE          NOT NULL,
        gasto_total       DECIMAL(14,2) NOT NULL DEFAULT 0,
        tramo_aplicado_id INT           DEFAULT NULL,
        pct_aplicado      DECIMAL(5,2)  NOT NULL DEFAULT 0,
        importe_rebate    DECIMAL(14,2) NOT NULL DEFAULT 0,
        id_factura_abono  INT           DEFAULT NULL,
        fecha_liquidacion DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_rl_ventana (id_empresa, id_suministrador, fecha_inicio, fecha_fin),
        INDEX idx_rl_empresa_sum (id_empresa, id_suministrador),
        CONSTRAINT fk_rl_tramo FOREIGN KEY (tramo_aplicado_id)
            REFERENCES rappel_tramos(id) ON DELETE SET NULL"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
