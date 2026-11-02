"""
Migración 0313 — `documentos_logisticos_bultos` + `documentos_logisticos_bultos_lineas`. ADITIVA,
idempotente, reversible.

Recepción de mercancías (Logística): hasta ahora un palé solo podía recepcionarse ENTERO de una
vez (`db.logistica.procesar_recepcion_logistica`) — no existía ningún desglose por bulto/caja
dentro de un palé (confirmado por auditoría: "BULTO" era solo un token de ruido a ignorar al
escanear, nunca una entidad real). Se añade la posibilidad de recepcionar un palé bulto a bulto:
el operario, tras escanear el palé, puede declarar cuántos bultos lo componen — el sistema reparte
proporcionalmente la cantidad esperada de cada artículo entre esos bultos (editable línea a línea
en el momento de confirmar cada bulto, para absorber cualquier discrepancia real) — e imprime una
etiqueta con código de barras por bulto para pegarla físicamente y escanearla al recepcionarlo.

Mismo patrón que las tablas hermanas `documentos_logisticos_pales`/`_lineas` (ya existentes en
`bootstrap_mariadb.sql`): esta migración las replica para instalaciones YA provisionadas (el
bootstrap de un `.sql` nuevo ya las incluye directamente)."""

VERSION = "0313"
DESCRIPCION = "documentos_logisticos_bultos(_lineas) — recepción de palés bulto a bulto"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documentos_logisticos_bultos (
            id_bulto         VARCHAR(100) PRIMARY KEY,
            id_documento     VARCHAR(50)  NOT NULL,
            id_pale          VARCHAR(80)  NOT NULL,
            id_visual        VARCHAR(30)  NOT NULL,
            estado           VARCHAR(30)  NOT NULL DEFAULT 'PENDIENTE',
            usuario_receptor VARCHAR(100),
            fecha_recepcion  DATETIME NULL,
            creado_en        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY idx_dlb_documento (id_documento),
            KEY idx_dlb_pale (id_pale)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documentos_logisticos_bultos_lineas (
            id                BIGINT AUTO_INCREMENT PRIMARY KEY,
            id_bulto          VARCHAR(100) NOT NULL,
            codigo_articulo   VARCHAR(50)  NOT NULL,
            nombre_articulo   VARCHAR(255) NOT NULL,
            cantidad_enviada  INT NOT NULL DEFAULT 0,
            cantidad_recibida INT NULL,
            estado_linea      VARCHAR(30)  NOT NULL DEFAULT 'PENDIENTE',
            KEY idx_dlbl_bulto (id_bulto),
            KEY idx_dlbl_codigo (codigo_articulo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS documentos_logisticos_bultos_lineas")
    cur.execute("DROP TABLE IF EXISTS documentos_logisticos_bultos")
