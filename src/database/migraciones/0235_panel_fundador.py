"""
Migración 0235 — Cuenta y sesiones del PANEL DEL FUNDADOR (proyecto de infraestructura SaaS
central — Fase 4, ver plan `hazy-riding-aurora`). Solo tienen sentido en la base de datos CENTRAL
(`src/backend_central/`), igual que las tablas de la migración 0234 — en una instalación local
quedan sin usar.

- `panel_fundador_admin`: UNA sola cuenta (la del fundador), sin relación con `usuarios` de ningún
  cliente. Se crea una vez mediante `src/backend_central/crear_fundador.py` (script de arranque, no
  hay alta desde la propia web — evita el problema del huevo y la gallina de un panel sin cuenta).
- `panel_fundador_sesiones`: mismo patrón sin-`secret_key` que `b2b_sesiones_empresa`/
  `proveedor_sesiones` (token opaco + expiración en BD), aquí entregado vía cookie HttpOnly en vez
  de la URL, porque es un login real de formulario, no un enlace de invitación.
"""

VERSION = "0235"
DESCRIPCION = "Cuenta y sesiones del panel web del fundador (servidor central)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("panel_fundador_admin", """
        id              INT AUTO_INCREMENT PRIMARY KEY,
        usuario         VARCHAR(80)  NOT NULL,
        password_hash   VARCHAR(255) NOT NULL,
        creado_en       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ultimo_acceso   DATETIME     NULL,
        UNIQUE KEY uq_panel_fundador_usuario (usuario)"""),
    ("panel_fundador_sesiones", """
        id              INT AUTO_INCREMENT PRIMARY KEY,
        token_sesion    VARCHAR(64)  NOT NULL,
        usuario         VARCHAR(80)  NOT NULL,
        creada_en       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expira          DATETIME     NOT NULL,
        UNIQUE KEY uq_panel_fundador_token (token_sesion)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
