"""
Migración 0281 — Smart Suppliers: reglas de pack/bundle definidas por el PROVEEDOR. ADITIVA,
idempotente, reversible.

`b2b_promo_bundles` es una forma de dato GENUINAMENTE distinta de `rappel_tramos` (migración 0258,
ver `services.compras.b2b_rappels`): un rappel es un umbral ÚNICO sobre el GASTO ACUMULADO de toda una
ventana temporal (empresa↔suministrador), liquidado retroactivamente; un bundle es un emparejamiento
de DOS artículos concretos del catálogo del proveedor (producto disparador A + cantidad mínima →
producto recompensa B + descuento), evaluado EN EL MOMENTO del carrito/pedido, sin ninguna noción de
gasto acumulado ni de liquidación posterior. Forzarlo dentro de `rappel_tramos` habría sido abuso de
esquema (esa tabla ni tiene columnas para un segundo artículo ni su `UNIQUE KEY`/liquidación tendrían
sentido aquí) — de ahí esta tabla nueva.

La recompensa admite DOS formas (`forma_recompensa`), ambas evaluadas por
`services.compras.b2b_bundles.calcular_descuento_bundle`:
  - 'pct_descuento': % de descuento sobre CADA unidad del artículo B ya presente en el carrito, una
    vez que el carrito reúne `cantidad_minima` unidades del artículo A — la forma explícitamente
    pedida ("compra N de A, obtén X% de descuento en B").
  - 'precio_pack_fijo': precio fijo para el conjunto (cantidad_minima de A + 1 de B) — variante bonus,
    calculada por "packs" completos (floor) cuando el carrito contiene múltiplos de ambos artículos.
Exactamente una de `pct_descuento`/`precio_pack_fijo` es NOT NULL según `forma_recompensa` (lo valida
el servicio, no una CHECK de MySQL/MariaDB por compatibilidad con versiones sin soporte real de CHECK).

`fecha_inicio`/`fecha_fin` + `activo` siguen la MISMA convención de ventana activa que `rappel_tramos`
(ver migración 0258) — reutilizada tal cual, sin reinventar otro criterio de vigencia.
"""

VERSION = "0281"
DESCRIPCION = "Smart Suppliers: reglas de pack/bundle definidas por el proveedor (producto A -> descuento en B)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("b2b_promo_bundles", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_suministrador BIGINT NOT NULL,
        nombre VARCHAR(120) NOT NULL,
        codigo_disparador VARCHAR(64) NOT NULL,
        cantidad_minima INT NOT NULL DEFAULT 1,
        codigo_recompensa VARCHAR(64) NOT NULL,
        forma_recompensa ENUM('pct_descuento','precio_pack_fijo') NOT NULL DEFAULT 'pct_descuento',
        pct_descuento DECIMAL(5,2) DEFAULT NULL,
        precio_pack_fijo DECIMAL(12,2) DEFAULT NULL,
        fecha_inicio DATE NOT NULL,
        fecha_fin DATE NOT NULL,
        activo TINYINT(1) NOT NULL DEFAULT 1,
        creado_por INT DEFAULT NULL,
        creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_b2bpb_disparador (id_suministrador, codigo_disparador, activo),
        INDEX idx_b2bpb_recompensa (id_suministrador, codigo_recompensa, activo)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
