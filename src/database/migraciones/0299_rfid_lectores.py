"""
Migración 0299 — Configuración de hardware RFID real (lector Zebra FX/RFD vía LLRP). ADITIVA,
reversible, idempotente.

Hasta ahora `LectorZebraGateway` se instanciaba SIEMPRE con `modo_simulado=True` hardcodeado en
`gui/ubicacion_tienda.py` — no existía ningún sitio donde guardar la IP/puerto de un lector físico.
`rfid_lectores` es esa configuración, UNA fila por (empresa, centro): mismo criterio de alcance que
`camaras` (migr. 0133) — `id_centro=''` es el comodín "config a nivel de empresa, válida para
cualquier centro sin una fila más específica propia" (evita el problema de NULL no siendo único en
una UNIQUE KEY compuesta).

Sin credenciales: a diferencia de `camaras.fuente_cifrada` (RTSP con usuario/contraseña en la URL),
una conexión LLRP estándar (puerto 5084) no lleva autenticación en el protocolo — no se añade una
columna de contraseña cifrada que nunca se usaría (si algún lector concreto exige una extensión de
vendor con credenciales, se añadirá cuando haga falta de verdad, no de forma especulativa).

`modo` ('simulado'|'fisico') es la fuente de verdad de si el gateway debe intentar LLRP real — el
resolutor (`services.rfid.hardware.resolver_gateway`) degrada a simulado de todas formas si `modo`
dice 'fisico' pero no hay `ip` guardada (nunca intenta conectar con una IP vacía).
"""

VERSION = "0299"
DESCRIPCION = "Configuración de hardware RFID real: tabla rfid_lectores (IP/puerto/modo por empresa+centro)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rfid_lectores (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  CHAR(36)     NOT NULL,
            id_centro   VARCHAR(64)  NOT NULL DEFAULT '',
            nombre      VARCHAR(120) NOT NULL DEFAULT 'Lector RFID',
            modo        VARCHAR(20)  NOT NULL DEFAULT 'simulado',
            ip          VARCHAR(45)  DEFAULT NULL,
            puerto      INT          NOT NULL DEFAULT 5084,
            activo      TINYINT(1)   NOT NULL DEFAULT 1,
            creado      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_rfid_lector_scope (id_empresa, id_centro),
            INDEX idx_rfid_lector_emp (id_empresa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS rfid_lectores")
