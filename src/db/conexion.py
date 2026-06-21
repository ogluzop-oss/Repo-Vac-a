import csv
import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime

import pymysql
import pymysql.cursors
from dotenv import load_dotenv

# Pool de conexiones (A2.1). Si DBUtils no estuviera disponible, se degrada a
# conexión directa (comportamiento anterior) sin romper nada.
try:
    from dbutils.pooled_db import PooledDB
    _POOL_DISPONIBLE = True
except Exception:  # pragma: no cover
    PooledDB = None
    _POOL_DISPONIBLE = False

# Cargar variables de entorno
load_dotenv()

# --- Señales para la interfaz ---
try:
    from PyQt6.QtCore import QObject, pyqtSignal

    class StockSignals(QObject):
        stock_actualizado = pyqtSignal(str)
        propuestas_actualizadas = pyqtSignal()

    stock_signals = StockSignals()
except Exception:

    class StockSignals:
        def __init__(self):
            _dummy = type("Dummy", (), {"emit": lambda *a: None})()
            self.stock_actualizado = _dummy
            self.propuestas_actualizadas = _dummy

    stock_signals = StockSignals()

# Configuración de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("conexion_db")

# --- CONFIGURACIÓN DE MARIADB ---
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "admin123"),
    "database": os.getenv("DB_NAME", "smart_manager_db"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "autocommit": True,
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.Cursor,
}

# Configurar SSL si está disponible
ssl_config = {}
if os.getenv("DB_SSL_CA"):
    ssl_config["ca"] = os.getenv("DB_SSL_CA")
if os.getenv("DB_SSL_CERT"):
    ssl_config["cert"] = os.getenv("DB_SSL_CERT")
if os.getenv("DB_SSL_KEY"):
    ssl_config["key"] = os.getenv("DB_SSL_KEY")
if ssl_config:
    DB_CONFIG["ssl"] = ssl_config

BOOTSTRAP_SQL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "database", "bootstrap_mariadb.sql"
)


# ============================================================
# BLOQUE CONEXIÓN Y ARRANQUE DE BASE DE DATOS
# ============================================================


def _ejecutar_script_sql(cursor, ruta_script: str, nombre_db: str | None = None):
    """Ejecuta un script SQL simple separado por ';'.

    Si `nombre_db` difiere del nombre por defecto del bootstrap, sustituye el
    nombre de la base en `CREATE DATABASE`/`USE` para respetar `DB_NAME` (en
    producción coincide con 'smart_manager_db' → sin cambios; habilita BD de
    pruebas aisladas)."""
    if not os.path.exists(ruta_script):
        raise FileNotFoundError(f"No existe el script SQL: {ruta_script}")

    with open(ruta_script, encoding="utf-8") as f:
        contenido = f.read()

    if nombre_db and nombre_db != "smart_manager_db":
        contenido = contenido.replace("smart_manager_db", nombre_db)

    for sentencia in contenido.split(";"):
        sql = sentencia.strip()
        if sql:
            cursor.execute(sql)


def asegurar_base_de_datos():
    """Crea la base y sus tablas mínimas si aún no existen."""
    conn = None
    try:
        config_base = DB_CONFIG.copy()
        config_base.pop("database", None)
        conn = pymysql.connect(**config_base)
        with conn.cursor() as cur:
            _ejecutar_script_sql(cur, BOOTSTRAP_SQL_PATH, DB_CONFIG.get("database"))
        conn.commit()
        logger.info("Base de datos inicializada automáticamente desde bootstrap.")
    finally:
        if conn:
            conn.close()


# ── Pool de conexiones (A2.1) ────────────────────────────────────────────────
# Registro de pools POR CONFIGURACIÓN (host/puerto/BD/usuario). Hoy hay un único
# pool (BD activa); esta estructura deja preparado el pool-por-tenant del futuro
# SaaS (BD por tenant) sin cambiar la API pública `obtener_conexion()`.
_POOLS = {}


def _clave_pool(cfg) -> tuple:
    return (cfg.get("host"), cfg.get("port"), cfg.get("database"), cfg.get("user"))


def _crear_pool(cfg):
    return PooledDB(
        creator=pymysql,
        maxconnections=int(os.getenv("DB_POOL_MAX", "20")),
        mincached=0,                     # sin conexiones eager (BD podría no existir aún)
        maxcached=int(os.getenv("DB_POOL_CACHE", "10")),
        blocking=True,                   # espera si se alcanza el máximo (no peta)
        ping=1,                          # valida la conexión al sacarla del pool
        reset=True,                      # limpia estado al devolverla
        **cfg,
    )


def _obtener_pool(cfg):
    clave = _clave_pool(cfg)
    pool = _POOLS.get(clave)
    if pool is None:
        pool = _crear_pool(cfg)
        _POOLS[clave] = pool
    return pool


def _resetear_pool(cfg):
    _POOLS.pop(_clave_pool(cfg), None)


def _conectar(cfg):
    """Conexión del pool (o directa si DBUtils no está disponible)."""
    if _POOL_DISPONIBLE:
        return _obtener_pool(cfg).connection()
    return pymysql.connect(**cfg)


@contextmanager
def obtener_conexion(config=None):
    """Conexión a MariaDB tomada de un POOL (A2.1). La API es idéntica: al salir,
    la conexión se DEVUELVE al pool (no se cierra el socket). `config` opcional
    permite apuntar a otra BD/tenant (futuro SaaS); por defecto usa la activa."""
    cfg = config or DB_CONFIG
    conn = None
    try:
        try:
            conn = _conectar(cfg)
        except pymysql.err.OperationalError as e:
            codigo_error = e.args[0] if getattr(e, "args", None) else None
            if codigo_error == 1049:
                logger.warning(
                    "La base de datos no existe todavía. Se intentará crear automáticamente."
                )
                asegurar_base_de_datos()
                _resetear_pool(cfg)
                conn = _conectar(cfg)
            else:
                raise
        yield conn
    except Exception as e:
        logger.error(f"Error crítico de conexión a MariaDB: {e}")
        raise ConnectionError(f"No se pudo conectar a MariaDB: {e}")
    finally:
        if conn:
            conn.close()


@contextmanager
def transaccion(config=None):
    """Transacción REAL (A2.2): toma una conexión del pool con autocommit
    DESACTIVADO, hace COMMIT al salir correctamente y ROLLBACK ante cualquier
    excepción; restaura autocommit antes de devolverla al pool.

    Cede la CONEXIÓN (úsala con `with transaccion() as conn: with conn.cursor()...`).
    Pensada para operaciones multi-sentencia (ventas, stock, pedidos) y para que el
    `SELECT … FOR UPDATE` mantenga el bloqueo durante toda la operación. No llames a
    `conn.commit()` dentro: lo gestiona el context manager."""
    cfg = config or DB_CONFIG
    conn = _conectar(cfg)
    try:
        # `START TRANSACTION` abre una transacción explícita aunque la sesión esté
        # en autocommit, y la mantiene (con sus bloqueos FOR UPDATE) hasta COMMIT.
        # Es agnóstico del driver: no depende de `autocommit()` (que el wrapper del
        # pool no expone). commit()/rollback() sí son DB-API y los proxia el pool.
        with conn.cursor() as _c:
            _c.execute("START TRANSACTION")
        try:
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
    finally:
        conn.close()           # devuelve al pool


def init_db():
    """Inicialización centralizada al arranque.

    1) Garantiza el esquema base con `ensure_schema()` (idempotente, como siempre).
    2) Aplica las MIGRACIONES versionadas pendientes (C4): sella la baseline en
       instalaciones existentes y ejecuta las nuevas (0002+) con backup previo. Si
       el runner fallara, el esquema base ya quedó garantizado en el paso 1."""
    ok = ensure_schema()
    try:
        from src.db import migrador
        res = migrador.aplicar_pendientes()
        if res.get("error"):
            logger.error("Migraciones pendientes con error: %s", res["error"])
        elif res.get("aplicadas"):
            logger.info("Migraciones aplicadas: %s", res["aplicadas"])
    except Exception as e:
        logger.error("Runner de migraciones no disponible (%s); esquema base OK.", e)
    return ok


# ============================================================
# BLOQUE ESQUEMA Y MANTENIMIENTO DE BASE DE DATOS
# ============================================================


_schema_ready = False

# Identidad raíz multiempresa (multi-tenant). En esta fase la app sigue siendo de
# escritorio mono-empresa: todas las filas existentes pertenecen a esta empresa por
# defecto, así nada se rompe. Las nuevas empresas usarán UUID propios (uuid4).
EMPRESA_DEFAULT_ID = "00000000-0000-0000-0000-000000000001"
EMPRESA_DEFAULT_CODIGO = "EMP-001"


def ensure_schema(force: bool = False):
    """Asegura el esquema mínimo global, el de logística y el de stock.

    Idempotente a nivel de proceso: una vez verificado el esquema, las
    siguientes llamadas son no-op. Antes se reejecutaba el bootstrap completo
    (CREATE/ALTER + logística) en CADA consulta, lo que ralentizaba mucho la
    carga de pantallas con muchas consultas (p. ej. CONFIGURACIÓN). Usa
    force=True para forzar la re-verificación si fuera necesario."""
    global _schema_ready
    if _schema_ready and not force:
        return True
    try:
        asegurar_base_de_datos()
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                # Nueva tabla mostrar_stock solicitada
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS mostrar_stock (
                        codigo VARCHAR(50) PRIMARY KEY,
                        stock_lineal INT DEFAULT 0,
                        stock_almacen INT DEFAULT 0,
                        stock_almacen_central INT DEFAULT 0,
                        capacidad_lineal INT DEFAULT 0,
                        capacidad_almacen INT DEFAULT 0,
                        stock_total INT DEFAULT 0
                    )
                """)
                # Tabla para Configuración de Caja
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS caja_config (
                        id INT PRIMARY KEY,
                        fondo_caja_fuerte DOUBLE DEFAULT 0.0,
                        estado_caja ENUM('CERRADA', 'ABIERTA') DEFAULT 'CERRADA',
                        fecha_actualizacion DATETIME
                    )
                """)
                # Columnas de referencia tienda/almacén
                cur.execute("""
                    ALTER TABLE configuraciones
                    ADD COLUMN IF NOT EXISTS ref_tienda  VARCHAR(100) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS ref_almacen VARCHAR(100) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS moneda      VARCHAR(3)   NOT NULL DEFAULT 'EUR'
                """)

                # ── Fundación MULTIEMPRESA (multi-tenant), aditiva y no disruptiva ──
                # Entidad raíz 'empresas' + enlace de tiendas/usuarios/config a la
                # empresa. Todo lo existente queda bajo la empresa por defecto, así
                # las consultas actuales (sin filtro) siguen devolviendo lo mismo.
                _emp = EMPRESA_DEFAULT_ID
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS empresas (
                        id_empresa          CHAR(36)     NOT NULL PRIMARY KEY,
                        codigo_empresa      VARCHAR(20)  NOT NULL UNIQUE,
                        nombre_empresa      VARCHAR(255) NOT NULL DEFAULT 'SMART MANAGER',
                        razon_social        VARCHAR(255)          DEFAULT NULL,
                        cif_nif             VARCHAR(50)           DEFAULT NULL,
                        direccion_fiscal    VARCHAR(255)          DEFAULT NULL,
                        telefono            VARCHAR(50)           DEFAULT NULL,
                        email_principal     VARCHAR(255)          DEFAULT NULL,
                        estado              VARCHAR(20)  NOT NULL DEFAULT 'activa',
                        plan_licencia       VARCHAR(50)  NOT NULL DEFAULT 'base',
                        fecha_alta          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        fecha_actualizacion DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute(f"""
                    ALTER TABLE tiendas
                    ADD COLUMN IF NOT EXISTS id_empresa          CHAR(36)    NOT NULL DEFAULT '{_emp}',
                    ADD COLUMN IF NOT EXISTS codigo_tienda       VARCHAR(20) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS fecha_alta          DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS fecha_actualizacion DATETIME    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                """)
                cur.execute(f"""
                    ALTER TABLE usuarios
                    ADD COLUMN IF NOT EXISTS id_empresa CHAR(36) NOT NULL DEFAULT '{_emp}'
                """)
                # Seguridad de acceso (C1.3): bloqueo por intentos + último acceso.
                cur.execute("""
                    ALTER TABLE usuarios
                    ADD COLUMN IF NOT EXISTS intentos_fallidos INT NOT NULL DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS bloqueado_hasta DATETIME DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS ultimo_login DATETIME DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS must_change_password TINYINT(1) NOT NULL DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS email VARCHAR(255) DEFAULT NULL
                """)
                # Identidad por USUARIO ÚNICO POR EMPRESA (C1.4): el nombre deja de
                # ser único global y pasa a serlo dentro de cada empresa (SaaS).
                try:
                    cur.execute("ALTER TABLE usuarios DROP INDEX IF EXISTS nombre")
                except Exception:
                    pass
                try:
                    cur.execute("ALTER TABLE usuarios "
                                "ADD UNIQUE KEY IF NOT EXISTS uq_usuario_empresa (id_empresa, nombre)")
                except Exception:
                    pass
                # Sesiones / refresh tokens (diseño para la futura API REST).
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS sesiones (
                        id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_usuario    INT          NOT NULL,
                        id_empresa    CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        jti           CHAR(36)     NOT NULL,
                        refresh_hash  VARCHAR(255)          DEFAULT NULL,
                        emitido       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        expira        DATETIME              DEFAULT NULL,
                        revocado      TINYINT(1)   NOT NULL DEFAULT 0,
                        UNIQUE KEY uq_sesion_jti (jti),
                        INDEX idx_sesion_usuario (id_usuario)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                # Identidades externas (OIDC: Google/Microsoft/Apple) — diseño.
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS identidades_externas (
                        id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_usuario    INT          NOT NULL,
                        id_empresa    CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        proveedor     VARCHAR(30)  NOT NULL,
                        sub_externo   VARCHAR(255) NOT NULL,
                        email         VARCHAR(255)          DEFAULT NULL,
                        fecha_alta    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY uq_idext (proveedor, sub_externo),
                        INDEX idx_idext_usuario (id_usuario)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute(f"""
                    ALTER TABLE configuraciones
                    ADD COLUMN IF NOT EXISTS id_empresa CHAR(36) NOT NULL DEFAULT '{_emp}'
                """)
                # Siembra de la empresa por defecto (a partir de configuraciones si existe).
                cur.execute(f"""
                    INSERT IGNORE INTO empresas (id_empresa, codigo_empresa, nombre_empresa, email_principal)
                    SELECT '{_emp}', '{EMPRESA_DEFAULT_CODIGO}',
                           COALESCE(NULLIF(nombre_empresa,''), 'SMART MANAGER'),
                           COALESCE(NULLIF(email,''), NULL)
                    FROM configuraciones ORDER BY id ASC LIMIT 1
                """)
                cur.execute(f"""
                    INSERT IGNORE INTO empresas (id_empresa, codigo_empresa, nombre_empresa)
                    VALUES ('{_emp}', '{EMPRESA_DEFAULT_CODIGO}', 'SMART MANAGER')
                """)
                # Backfill de filas existentes hacia la empresa por defecto + códigos visibles.
                cur.execute(f"UPDATE tiendas SET id_empresa='{_emp}' WHERE id_empresa IS NULL OR id_empresa=''")
                cur.execute("UPDATE tiendas SET codigo_tienda=CONCAT('TND-', LPAD(id,3,'0')) WHERE codigo_tienda IS NULL OR codigo_tienda=''")
                cur.execute(f"UPDATE usuarios SET id_empresa='{_emp}' WHERE id_empresa IS NULL OR id_empresa=''")
                cur.execute(f"UPDATE configuraciones SET id_empresa='{_emp}' WHERE id_empresa IS NULL OR id_empresa=''")

                # ── FASE 2: DATOS CORPORATIVOS (fuente única reutilizable) ──
                # Ampliación de 'empresas' con todos los campos necesarios para
                # generar documentos (contratos, facturas, certificados...) +
                # tablas independientes de representantes legales y centros de
                # trabajo. Todo aditivo (ADD COLUMN IF NOT EXISTS) y por id_empresa.
                cur.execute("""
                    ALTER TABLE empresas
                    ADD COLUMN IF NOT EXISTS nombre_comercial    VARCHAR(255) DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS municipio           VARCHAR(120) DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS provincia           VARCHAR(120) DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS comunidad_autonoma  VARCHAR(120) DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS cp                  VARCHAR(10)  DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS pais                VARCHAR(80)  DEFAULT 'ESPAÑA',
                    ADD COLUMN IF NOT EXISTS regimen_ss          VARCHAR(20)  DEFAULT '0111',
                    ADD COLUMN IF NOT EXISTS ccc                 VARCHAR(50)  DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS cnae                VARCHAR(20)  DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS actividad_economica VARCHAR(255) DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS convenio_colectivo  VARCHAR(255) DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS cod_pais            VARCHAR(10)  DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS cod_provincia       VARCHAR(10)  DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS cod_municipio       VARCHAR(15)  DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS cod_actividad       VARCHAR(15)  DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS pais_fiscal         VARCHAR(2)   DEFAULT 'ES'
                """)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS representantes_legales (
                        id_representante CHAR(36)     NOT NULL PRIMARY KEY,
                        id_empresa       CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        nombre           VARCHAR(120)          DEFAULT NULL,
                        apellidos        VARCHAR(180)          DEFAULT NULL,
                        dni_nie          VARCHAR(50)           DEFAULT NULL,
                        cargo            VARCHAR(120)          DEFAULT 'REPRESENTANTE LEGAL',
                        telefono         VARCHAR(50)           DEFAULT NULL,
                        email            VARCHAR(255)          DEFAULT NULL,
                        es_principal     TINYINT      NOT NULL DEFAULT 0,
                        estado           VARCHAR(20)  NOT NULL DEFAULT 'activo',
                        fecha_alta       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_rep_empresa (id_empresa)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS centros_trabajo (
                        id_centro                CHAR(36)     NOT NULL PRIMARY KEY,
                        id_empresa               CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        id_tienda                INT                   DEFAULT NULL,
                        codigo_centro            VARCHAR(20)           DEFAULT NULL,
                        nombre_centro            VARCHAR(255)          DEFAULT NULL,
                        direccion                VARCHAR(255)          DEFAULT NULL,
                        codigo_postal            VARCHAR(10)           DEFAULT NULL,
                        municipio                VARCHAR(120)          DEFAULT NULL,
                        provincia                VARCHAR(120)          DEFAULT NULL,
                        comunidad_autonoma       VARCHAR(120)          DEFAULT NULL,
                        pais                     VARCHAR(80)  NOT NULL DEFAULT 'ESPAÑA',
                        telefono                 VARCHAR(50)           DEFAULT NULL,
                        email                    VARCHAR(255)          DEFAULT NULL,
                        codigo_cuenta_cotizacion VARCHAR(50)           DEFAULT NULL,
                        codigo_centro_trabajo    VARCHAR(50)           DEFAULT NULL,
                        actividad_economica      VARCHAR(255)          DEFAULT NULL,
                        cod_pais                 VARCHAR(10)           DEFAULT NULL,
                        cod_municipio            VARCHAR(15)           DEFAULT NULL,
                        cod_actividad            VARCHAR(15)           DEFAULT NULL,
                        es_principal             TINYINT      NOT NULL DEFAULT 0,
                        estado                   VARCHAR(20)  NOT NULL DEFAULT 'activo',
                        fecha_alta               DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_centro_empresa (id_empresa),
                        INDEX idx_centro_tienda (id_tienda)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                # Códigos oficiales en centros existentes (aditivo).
                cur.execute("""
                    ALTER TABLE centros_trabajo
                    ADD COLUMN IF NOT EXISTS cod_pais      VARCHAR(10) DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS cod_municipio VARCHAR(15) DEFAULT NULL,
                    ADD COLUMN IF NOT EXISTS cod_actividad VARCHAR(15) DEFAULT NULL
                """)

                # ── RENDIMIENTO diario por tienda (ediciones manuales que
                # sobreescriben los valores auto-calculados de TPV/autocobro/horarios) ──
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS rendimiento_diario (
                        id           INT AUTO_INCREMENT PRIMARY KEY,
                        id_empresa   CHAR(36)      NOT NULL DEFAULT '{_emp}',
                        fecha        DATE          NOT NULL,
                        facturacion  DECIMAL(12,2)          DEFAULT NULL,
                        clientes     INT                    DEFAULT NULL,
                        horas        DECIMAL(8,2)           DEFAULT NULL,
                        prevision    DECIMAL(12,2)          DEFAULT NULL,
                        fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        UNIQUE KEY uq_rend_emp_fecha (id_empresa, fecha)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute("ALTER TABLE rendimiento_diario "
                            "ADD COLUMN IF NOT EXISTS prevision DECIMAL(12,2) DEFAULT NULL")

                # Migración: en BBDD antiguas `ventas.codigo` se creó NOT NULL (modelo
                # de venta de un solo artículo). El modelo actual usa venta_items, así
                # que el INSERT del TPV/autocobro no aporta `codigo` → error 1364. Se
                # vuelve nullable con default para que esas ventas se registren.
                try:
                    cur.execute("ALTER TABLE ventas MODIFY codigo VARCHAR(50) NULL DEFAULT NULL")
                    cur.execute("ALTER TABLE ventas MODIFY cantidad INT NULL DEFAULT 0")
                except Exception as _e:
                    logger.warning("No se pudo migrar ventas.codigo/cantidad a NULL: %s", _e)

                # Tipo de IVA por artículo (para el desglose fiscal del ticket).
                try:
                    cur.execute("ALTER TABLE articulos "
                                "ADD COLUMN IF NOT EXISTS iva DECIMAL(5,2) NOT NULL DEFAULT 21.00")
                except Exception as _e:
                    logger.warning("No se pudo añadir articulos.iva: %s", _e)

                # CLIENTES (captura en el flujo de venta del TPV; multiempresa).
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS clientes (
                        id          INT AUTO_INCREMENT PRIMARY KEY,
                        nombre      VARCHAR(150) NOT NULL,
                        nif         VARCHAR(20)           DEFAULT NULL,
                        telefono    VARCHAR(30)           DEFAULT NULL,
                        email       VARCHAR(150)          DEFAULT NULL,
                        direccion   VARCHAR(255)          DEFAULT NULL,
                        id_empresa  CHAR(36)     NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
                        estado      VARCHAR(20)  NOT NULL DEFAULT 'activo',
                        fecha_alta  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        KEY idx_cli_nombre (nombre),
                        KEY idx_cli_nif (nif)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                # Cliente asociado a la venta (denormalizado para ticket/búsqueda).
                try:
                    cur.execute(
                        "ALTER TABLE ventas "
                        "ADD COLUMN IF NOT EXISTS cliente_id INT DEFAULT NULL, "
                        "ADD COLUMN IF NOT EXISTS cliente_nombre VARCHAR(150) DEFAULT NULL, "
                        "ADD COLUMN IF NOT EXISTS cliente_nif VARCHAR(20) DEFAULT NULL")
                except Exception as _e:
                    logger.warning("No se pudo añadir ventas.cliente_*: %s", _e)

                # Configuración del ticket por empresa (texto legal, mensaje de
                # despedida y plazo de devolución). Fuente única para el generador.
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS config_ticket (
                        id_empresa        CHAR(36)     NOT NULL PRIMARY KEY,
                        texto_legal       TEXT                  DEFAULT NULL,
                        mensaje_despedida VARCHAR(255)          DEFAULT NULL,
                        devol_dias        INT          NOT NULL DEFAULT 30,
                        fecha_actualizacion DATETIME   DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

                # ── CENTRO DOCUMENTAL UNIFICADO (registro, no almacén) ──
                # Índice único de TODOS los documentos generados por el sistema
                # (tickets, facturas, albaranes, contratos, informes, Excel...).
                # No guarda el binario: referencia la ruta del PDF/fichero ya
                # generado en documentos/. Multi-tenant (id_empresa/id_tienda) y
                # con metadatos para búsqueda (cliente, trabajador, importe, hash).
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS documentos_registro (
                        id_documento     CHAR(36)     NOT NULL PRIMARY KEY,
                        id_empresa       CHAR(36)     NOT NULL,
                        id_tienda        INT                   DEFAULT NULL,
                        id_usuario       INT                   DEFAULT NULL,
                        tipo_documento   VARCHAR(40)  NOT NULL DEFAULT 'otros',
                        nombre           VARCHAR(255) NOT NULL DEFAULT '',
                        referencia       VARCHAR(120)          DEFAULT NULL,
                        ruta             VARCHAR(500) NOT NULL DEFAULT '',
                        hash_documental  VARCHAR(64)           DEFAULT NULL,
                        cliente          VARCHAR(255)          DEFAULT NULL,
                        trabajador       VARCHAR(255)          DEFAULT NULL,
                        importe          DECIMAL(12,2)         DEFAULT NULL,
                        estado           VARCHAR(30)  NOT NULL DEFAULT 'generado',
                        fecha_generacion DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_doc_empresa (id_empresa),
                        INDEX idx_doc_tipo (tipo_documento),
                        INDEX idx_doc_ref (referencia),
                        INDEX idx_doc_hash (hash_documental),
                        UNIQUE KEY uq_doc_ruta (ruta)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

                # ── VENTA ONLINE desde TPV (F2) — infraestructura neutra ──
                # Pedido online generado desde una tienda (artículo sin stock local,
                # envío desde almacén central, etc.). Cuenta para el trabajador y la
                # tienda origen. Preparado para conectar Shopify/WooCommerce/
                # PrestaShop/web propia vía capa de servicio (plataforma +
                # referencia_externa); NO acoplado a ninguna plataforma.
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS pedidos_online (
                        id_pedido          CHAR(36)     NOT NULL PRIMARY KEY,
                        id_empresa         CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        id_tienda          INT                   DEFAULT NULL,
                        id_usuario         INT                   DEFAULT NULL,
                        trabajador         VARCHAR(255)          DEFAULT NULL,
                        cliente_id         INT                   DEFAULT NULL,
                        cliente_nombre     VARCHAR(255)          DEFAULT NULL,
                        cliente_telefono   VARCHAR(50)           DEFAULT NULL,
                        cliente_email      VARCHAR(255)          DEFAULT NULL,
                        direccion_envio    VARCHAR(500)          DEFAULT NULL,
                        total              DECIMAL(12,2) NOT NULL DEFAULT 0,
                        estado             VARCHAR(20)  NOT NULL DEFAULT 'PENDIENTE',
                        plataforma         VARCHAR(30)  NOT NULL DEFAULT 'interno',
                        referencia_externa VARCHAR(120)          DEFAULT NULL,
                        observaciones      TEXT                  DEFAULT NULL,
                        fecha              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        fecha_actualizacion DATETIME    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        INDEX idx_po_empresa (id_empresa),
                        INDEX idx_po_tienda (id_tienda),
                        INDEX idx_po_estado (estado)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                # Control idempotente de descuento de stock del canal online:
                # se descuenta al confirmar el pago y se repone si se cancela.
                cur.execute(
                    "ALTER TABLE pedidos_online "
                    "ADD COLUMN IF NOT EXISTS stock_descontado TINYINT(1) NOT NULL DEFAULT 0, "
                    "ADD COLUMN IF NOT EXISTS transportista VARCHAR(120) DEFAULT NULL, "
                    "ADD COLUMN IF NOT EXISTS seguimiento   VARCHAR(120) DEFAULT NULL, "
                    "ADD COLUMN IF NOT EXISTS fecha_envio   DATETIME     DEFAULT NULL, "
                    "ADD COLUMN IF NOT EXISTS referencia_pago VARCHAR(160) DEFAULT NULL, "
                    "ADD COLUMN IF NOT EXISTS enlace_pago     VARCHAR(600) DEFAULT NULL, "
                    "ADD COLUMN IF NOT EXISTS estado_pago     VARCHAR(20)  DEFAULT NULL")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pedidos_online_items (
                        id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_pedido       CHAR(36)     NOT NULL,
                        codigo_articulo VARCHAR(50)           DEFAULT NULL,
                        nombre          VARCHAR(255)          DEFAULT NULL,
                        cantidad        INT          NOT NULL DEFAULT 1,
                        precio_unitario DECIMAL(12,2) NOT NULL DEFAULT 0,
                        subtotal        DECIMAL(12,2) NOT NULL DEFAULT 0,
                        origen_stock    VARCHAR(20)  NOT NULL DEFAULT 'central',
                        INDEX idx_poi_pedido (id_pedido)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                # Configuración de e-commerce por empresa (plataforma + URL + creds)
                # para el adaptador multiplataforma (Shopify/Woo/Presta/web propia).
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS ecommerce_config (
                        id_empresa  CHAR(36)     NOT NULL PRIMARY KEY,
                        plataforma  VARCHAR(30)  NOT NULL DEFAULT 'web',
                        base_url    VARCHAR(500)          DEFAULT NULL,
                        api_key     VARCHAR(255)          DEFAULT NULL,
                        api_secret  VARCHAR(255)          DEFAULT NULL,
                        estado      VARCHAR(20)  NOT NULL DEFAULT 'activo',
                        fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                # Configuración de la PASARELA DE PAGO por empresa (Stripe/PayPal/
                # Redsys/simulado). Credenciales por proveedor + modo test/live.
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS pasarela_config (
                        id_empresa  CHAR(36)     NOT NULL PRIMARY KEY,
                        proveedor   VARCHAR(30)  NOT NULL DEFAULT 'redsys',
                        api_key     VARCHAR(255)          DEFAULT NULL,
                        api_secret  VARCHAR(255)          DEFAULT NULL,
                        comercio    VARCHAR(120)          DEFAULT NULL,
                        modo        VARCHAR(10)  NOT NULL DEFAULT 'test',
                        moneda      VARCHAR(3)   NOT NULL DEFAULT 'EUR',
                        estado      VARCHAR(20)  NOT NULL DEFAULT 'activo',
                        fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                # Secreto de firma de WEBHOOKS (distinto de la API key; p. ej. el
                # 'whsec_…' de Stripe). Confirmación automática del pago (Fase 3).
                cur.execute(
                    "ALTER TABLE pasarela_config "
                    "ADD COLUMN IF NOT EXISTS webhook_secret VARCHAR(255) DEFAULT NULL")
                # Registro de WEBHOOKS de pago: idempotencia/anti-duplicado y
                # trazabilidad. UNIQUE(empresa,proveedor,evento) evita reprocesar.
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS pagos_webhooks_log (
                        id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_empresa  CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        proveedor   VARCHAR(30)  NOT NULL,
                        evento_id   VARCHAR(180) NOT NULL,
                        evento_tipo VARCHAR(80)           DEFAULT NULL,
                        referencia  VARCHAR(180)          DEFAULT NULL,
                        id_pedido   CHAR(36)              DEFAULT NULL,
                        estado      VARCHAR(20)           DEFAULT NULL,
                        resultado   VARCHAR(20)  NOT NULL DEFAULT 'procesado',
                        ip_origen   VARCHAR(60)           DEFAULT NULL,
                        recibido    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY uq_wh_evento (id_empresa, proveedor, evento_id),
                        INDEX idx_wh_pedido (id_pedido), INDEX idx_wh_ref (referencia)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

                # Config de la WEB PROPIA (Escenario B): tienda online generada a
                # partir del catálogo. Una fila por empresa (marca/tema/dominio).
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS web_config (
                        id_empresa  CHAR(36)     NOT NULL PRIMARY KEY,
                        activa      TINYINT(1)   NOT NULL DEFAULT 0,
                        nombre      VARCHAR(150)          DEFAULT NULL,
                        descripcion TEXT                  DEFAULT NULL,
                        color       VARCHAR(10)  NOT NULL DEFAULT '#00FFC6',
                        logo_url    VARCHAR(500)          DEFAULT NULL,
                        moneda      VARCHAR(3)   NOT NULL DEFAULT 'EUR',
                        dominio     VARCHAR(255)          DEFAULT NULL,
                        fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

                # ══ CATÁLOGO ONLINE (Fase 2 — omnicanal) ═══════════════════════
                # Capa de presentación/web SOBRE `articulos` (no duplica el maestro):
                # cada producto de catálogo referencia articulos.codigo (única fuente
                # de stock/precio) y añade datos web. Todo por id_empresa/id_tienda
                # (id_tienda NULL = visible para toda la empresa).
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS catalogo_categorias (
                        id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_empresa  CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        id_tienda   INT                   DEFAULT NULL,
                        parent_id   BIGINT                DEFAULT NULL,
                        nombre      VARCHAR(150) NOT NULL,
                        slug        VARCHAR(180)          DEFAULT NULL,
                        descripcion TEXT                  DEFAULT NULL,
                        imagen      VARCHAR(500)          DEFAULT NULL,
                        orden       INT          NOT NULL DEFAULT 0,
                        visible     TINYINT(1)   NOT NULL DEFAULT 1,
                        fecha_alta  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_cat_emp (id_empresa), INDEX idx_cat_parent (parent_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS catalogo_marcas (
                        id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_empresa  CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        nombre      VARCHAR(150) NOT NULL,
                        slug        VARCHAR(180)          DEFAULT NULL,
                        logo        VARCHAR(500)          DEFAULT NULL,
                        descripcion TEXT                  DEFAULT NULL,
                        visible     TINYINT(1)   NOT NULL DEFAULT 1,
                        fecha_alta  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_marca_emp (id_empresa)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS catalogo_etiquetas (
                        id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_empresa  CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        nombre      VARCHAR(120) NOT NULL,
                        slug        VARCHAR(150)          DEFAULT NULL,
                        INDEX idx_etq_emp (id_empresa)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS catalogo_productos (
                        id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_empresa      CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        id_tienda       INT                   DEFAULT NULL,
                        codigo_articulo VARCHAR(50)  NOT NULL,
                        id_categoria    BIGINT                DEFAULT NULL,
                        id_marca        BIGINT                DEFAULT NULL,
                        slug            VARCHAR(220)          DEFAULT NULL,
                        titulo_web      VARCHAR(255)          DEFAULT NULL,
                        descripcion_web TEXT                  DEFAULT NULL,
                        destacado       TINYINT(1)   NOT NULL DEFAULT 0,
                        recomendado     TINYINT(1)   NOT NULL DEFAULT 0,
                        visible_web     TINYINT(1)   NOT NULL DEFAULT 1,
                        orden           INT          NOT NULL DEFAULT 0,
                        seo_title       VARCHAR(255)          DEFAULT NULL,
                        seo_descripcion VARCHAR(500)          DEFAULT NULL,
                        fecha_alta      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        fecha_actualizacion DATETIME  DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        UNIQUE KEY uq_prod_emp_art (id_empresa, codigo_articulo),
                        INDEX idx_prod_cat (id_categoria), INDEX idx_prod_marca (id_marca),
                        INDEX idx_prod_emp (id_empresa)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS catalogo_imagenes (
                        id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_empresa  CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        id_producto BIGINT       NOT NULL,
                        url         VARCHAR(600) NOT NULL,
                        alt         VARCHAR(255)          DEFAULT NULL,
                        orden       INT          NOT NULL DEFAULT 0,
                        es_portada  TINYINT(1)   NOT NULL DEFAULT 0,
                        INDEX idx_img_prod (id_producto)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS catalogo_atributos (
                        id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_empresa  CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        nombre      VARCHAR(120) NOT NULL,
                        tipo        VARCHAR(30)  NOT NULL DEFAULT 'texto',
                        INDEX idx_attr_emp (id_empresa)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS catalogo_producto_atributos (
                        id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_empresa  CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        id_producto BIGINT       NOT NULL,
                        id_atributo BIGINT                DEFAULT NULL,
                        nombre      VARCHAR(120)          DEFAULT NULL,
                        valor       VARCHAR(255)          DEFAULT NULL,
                        INDEX idx_pattr_prod (id_producto)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS catalogo_variantes (
                        id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_empresa      CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        id_producto     BIGINT       NOT NULL,
                        codigo_articulo VARCHAR(50)           DEFAULT NULL,
                        sku             VARCHAR(80)           DEFAULT NULL,
                        nombre          VARCHAR(180)          DEFAULT NULL,
                        precio_dif      DECIMAL(10,2) NOT NULL DEFAULT 0,
                        atributos       TEXT                  DEFAULT NULL,
                        orden           INT          NOT NULL DEFAULT 0,
                        visible         TINYINT(1)   NOT NULL DEFAULT 1,
                        INDEX idx_var_prod (id_producto)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS catalogo_producto_etiquetas (
                        id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_empresa  CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        id_producto BIGINT       NOT NULL,
                        id_etiqueta BIGINT       NOT NULL,
                        UNIQUE KEY uq_prod_etq (id_producto, id_etiqueta),
                        INDEX idx_petq_prod (id_producto), INDEX idx_petq_etq (id_etiqueta)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS catalogo_relacionados (
                        id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_empresa      CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        id_producto     BIGINT       NOT NULL,
                        id_producto_rel BIGINT       NOT NULL,
                        tipo            VARCHAR(20)  NOT NULL DEFAULT 'relacionado',
                        UNIQUE KEY uq_rel (id_producto, id_producto_rel, tipo),
                        INDEX idx_rel_prod (id_producto)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                # Reservas de stock del canal online (TPV: reservar / solicitar a
                # otra tienda) sin afectar al flujo normal del TPV.
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS catalogo_reservas (
                        id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        id_empresa      CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        id_tienda       INT                   DEFAULT NULL,
                        id_tienda_origen INT                  DEFAULT NULL,
                        codigo_articulo VARCHAR(50)  NOT NULL,
                        cantidad        INT          NOT NULL DEFAULT 1,
                        cliente         VARCHAR(255)          DEFAULT NULL,
                        trabajador      VARCHAR(255)          DEFAULT NULL,
                        tipo            VARCHAR(20)  NOT NULL DEFAULT 'reserva',
                        estado          VARCHAR(20)  NOT NULL DEFAULT 'activa',
                        observaciones   VARCHAR(500)          DEFAULT NULL,
                        caduca          DATETIME              DEFAULT NULL,
                        fecha           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_res_emp (id_empresa), INDEX idx_res_tienda (id_tienda),
                        INDEX idx_res_estado (estado)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

                # ── Módulo de CORREO CORPORATIVO (multi-tenant, multi-buzón) ──
                # Identidad: empresa → tienda → correo. El correo es un SERVICIO
                # asociado, nunca la clave principal. Preparado para licenciamiento
                # (SaaS) y OAuth 2.0 (tokens cifrados, NUNCA contraseñas).
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS licencias_correo (
                        id_licencia          CHAR(36)     NOT NULL PRIMARY KEY,
                        id_empresa           CHAR(36)     NOT NULL,
                        id_tienda            INT                   DEFAULT NULL,
                        id_usuario           INT                   DEFAULT NULL,
                        tipo_licencia        VARCHAR(30)  NOT NULL DEFAULT 'correo_tienda',
                        estado               VARCHAR(20)  NOT NULL DEFAULT 'activa',
                        numero_buzon         VARCHAR(50)           DEFAULT NULL,
                        limite_almacenamiento INT         NOT NULL DEFAULT 5120,
                        fecha_alta           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        fecha_baja           DATETIME              DEFAULT NULL,
                        observaciones        TEXT                  DEFAULT NULL,
                        fecha_actualizacion  DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        INDEX idx_lic_empresa (id_empresa)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS correos_corporativos (
                        id_correo            CHAR(36)     NOT NULL PRIMARY KEY,
                        id_empresa           CHAR(36)     NOT NULL,
                        id_tienda            INT                   DEFAULT NULL,
                        id_usuario           INT                   DEFAULT NULL,
                        direccion            VARCHAR(255) NOT NULL,
                        proveedor            VARCHAR(30)  NOT NULL DEFAULT 'simulado',
                        tipo                 VARCHAR(30)  NOT NULL DEFAULT 'general',
                        estado               VARCHAR(20)  NOT NULL DEFAULT 'activo',
                        id_licencia          CHAR(36)              DEFAULT NULL,
                        ultima_sincronizacion DATETIME             DEFAULT NULL,
                        observaciones        TEXT                  DEFAULT NULL,
                        fecha_alta           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        fecha_actualizacion  DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        UNIQUE KEY uq_correo_empresa (id_empresa, direccion),
                        INDEX idx_correo_empresa (id_empresa),
                        INDEX idx_correo_tienda (id_tienda)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS oauth_tokens (
                        id_token             CHAR(36)     NOT NULL PRIMARY KEY,
                        id_correo            CHAR(36)     NOT NULL,
                        proveedor            VARCHAR(30)  NOT NULL,
                        access_token_cifrado  TEXT                 DEFAULT NULL,
                        refresh_token_cifrado TEXT                 DEFAULT NULL,
                        scope                VARCHAR(500)          DEFAULT NULL,
                        expira_en            DATETIME              DEFAULT NULL,
                        fecha_actualizacion  DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        UNIQUE KEY uq_token_correo (id_correo)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

                # Artículos BANEADOS para devolución (no admiten devolución por
                # política de empresa, p. ej. ropa interior). Multi-tenant.
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS devoluciones_baneados (
                        id          INT AUTO_INCREMENT PRIMARY KEY,
                        id_empresa  CHAR(36)     NOT NULL DEFAULT '{_emp}',
                        codigo      VARCHAR(100) NOT NULL,
                        nombre      VARCHAR(255)          DEFAULT NULL,
                        motivo      VARCHAR(500)          DEFAULT NULL,
                        usuario     VARCHAR(100)          DEFAULT NULL,
                        fecha       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY uq_ban_empresa (id_empresa, codigo),
                        INDEX idx_ban_empresa (id_empresa)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

                # ── Fase 0b: id_empresa (+id_tienda) en las TABLAS OPERATIVAS ──
                # Aditivo y no disruptivo: ADD COLUMN ... DEFAULT rellena las filas
                # existentes con la empresa por defecto, así las consultas actuales
                # (sin filtro) siguen devolviendo lo mismo. Prepara el scoping por
                # tenant que activaremos módulo a módulo (Punto 3).
                _tablas_op = (
                    "articulos", "ventas", "venta_items", "ventas_errores",
                    "facturacion_diaria_log", "prevision_historico", "prevision_objetivos",
                    "documentos_logisticos", "documentos_logisticos_pales",
                    "documentos_logisticos_lineas", "recepciones_logisticas",
                    "incidencias_logisticas", "movimientos_stock", "configuracion_mapa",
                    "ubicaciones", "etiquetas", "mermas", "pedidos", "fichajes",
                    "reab_config", "reab_propuestas", "reab_schedule", "auditoria_logs",
                    "productos_granel", "devoluciones", "devolucion_items",
                    "mostrar_stock", "caja_config",
                )
                for _t in _tablas_op:
                    try:
                        cur.execute(
                            f"ALTER TABLE {_t} ADD COLUMN IF NOT EXISTS "
                            f"id_empresa CHAR(36) NOT NULL DEFAULT '{_emp}'"
                        )
                    except Exception as _e:
                        logger.warning("Fase 0b: id_empresa en %s: %s", _t, _e)
                # id_tienda (NULL = aún no asignada) en las tablas por-tienda.
                _tablas_tienda = (
                    "ventas", "mermas", "movimientos_stock", "recepciones_logisticas",
                    "documentos_logisticos", "pedidos", "etiquetas", "fichajes",
                    "devoluciones", "auditoria_logs", "productos_granel",
                )
                for _t in _tablas_tienda:
                    try:
                        cur.execute(
                            f"ALTER TABLE {_t} ADD COLUMN IF NOT EXISTS id_tienda INT DEFAULT NULL"
                        )
                    except Exception as _e:
                        logger.warning("Fase 0b: id_tienda en %s: %s", _t, _e)

                # ── Fase 3b.1: aislamiento por tienda — base de datos (aditivo) ──
                # 1) Backfill: el histórico se creó sin tienda (id_tienda NULL).
                #    Lo asignamos a la TIENDA POR DEFECTO (la de menor id de la
                #    empresa por defecto) para poder filtrar por tienda sin ocultar
                #    datos antiguos. Idempotente (solo filas NULL).
                cur.execute(f"SELECT MIN(id) FROM tiendas WHERE id_empresa='{_emp}'")
                _row_td = cur.fetchone()
                _tienda_def = None
                if _row_td:
                    _tienda_def = _row_td[0] if not isinstance(_row_td, dict) else list(_row_td.values())[0]
                if _tienda_def:
                    for _t in (*_tablas_tienda, "documentos_registro"):
                        try:
                            cur.execute(
                                f"UPDATE {_t} SET id_tienda=%s WHERE id_tienda IS NULL",
                                (_tienda_def,))
                        except Exception as _e:
                            logger.warning("3b.1 backfill id_tienda en %s: %s", _t, _e)

                # 2) Stock POR TIENDA (aislamiento real de existencias). Clave por
                #    (id_tienda, codigo_articulo). No sustituye aún a articulos.* —
                #    el wiring de lecturas/escrituras llega en el siguiente paso.
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS stock_tienda (
                        id_empresa          CHAR(36)    NOT NULL DEFAULT '{_emp}',
                        id_tienda           INT         NOT NULL,
                        codigo_articulo     VARCHAR(50) NOT NULL,
                        stock               INT         NOT NULL DEFAULT 0,
                        fecha_actualizacion DATETIME    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        PRIMARY KEY (id_tienda, codigo_articulo),
                        INDEX idx_st_empresa (id_empresa),
                        INDEX idx_st_articulo (codigo_articulo)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                # Migración inicial: vuelca el stock actual de articulos a la tienda
                # por defecto SOLO si la tabla está vacía (idempotente; no pisa datos
                # reales una vez poblada).
                if _tienda_def:
                    cur.execute("SELECT COUNT(*) FROM stock_tienda")
                    _r = cur.fetchone()
                    _n_st = (_r[0] if not isinstance(_r, dict) else list(_r.values())[0]) if _r else 0
                    if not _n_st:
                        try:
                            cur.execute(
                                "INSERT INTO stock_tienda (id_empresa, id_tienda, codigo_articulo, stock) "
                                "SELECT id_empresa, %s, codigo, COALESCE(Stock_tienda,0) FROM articulos "
                                "WHERE codigo IS NOT NULL AND codigo<>''",
                                (_tienda_def,))
                        except Exception as _e:
                            logger.warning("3b.1 migración stock_tienda: %s", _e)

                # ── Entidad ALMACÉN adaptada al modelo multiempresa (aditivo) ──
                # Cada almacén pertenece a una empresa y tiene código/tipo/estado.
                # Se mantiene el PK INT existente (compatibilidad con el código que
                # consulta `almacen`), igual que en `tiendas`.
                try:
                    cur.execute(f"""
                        ALTER TABLE almacen
                        ADD COLUMN IF NOT EXISTS id_empresa     CHAR(36)    NOT NULL DEFAULT '{_emp}',
                        ADD COLUMN IF NOT EXISTS codigo_almacen VARCHAR(20) NOT NULL DEFAULT '',
                        ADD COLUMN IF NOT EXISTS tipo_almacen   VARCHAR(30) NOT NULL DEFAULT 'central',
                        ADD COLUMN IF NOT EXISTS estado         VARCHAR(20) NOT NULL DEFAULT 'activo',
                        ADD COLUMN IF NOT EXISTS fecha_creacion DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
                    """)
                    cur.execute("UPDATE almacen SET codigo_almacen=CONCAT('ALM-', LPAD(id,3,'0')) WHERE codigo_almacen IS NULL OR codigo_almacen=''")
                    cur.execute("UPDATE almacen SET tipo_almacen='central' WHERE UPPER(nombre) LIKE '%CENTRAL%'")
                except Exception as _e:
                    logger.warning("Almacén multiempresa: %s", _e)

                # Relaciones de movimiento preparadas (NULL = aún no asignadas).
                # Permiten en el futuro: id_empresa → id_almacen_origen → id_almacen_destino.
                _alm_od = ("movimientos_stock", "documentos_logisticos", "recepciones_logisticas")
                for _t in _alm_od:
                    try:
                        cur.execute(f"ALTER TABLE {_t} ADD COLUMN IF NOT EXISTS id_almacen_origen INT DEFAULT NULL")
                        cur.execute(f"ALTER TABLE {_t} ADD COLUMN IF NOT EXISTS id_almacen_destino INT DEFAULT NULL")
                    except Exception as _e:
                        logger.warning("Almacén orig/dest en %s: %s", _t, _e)
                # Almacén destino preparado en reabastecimiento y pedidos.
                for _t in ("reab_propuestas", "pedidos"):
                    try:
                        cur.execute(f"ALTER TABLE {_t} ADD COLUMN IF NOT EXISTS id_almacen INT DEFAULT NULL")
                    except Exception as _e:
                        logger.warning("Almacén en %s: %s", _t, _e)
                conn.commit()

        from src.db.logistica import ensure_schema_logistica

        ensure_schema_logistica()
        logger.info("Esquema global, logístico y de stock verificado.")
        # Cifrado en reposo: migra secretos en claro existentes (idempotente).
        for _mod in ("pagos", "ecommerce"):
            try:
                import importlib
                getattr(importlib.import_module(f"src.db.{_mod}"), "migrar_cifrado")()
            except Exception as _e:
                logger.debug("migrar_cifrado(%s): %s", _mod, _e)
        _schema_ready = True
        return True
    except Exception as e:
        logger.error(f"Error crítico en ensure_schema: {e}")
        return False


def _aplicar_parches(cur):
    """Mantenimiento interno de columnas faltantes."""
    parches = {
        "configuraciones": [
            ("moneda", "VARCHAR(3) NOT NULL DEFAULT 'EUR'"),
        ],
        "articulos": [
            ("estado", "VARCHAR(20) DEFAULT 'activo'"),
            ("Stock_esperado", "INT DEFAULT 0"),
        ],
        "documentos_logisticos": [
            ("fecha_recepcion", "DATETIME NULL"),
            ("usuario_receptor", "VARCHAR(100)"),
        ],
    }
    for tabla, cols in parches.items():
        for col_nombre, definicion in cols:
            cur.execute(
                """
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
            """,
                (tabla, col_nombre),
            )
            if not cur.fetchone():
                cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col_nombre} {definicion}")
                logger.info(f"Columna {col_nombre} añadida a {tabla}.")


def tabla_existe(nombre_tabla: str) -> bool:
    """Comprueba si existe una tabla en la BD MariaDB."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT TABLE_NAME 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_SCHEMA = DATABASE() 
                    AND TABLE_NAME = %s
                """
                cur.execute(query, (nombre_tabla,))
                return bool(cur.fetchone())
    except Exception:
        logger.exception(f"Error comprobando si existe la tabla {nombre_tabla}")
        return False


# ============================================================
# BLOQUE UTILIDADES Y CONFIGURACIÓN
# ============================================================


def _fila_a_dict(cursor, fila):
    if fila is None:
        return None
    if isinstance(fila, dict):
        return fila
    columnas = [desc[0] for desc in (cursor.description or [])]
    return dict(zip(columnas, fila, strict=False))


def _filas_a_dicts(cursor, filas):
    if not filas:
        return []
    if isinstance(filas[0], dict):
        return list(filas)
    columnas = [desc[0] for desc in (cursor.description or [])]
    return [dict(zip(columnas, fila, strict=False)) for fila in filas]


def formatear_nombre_centro(nombre: str) -> str:
    """Normaliza nombres de centros a códigos de 4 caracteres (ej. 'Almacén Central' -> 'ALMC')."""
    if not nombre:
        return "DESC"
    n = nombre.upper().strip()

    if any(x in n for x in ["CENTRAL", "ALMC", "LOGÍSTICO", "WAREHOUSE"]):
        return "ALMC"

    nums = re.findall(r"\d+", n)
    if nums:
        prefix = "A" if "ALMACEN" in n or "ALM" in n else "T"
        return f"{prefix}{nums[0].zfill(3)}"[:4]

    return n.replace(" ", "")[:4]


def obtener_configuracion():
    """Recupera configuración global con aliases compatibles."""
    defaults = {
        "nombre_empresa": "SMART MANAGER",
        "codigo_local": "ALMC",
        "tienda_codigo": "ALMC",
        "email": "info@smartmanagerai.local",
        "moneda": "EUR",
    }

    try:
        ensure_schema()
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, nombre_empresa, codigo_local, email, moneda
                    FROM configuraciones
                    ORDER BY id ASC
                    LIMIT 1
                    """)
                fila = _fila_a_dict(cur, cur.fetchone())
                if not fila:
                    return defaults.copy()

                config = defaults.copy()
                config.update(fila)
                config["codigo_local"] = str(
                    config.get("codigo_local") or defaults["codigo_local"]
                ).strip()
                config["tienda_codigo"] = config["codigo_local"]
                config["nombre_empresa"] = str(
                    config.get("nombre_empresa") or defaults["nombre_empresa"]
                ).strip()
                config["email"] = str(config.get("email") or defaults["email"]).strip()
                config["moneda"] = str(
                    config.get("moneda") or defaults["moneda"]
                ).strip().upper()
                return config
    except Exception as e:
        logger.error(f"Error en obtener_configuracion: {e}")
        return defaults.copy()


def obtener_referencias() -> dict:
    """Devuelve {'ref_tienda': str, 'ref_almacen': str} desde configuraciones."""
    try:
        ensure_schema()
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT ref_tienda, ref_almacen FROM configuraciones ORDER BY id ASC LIMIT 1")
                fila = cur.fetchone()
                if fila:
                    return {"ref_tienda": fila[0] or "", "ref_almacen": fila[1] or ""}
    except Exception as e:
        logger.error(f"Error en obtener_referencias: {e}")
    return {"ref_tienda": "", "ref_almacen": ""}


def guardar_referencia(tipo: str, valor: str) -> bool:
    """Guarda la referencia de tienda ('tienda') o almacén ('almacen') en configuraciones."""
    col = "ref_tienda" if tipo == "tienda" else "ref_almacen"
    try:
        ensure_schema()
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE configuraciones SET {col} = %s ORDER BY id ASC LIMIT 1", (valor.strip(),))
                conn.commit()
                return True
    except Exception as e:
        logger.error(f"Error en guardar_referencia: {e}")
        return False


# ============================================================
# BLOQUE GESTIÓN DE ARTÍCULOS Y STOCK
# ============================================================


def obtener_articulo(codigo: str):
    """Recupera un artículo completo por su código."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                # Fetch all columns to return a complete article dictionary
                cur.execute(
                    "SELECT * FROM articulos WHERE codigo = %s",
                    (codigo,),
                )

                return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error(f"Error obtener_articulo ({codigo}): {e}")
        return None


def listar_stock() -> list[dict]:
    """Lista artículos con sus diferentes stocks de MariaDB."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT a.codigo, a.nombre, 
                           COALESCE(a.Stock_central, 0) AS Stock_central,
                           COALESCE(a.Stock_total, 0) AS Stock_total,
                           COALESCE(a.Stock_tienda, 0) AS Stock_tienda,
                           COALESCE(a.Stock_esperado, 0) AS Stock_esperado
                    FROM articulos a
                """)
                return cur.fetchall()
    except Exception:
        logger.exception("Error en listar_stock")
        return []


def articulos_bajo_stock() -> list[dict]:
    """Devuelve artículos con stock tienda < esperado."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT codigo, nombre, 
                           COALESCE(Stock_total, 0) AS Stock_total, 
                           COALESCE(Stock_tienda, 0) AS Stock_tienda, 
                           COALESCE(Stock_esperado, 0) AS Stock_esperado
                    FROM articulos
                    WHERE COALESCE(Stock_tienda, 0) < COALESCE(Stock_esperado, 0)
                    ORDER BY nombre ASC
                """)
                return cur.fetchall()
    except Exception:
        logger.exception("Error en articulos_bajo_stock")
        return []


def modificar_stock_completo(
    codigo: str, stock_central: int, stock_total: int, stock_tienda: int
) -> bool:
    """Actualiza los niveles de stock y notifica a la UI."""
    try:
        anterior = None
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(Stock_total,0)+COALESCE(Stock_tienda,0) "
                            "FROM articulos WHERE codigo=%s", (codigo,))
                _r = cur.fetchone()
                if _r:
                    anterior = (_r[0] if not isinstance(_r, dict) else list(_r.values())[0])
                cur.execute(
                    """
                    UPDATE articulos
                    SET Stock_central = %s, Stock_total = %s, Stock_tienda = %s
                    WHERE codigo = %s
                    """,
                    (stock_central, stock_total, stock_tienda, codigo),
                )
            conn.commit()
        stock_signals.stock_actualizado.emit(str(codigo))
        # INV.1: kárdex AJUSTE (best-effort) con stock anterior/nuevo/diferencia.
        try:
            from src.db import kardex
            nuevo = int((stock_total or 0) + (stock_tienda or 0))
            kardex.registrar_movimiento(
                codigo, "AJUSTE", (nuevo - int(anterior or 0)),
                origen="AJUSTE_MANUAL", stock_anterior=anterior, stock_nuevo=nuevo,
                observaciones="Corrección manual de stock")
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error(f"Error al modificar stock de {codigo}: {e}")
        return False


def _salida_stock_clamp(cur, codigo, cantidad, contexto="venta", id_empresa=None) -> int:
    """M4 — Política ÚNICA de salida de stock de sala (TPV): descuento atómico que NUNCA
    deja stock negativo (clamp a 0) y NUNCA es silencioso: si hay faltante, registra un
    aviso en `ventas_errores` (misma transacción que la venta). Devuelve el faltante."""
    cantidad = int(cantidad or 0)
    if not codigo or cantidad <= 0:
        return 0
    cur.execute("SELECT COALESCE(Stock_tienda,0) FROM articulos WHERE codigo=%s", (codigo,))
    r = cur.fetchone()
    disp = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else 0
    faltante = max(0, cantidad - disp)
    cur.execute("UPDATE articulos SET Stock_tienda = IF(COALESCE(Stock_tienda,0)-%s<0, 0, "
                "COALESCE(Stock_tienda,0)-%s) WHERE codigo=%s", (cantidad, cantidad, codigo))
    if faltante > 0:
        try:
            from src.db.empresa import empresa_actual_id
            emp = id_empresa or empresa_actual_id()
        except Exception:
            emp = id_empresa
        try:
            cur.execute("INSERT INTO ventas_errores (codigo, cantidad, fecha, motivo, id_empresa) "
                        "VALUES (%s,%s,NOW(),%s,%s)",
                        (str(codigo), faltante, f"sobreventa:{contexto} (faltante {faltante})", emp))
        except Exception:
            pass
    return faltante


def descontar_stock(codigo: str, cantidad: int) -> tuple[bool, int, int]:
    """
    Descuenta stock con bloqueo de fila (FOR UPDATE) para evitar condiciones de carrera.
    Prioriza Stock_central/total y luego Tienda.
    """
    for intento in range(3):  # Reintentos en caso de Deadlock
        try:
            # A2.2: dentro de una TRANSACCIÓN real → el FOR UPDATE mantiene el
            # bloqueo de fila hasta el commit (evita sobreventa en concurrencia).
            with transaccion() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT Stock_total, Stock_tienda FROM articulos WHERE codigo=%s FOR UPDATE",
                        (codigo,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return False, 0, 0

                    s_total, s_tienda = (
                        (row[0], row[1])
                        if not isinstance(row, dict)
                        else (row["Stock_total"], row["Stock_tienda"])
                    )

                    if (s_total + s_tienda) < cantidad:
                        return False, 0, 0

                    desc_tot = min(cantidad, s_total)
                    desc_tie = cantidad - desc_tot

                    cur.execute(
                        "UPDATE articulos SET Stock_total = Stock_total - %s, Stock_tienda = Stock_tienda - %s WHERE codigo = %s",
                        (desc_tot, desc_tie, codigo),
                    )
            # commit/rollback gestionado por transaccion()

            try:
                stock_signals.stock_actualizado.emit(str(codigo))
            except Exception:
                pass

            return True, desc_tot, desc_tie
        except Exception:
            time.sleep(0.1)
            continue
    return False, 0, 0


def sumar_stock_recepcion(codigo: str, cantidad: int):
    """Incrementa el stock total tras una recepción."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE articulos SET Stock_total = Stock_total + %s, Stock_tienda = Stock_tienda + %s WHERE codigo = %s",
                    (cantidad, cantidad, codigo),
                )
            conn.commit()
            try:
                stock_signals.stock_actualizado.emit(str(codigo))
            except Exception:
                pass
        return True
    except Exception as e:
        logger.error(f"Error al sumar stock: {e}")
        return False


def _ajustar_stock_articulo_por_tipo(
    codigo: str, cantidad: int, tipo_stock: str
) -> bool:
    """
    Ajusta el stock de un artículo en la columna especificada (Stock_tienda o Stock_total).
    cantidad puede ser positiva (sumar) o negativa (restar).
    """
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                columna_stock = ""
                if tipo_stock == "STOCK LINEAL":
                    columna_stock = "Stock_tienda"
                elif tipo_stock == "STOCK ALMACÉN":
                    columna_stock = "Stock_total"
                else:
                    logger.error(f"Tipo de stock desconocido: {tipo_stock}")
                    return False

                # Asegurarse de que el stock no baje de cero
                cur.execute(
                    f"UPDATE articulos SET {columna_stock} = GREATEST(0, {columna_stock} + %s) WHERE codigo = %s",
                    (cantidad, codigo),
                )
            conn.commit()
            try:
                stock_signals.stock_actualizado.emit(str(codigo))
            except Exception:
                pass
        return True
    except Exception as e:
        logger.error(f"Error al ajustar stock de {codigo} en {tipo_stock}: {e}")
        return False


def _get_todos_articulos_para_completer():
    """Obtiene todos los códigos y nombres de artículos para el autocompletado."""
    try:
        with obtener_conexion() as conn:
            cur = conn.cursor()
            cur.execute("SELECT codigo, nombre FROM articulos ORDER BY nombre ASC")
            return cur.fetchall()
    except Exception:
        return []


def set_stock_esperado(codigo: str, nuevo_esperado: int) -> bool:
    """Actualiza el stock esperado en MariaDB."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE articulos SET Stock_esperado = %s WHERE codigo = %s",
                    (nuevo_esperado, codigo),
                )
        try:
            from src.gui.mostrar_stock import stock_signals

            stock_signals.stock_actualizado.emit(str(codigo))
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error(f"Error set_stock_esperado: {e}")
        return False


def set_ubicacion(codigo: str, pasillo: str, estanteria: str, balda: str):
    """
    Inserta o actualiza la ubicación.
    Requiere UNIQUE KEY en (codigo_articulo, pasillo).
    """
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                sql = """
                    INSERT INTO ubicaciones (codigo_articulo, pasillo, estanteria, balda)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        estanteria = VALUES(estanteria),
                        balda = VALUES(balda)
                """
                cur.execute(sql, (codigo, pasillo, estanteria, balda))
        return True
    except Exception:
        logger.exception("Error en set_ubicacion")
        return False


# ============================================================
# BLOQUE VENTAS Y FACTURACIÓN
# ============================================================


def registrar_venta(
    codigo: str,
    cantidad: int,
    fecha: str | None = None,
    forma_pago: str = "efectivo",
    empleado_id: int | None = None,
    cliente_id: int | None = None,
    iva: float = 0.0,
    descuentos: float = 0.0,
    devoluciones: float = 0.0,
) -> bool:
    """Registra una venta simple en MariaDB y actualiza stock."""
    try:
        ensure_schema()
        if fecha is None:
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ventas (codigo, cantidad, fecha, total, forma_pago, empleado)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        codigo,
                        cantidad,
                        fecha,
                        0.0,
                        forma_pago,
                        str(empleado_id) if empleado_id else None,
                    ),
                )
                _salida_stock_clamp(cur, codigo, cantidad, "venta")
        try:
            stock_signals.stock_actualizado.emit(str(codigo))
        except Exception:
            pass
        # INV.1: kárdex SALIDA_VENTA (best-effort, no afecta a la venta).
        try:
            from src.db import kardex
            kardex.registrar_movimiento(codigo, "SALIDA_VENTA", cantidad, origen="TIENDA",
                                        usuario=str(empleado_id) if empleado_id else None,
                                        observaciones="Venta simple")
        except Exception:
            pass
        # INV.3: consumo FEFO de lotes (best-effort, no-op si no hay lotes).
        try:
            from src.db import lotes
            lotes.consumir_fefo(codigo, cantidad, tipo="SALIDA_VENTA",
                                usuario=str(empleado_id) if empleado_id else None,
                                observaciones="Venta simple")
        except Exception:
            pass
        return True
    except Exception:
        logger.exception("Error en registrar_venta")
        return False


def registrar_venta_con_items(
    items: list[dict],
    fecha: str | None = None,
    forma_pago: str = "efectivo",
    empleado_id: int | None = None,
    cliente_id: int | None = None,
    factura_id: int | None = None,
    *,
    cliente: dict | None = None,
    numero_caja: int | None = None,
    total: float | None = None,
    id_empresa: str | None = None,
    id_tienda: int | None = None,
) -> int | None:
    """Registra una venta compleja (varios ítems) en MariaDB — RUTA CANÓNICA de venta.

    Ampliación aditiva (P0 convergencia TPV): parámetros nuevos OPCIONALES y compatibles
    hacia atrás. `cliente` = {id, nombre, nif}; `numero_caja`; `total` (importe real cobrado
    con descuentos — si no se indica, se recalcula por líneas); `id_empresa/id_tienda` para
    override del tenant (si no, se toma del contexto activo). Cada ítem admite además
    `nombre`, `seccion`, `subtotal` (real con descuento), `peso_vendido`, `precio_kg`,
    `modo_venta` (granel). Dispara Verifactu, contabilidad, kárdex, FEFO, stock_almacen y M4."""
    try:
        ensure_schema()
        if fecha is None:
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        from src.db.empresa import empresa_actual_id, tienda_actual_id
        _eid = id_empresa or empresa_actual_id()
        _tid = id_tienda if id_tienda is not None else tienda_actual_id()
        cli = cliente or {}
        cli_id = cli.get("id") if cli.get("id") is not None else cliente_id
        cli_nom = cli.get("nombre")
        cli_nif = cli.get("nif")
        with transaccion() as conn:        # A2.2: venta + ítems + stock atómicos
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ventas (fecha, total, forma_pago, empleado, numero_caja, "
                    "cliente_id, cliente_nombre, cliente_nif, id_empresa, id_tienda) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (fecha, 0.0, forma_pago, str(empleado_id) if empleado_id else None,
                     numero_caja, cli_id, cli_nom, cli_nif, _eid, _tid),
                )
                venta_id = cur.lastrowid
                total_acumulado = 0.0

                for it in items:
                    codigo = it.get("codigo_articulo") or it.get("codigo") or ""
                    cantidad = int(it.get("cantidad") or 0)
                    precio = float(it.get("precio_unitario") or it.get("precio") or 0.0)
                    # Subtotal REAL (con descuento) si se aporta; si no, cantidad×precio.
                    subtotal = (round(float(it["subtotal"]), 2) if it.get("subtotal") is not None
                                else round(cantidad * precio, 2))
                    total_acumulado += subtotal

                    cur.execute(
                        "INSERT INTO venta_items (venta_id, codigo_articulo, nombre, seccion, "
                        "cantidad, precio_unitario, subtotal, peso_vendido, precio_kg, modo_venta, "
                        "id_empresa) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (venta_id, str(codigo), it.get("nombre"), it.get("seccion", ""),
                         cantidad, precio, subtotal, it.get("peso_vendido"), it.get("precio_kg"),
                         it.get("modo_venta", "UNIDAD"), _eid),
                    )
                    _salida_stock_clamp(cur, codigo, cantidad, "venta", id_empresa=_eid)

                total_final = round(float(total) if total is not None else total_acumulado, 2)
                cur.execute("UPDATE ventas SET total = %s WHERE id = %s", (total_final, venta_id))

        try:
            for it in items:
                cod = it.get("codigo_articulo") or it.get("codigo") or ""
                stock_signals.stock_actualizado.emit(str(cod))
        except Exception:
            pass
        # INV.1: kárdex SALIDA_VENTA por ítem (best-effort, tras commit; no afecta a la venta).
        try:
            from src.db import kardex
            for it in items:
                cod = it.get("codigo_articulo") or it.get("codigo") or ""
                qty = int(it.get("cantidad") or 0)
                if cod and qty:
                    kardex.registrar_movimiento(
                        cod, "SALIDA_VENTA", qty, id_documento=venta_id, origen="TIENDA",
                        usuario=str(empleado_id) if empleado_id else None,
                        id_empresa=_eid, id_tienda=_tid, idempotente=True,
                        observaciones=f"Venta ticket #{venta_id}")
        except Exception:
            pass
        # INV.3 + VTA.5: consumo FEFO de lotes (best-effort) y registro del almacén/lote
        # de la venta (ventas.id_almacen + venta_items.id_almacen/id_lote).
        try:
            from src.db import lotes
            from src.db import stock_almacen as _SA
            destino = _SA.almacen_de_tienda(_tid, _eid) if _tid else _SA.almacen_central(_eid)
            with obtener_conexion() as _c2, _c2.cursor() as _cur2:
                if destino:
                    _cur2.execute("UPDATE ventas SET id_almacen=%s WHERE id=%s", (destino, venta_id))
                for it in items:
                    cod = it.get("codigo_articulo") or it.get("codigo") or ""
                    qty = int(it.get("cantidad") or 0)
                    if not (cod and qty):
                        continue
                    r = lotes.consumir_fefo(cod, qty, tipo="SALIDA_VENTA", id_empresa=_eid,
                                            id_tienda=_tid, id_documento=venta_id, idempotente=True,
                                            usuario=str(empleado_id) if empleado_id else None)
                    id_lote = (r.get("detalle") or [{}])[0].get("id_lote") if r else None
                    _cur2.execute("UPDATE venta_items SET id_almacen=%s, id_lote=%s "
                                  "WHERE venta_id=%s AND codigo_articulo=%s",
                                  (destino, id_lote, venta_id, str(cod)))
                _c2.commit()
        except Exception:
            pass
        # INV.4: sincroniza el ledger multialmacén si el artículo está gestionado.
        try:
            from src.db import stock_almacen as SA
            for it in items:
                cod = it.get("codigo_articulo") or it.get("codigo") or ""
                if cod and SA.esta_gestionado(cod, _eid):
                    SA.reseed_articulo(cod, _eid)
        except Exception:
            pass
        # C3.2: gancho fiscal (no-op si fiscal_config.activo=0). Best-effort: nunca
        # rompe la venta. Tras el commit para no extender la transacción de venta.
        try:
            from src.services.fiscal.hooks import gancho_venta
            gancho_venta(venta_id, total_final, tipo="ticket",
                         id_empresa=_eid, id_tienda=_tid)
        except Exception:
            pass
        # E6.4: encola el evento contable (no-op si la contabilidad está apagada).
        try:
            from src.services.contabilidad.posting import encolar_venta
            encolar_venta(venta_id, total_final, fecha, forma_pago=forma_pago,
                          subtipo="ticket", id_empresa=_eid)
        except Exception:
            pass
        return venta_id
    except Exception:
        logger.exception("Error en registrar_venta_con_items")
        return None


def ventas_semana(codigo_articulo: str) -> int:
    """Devuelve el total de ventas del artículo en los últimos 7 días."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT SUM(cantidad)
                    FROM ventas
                    WHERE codigo = %s 
                      AND fecha >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                """,
                    (codigo_articulo,),
                )
                resultado = cur.fetchone()
                if resultado:
                    total = (
                        resultado["SUM(cantidad)"]
                        if isinstance(resultado, dict)
                        else resultado[0]
                    )
                    return int(total) if total else 0
                return 0
    except Exception:
        logger.exception("Error en ventas_semana")
        return 0


def obtener_ventas_por_hora(fecha=None):
    """Devuelve un diccionario: {hora: total_ventas}."""
    import datetime as dt_module

    if fecha is None:
        fecha = dt_module.datetime.now().strftime("%Y-%m-%d")

    horas = {hora: 0 for hora in range(8, 23)}

    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT HOUR(fecha), COUNT(*)
                    FROM ventas
                    WHERE DATE(fecha) = %s
                    GROUP BY HOUR(fecha)
                """,
                    (fecha,),
                )
                for row in cur.fetchall():
                    hora = (
                        row[0]
                        if not isinstance(row, dict)
                        else row.get("HOUR(fecha)", 0)
                    )
                    total = (
                        row[1] if not isinstance(row, dict) else row.get("COUNT(*)", 0)
                    )
                    if 8 <= hora <= 22:
                        horas[hora] = total
    except Exception as e:
        logger.error(f"Error en obtener_ventas_por_hora: {e}")

    return horas


def importar_ventas_desde_csv(ruta_csv: str) -> bool:
    """Importa ventas desde CSV y registra cada una en MariaDB."""
    try:
        if not os.path.exists(ruta_csv):
            logger.warning(f"Archivo CSV no encontrado: {ruta_csv}")
            return False

        with open(ruta_csv, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # Saltar cabecera
            for row in reader:
                if len(row) < 2 or not row[0]:
                    continue
                try:
                    codigo = row[0].strip()
                    cantidad = int(row[1])
                    # H5: misma ruta canónica que una venta normal (fiscal + contabilidad +
                    # kárdex + FEFO + stock_almacen + M4), no la ruta simple.
                    art = obtener_articulo(codigo) or {}
                    precio = float(art.get("precio") or 0) if art else 0.0
                    registrar_venta_con_items(
                        [{"codigo_articulo": codigo, "nombre": art.get("nombre"),
                          "cantidad": cantidad, "precio_unitario": precio,
                          "subtotal": round(precio * cantidad, 2)}],
                        forma_pago="importada")
                except ValueError:
                    continue

        logger.info(f"Ventas importadas exitosamente desde: {ruta_csv}")
        return True
    except Exception:
        logger.exception("Error importar_ventas_desde_csv")
        return False


def obtener_ventas_ia(id_empresa=None, dias=730):
    """Función especial para la IA Prophet (B7).

    Devuelve las ventas (fecha, codigo, cantidad) de UNA empresa, acotadas a los últimos
    `dias` (por defecto 2 años — ventana suficiente para previsión semanal). Mantiene el
    MISMO esquema de salida. Compatibilidad: sin argumentos usa la empresa ACTIVA y la
    ventana por defecto (corrige el full-scan global y el cruce entre empresas)."""
    import pandas as pd
    cols = ["fecha", "codigo", "cantidad"]
    try:
        if id_empresa is None:
            from src.db.empresa import empresa_actual_id
            id_empresa = empresa_actual_id()
    except Exception:
        pass
    try:
        with obtener_conexion() as conn:
            query = ("SELECT fecha, codigo, cantidad FROM ventas "
                     "WHERE id_empresa=%s AND fecha >= (CURDATE() - INTERVAL %s DAY)")
            return pd.read_sql_query(query, conn, params=(id_empresa, int(dias)))
    except Exception as e:
        logger.error(f"Error en obtener_ventas_ia: {e}")
        return pd.DataFrame(columns=cols)


# ============================================================
# BLOQUE FACTURACIÓN DIARIA (LOG DE EXPORTES)
# ============================================================


def log_facturacion_export(
    fecha_iso: str,
    empresa: str,
    tienda: str,
    responsable: str,
    total_efectivo: float,
    total_tarjeta: float,
    total: float,
    ruta_pdf: str,
) -> int | None:
    """Inserta un registro en facturacion_diaria_log y devuelve el ID insertado."""
    try:
        ensure_schema()
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO facturacion_diaria_log (
                        fecha, empresa, tienda, responsable, 
                        total_efectivo, total_tarjeta, total, ruta_pdf
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        fecha_iso,
                        empresa,
                        tienda,
                        responsable,
                        total_efectivo,
                        total_tarjeta,
                        total,
                        ruta_pdf,
                    ),
                )
                return cur.lastrowid
    except Exception:
        logger.exception("Error en log_facturacion_export")
        return None


def listar_facturacion_diaria_logs(limit: int = 200) -> list[dict]:
    """Devuelve los registros de facturacion_diaria_log (más recientes primero)."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        id, fecha, empresa, tienda, responsable, 
                        total_efectivo, total_tarjeta, total, 
                        ruta_pdf, fecha_exportacion
                    FROM facturacion_diaria_log
                    ORDER BY fecha_exportacion DESC
                    LIMIT %s
                """,
                    (limit,),
                )
                return cur.fetchall()
    except Exception:
        logger.exception("Error en listar_facturacion_diaria_logs")
        return []


def eliminar_facturacion_log_por_ruta(ruta_pdf: str) -> bool:
    """
    Elimina el registro de facturacion_diaria_log asociado a la ruta
    y borra el archivo físico del disco si existe.
    """
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM facturacion_diaria_log WHERE ruta_pdf = %s",
                    (ruta_pdf,),
                )
        try:
            if ruta_pdf and os.path.exists(ruta_pdf):
                os.remove(ruta_pdf)
                logger.info(f"Archivo físico eliminado: {ruta_pdf}")
        except Exception as e:
            logger.warning(
                f"Registro en DB borrado, pero no se pudo borrar el PDF: {e}"
            )
        return True
    except Exception:
        logger.exception("Error crítico en eliminar_facturacion_log_por_ruta")
        return False


# ============================================================
# BLOQUE GESTIÓN DE TRASPASOS LOGÍSTICOS
# ============================================================


def registrar_traspaso(*args, **kwargs):
    """
    Compatibilidad con la firma antigua, delegando en la nueva capa logística.
    Devuelve un dict con metadata útil en éxito o False en error.
    """
    try:
        from src.db.logistica import guardar_traspaso_logistico

        if kwargs.get("pales"):
            return guardar_traspaso_logistico(
                origen=kwargs.get("origen"),
                destino=kwargs.get("destino"),
                usuario=kwargs.get("usuario"),
                agencia=kwargs.get("agencia"),
                observaciones=kwargs.get("observaciones"),
                pales=kwargs.get("pales"),
                id_documento=kwargs.get("id_documento"),
                fecha_envio=kwargs.get("fecha_envio"),
            )

        if args and len(args) >= 9:
            (
                id_traspaso,
                origen,
                destino,
                usuario,
                articulos,
                agencia,
                observaciones,
                fecha_envio,
                pesos_pales,
            ) = args[:9]
        else:
            id_traspaso = kwargs.get("id_traspaso") or kwargs.get("id_documento")
            origen = kwargs.get("origen")
            destino = kwargs.get("destino")
            usuario = kwargs.get("usuario")
            articulos = kwargs.get("articulos", [])
            agencia = kwargs.get("agencia")
            observaciones = kwargs.get("observaciones")
            fecha_envio = kwargs.get("fecha_envio") or kwargs.get("fecha")
            pesos_pales = kwargs.get("pesos_pales", {})

        pales = _normalizar_pales_desde_articulos(articulos, pesos_pales)
        return guardar_traspaso_logistico(
            origen=origen,
            destino=destino,
            usuario=usuario,
            agencia=agencia,
            observaciones=observaciones,
            pales=pales,
            id_documento=id_traspaso,
            fecha_envio=fecha_envio,
        )
    except Exception as e:
        logger.error(f"Error en registrar_traspaso: {e}")
        return False


def cancelar_traspaso_seguro(id_documento: str) -> bool:
    """Cancela un traspaso solo si el usuario activo es ADMINISTRADOR."""
    from src.db.usuario import sesion_global

    if not sesion_global.es_admin():
        logger.warning(
            f"Intento de cancelación no autorizado por: {sesion_global.obtener_nombre()}"
        )
        return False
    return cancelar_traspaso(id_documento)


def cancelar_traspaso(id_documento: str) -> bool:
    """Cancela un traspaso 'PENDIENTE' y devuelve el stock a los artículos."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT estado FROM documentos_logisticos WHERE id_documento = %s",
                    (id_documento,),
                )
                res = cur.fetchone()
                if not res:
                    logger.warning(
                        f"No se puede cancelar {id_documento}: No encontrado."
                    )
                    return False
                estado_actual = res[0] if not isinstance(res, dict) else res["estado"]
                if estado_actual != "PENDIENTE":
                    logger.warning(
                        f"No se puede cancelar {id_documento}: estado={estado_actual}"
                    )
                    return False

                cur.execute(
                    "SELECT codigo_articulo, cantidad_enviada FROM documentos_logisticos_lineas WHERE id_documento = %s",
                    (id_documento,),
                )
                items = cur.fetchall()

                for item in items:
                    if isinstance(item, dict):
                        cod, qty = item["codigo_articulo"], item["cantidad_enviada"]
                    else:
                        cod, qty = item[0], item[1]
                    cur.execute(
                        "UPDATE articulos SET Stock_total = Stock_total + %s WHERE codigo = %s",
                        (qty, cod),
                    )
                    stock_signals.stock_actualizado.emit(cod)

                cur.execute(
                    "UPDATE documentos_logisticos SET estado = 'CANCELADO', observaciones = CONCAT(COALESCE(observaciones,''), ' | Cancelado el ', NOW()) WHERE id_documento = %s",
                    (id_documento,),
                )
            conn.commit()
            logger.info(f"Traspaso {id_documento} cancelado con éxito.")
            return True
    except Exception as e:
        logger.error(f"Error al cancelar traspaso {id_documento}: {e}")
        return False


def registrar_recepcion_completa(id_traspaso, proveedor, usuario, items):
    """Compatibilidad para recepciones antiguas sobre el nuevo esquema."""
    try:
        return procesar_recepcion_logistica(
            id_pale_escaneado=id_traspaso,
            centro_receptor=proveedor,
            usuario_receptor=usuario,
            items_a_recibir=items,
        )
    except Exception as e:
        logger.error(f"Error en registrar_recepcion_completa: {e}")
        return False


def _tenant_actual_mov():
    """(id_empresa, id_tienda) ACTIVOS para etiquetar movimientos/auditoría (3b.4).
    Import perezoso para evitar el ciclo con src.db.empresa."""
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        return empresa_actual_id(), tienda_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID, None


def registrar_pale(
    pale_codigo, proveedor, fecha, items, id_traspaso=None, observaciones=""
):
    """Compatibilidad ligera para la API antigua de palés."""
    try:
        resultado = registrar_traspaso(
            id_documento=id_traspaso,
            origen=proveedor,
            destino=proveedor,
            usuario="SISTEMA",
            articulos=items,
            agencia="PROPIA",
            observaciones=observaciones,
            fecha_envio=fecha,
            pesos_pales={str(pale_codigo): None},
        )
        return bool(resultado)
    except Exception as e:
        logger.error(f"Error en registrar_pale: {e}")
        return False


def registrar_pale_entrada(id_pale, codigo_articulo, cantidad):
    """Registra la entrada de un palé como movimiento de stock."""
    try:
        _emp, _tnd = _tenant_actual_mov()
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO movimientos_stock
                        (codigo_articulo, tipo_movimiento, cantidad, id_pale, origen,
                         observaciones, id_empresa, id_tienda)
                    VALUES (%s, 'ENTRADA_PALE', %s, %s, 'EXTERNO', %s, %s, %s)
                    """,
                    (codigo_articulo, cantidad, str(id_pale), f"Palé {id_pale}", _emp, _tnd),
                )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error registrando palé: {e}")
        return False


# ============================================================
# BLOQUE GENERACIÓN DE IDENTIFICADORES LOGÍSTICOS
# ============================================================


def generar_id_documento(tipo_doc="TRA"):
    """Genera un ID correlativo: TRA-2026-00001."""
    anio_actual = datetime.now().year
    prefix = f"{tipo_doc}-{anio_actual}-"

    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id_documento FROM documentos_logisticos WHERE id_documento LIKE %s ORDER BY id_documento DESC LIMIT 1",
                    (f"{prefix}%",),
                )
                row = cur.fetchone()

                if row:
                    try:
                        ultimo_num = int(row["id_documento"].split("-")[-1])
                        nuevo_num = ultimo_num + 1
                    except Exception:
                        nuevo_num = 1
                else:
                    nuevo_num = 1

                return f"{prefix}{nuevo_num:05d}"
    except Exception as e:
        logger.error(f"Error generando ID: {e}")
        return f"{prefix}{int(time.time()) % 10000:05d}"


def generar_id_logistico(origen: str, destino: str, flujo: str) -> tuple[str, int]:
    """Genera ID robusto: [ORIGEN]-[Flujo+Secuencial]-[DESTINO]-[YYYY]."""
    hoy = datetime.now()
    anio = hoy.year
    orig_code = formatear_nombre_centro(origen)
    dest_code = formatear_nombre_centro(destino)

    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                patron = f"{orig_code}-{flujo}%-{dest_code}-{anio}"
                cur.execute(
                    "SELECT id_documento FROM documentos_logisticos WHERE id_documento LIKE %s ORDER BY id_documento DESC LIMIT 1",
                    (patron,),
                )
                res = cur.fetchone()

                ultimo_val = 0
                if res:
                    val_id = res[0]
                    match = re.search(rf"-{flujo}(\d+)-", val_id)
                    if match:
                        ultimo_val = int(match.group(1))

                nueva_seq = ultimo_val + 1
                id_final = f"{orig_code}-{flujo}{nueva_seq:03d}-{dest_code}-{anio}"
                return id_final, nueva_seq
    except Exception as e:
        logger.error(f"Error generando ID: {e}")
        return f"{orig_code}-ERR-000", 0


def generar_id_traspaso(origen: str, destino: str):
    from src.db.logistica import generar_id_traspaso as _generar_id_traspaso_nuevo

    return _generar_id_traspaso_nuevo(origen, destino)


def registrar_linea_detalle(
    cursor, id_traspaso, id_pale, codigo, descripcion, cantidad, peso_bulto=0.0
):
    """Registra una línea individual de producto en documentos_logisticos_lineas."""
    try:
        id_visual = str(id_pale).split("-")[-1] if "-" in str(id_pale) else str(id_pale)
        cursor.execute(
            """
            INSERT INTO documentos_logisticos_lineas (
                id_documento, id_pale, id_visual, codigo_articulo, nombre_articulo, cantidad_enviada, peso_bulto
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(id_traspaso),
                str(id_pale),
                id_visual,
                str(codigo),
                str(descripcion),
                int(cantidad),
                float(peso_bulto),
            ),
        )
        return True
    except Exception as e:
        logger.error(f"Error en registrar_linea_detalle: {e}")
        raise e


# ============================================================
# BLOQUE CONSULTAS LOGÍSTICAS (HISTORIAL, PALES, TRAZABILIDAD)
# ============================================================


def obtener_historial_traspasos(estado_filtro="PENDIENTE", texto_filtro=""):
    from src.db.logistica import (
        obtener_historial_traspasos as _obtener_historial_traspasos_nuevo,
    )

    return _obtener_historial_traspasos_nuevo(estado_filtro, texto_filtro)


def obtener_trazabilidad_logistica(
    origen: str | None = None,
    destino: str | None = None,
    busqueda: str = "",
):
    from src.db.logistica import (
        obtener_trazabilidad_logistica as _obtener_trazabilidad_logistica_nueva,
    )

    return _obtener_trazabilidad_logistica_nueva(origen, destino, busqueda)


def obtener_pales_por_documento_logistico(id_documento: str, busqueda: str = ""):
    from src.db.logistica import (
        obtener_pales_por_documento_logistico as _obtener_pales_por_documento_nuevo,
    )

    return _obtener_pales_por_documento_nuevo(id_documento, busqueda)


def obtener_items_por_pale_logistico(id_pale: str, busqueda: str = ""):
    from src.db.logistica import (
        obtener_items_por_pale_logistico as _obtener_items_por_pale_nuevo,
    )

    return _obtener_items_por_pale_nuevo(id_pale, busqueda)


def obtener_items_pale_traspaso(id_pale_buscado):
    from src.db.logistica import (
        obtener_items_pale_traspaso as _obtener_items_pale_traspaso_nuevo,
    )

    return _obtener_items_pale_traspaso_nuevo(id_pale_buscado)


def obtener_items_pale(id_pale):
    return obtener_items_por_pale_logistico(id_pale)


def obtener_documento_logistico_completo(id_documento: str):
    from src.db.logistica import (
        obtener_documento_logistico_completo as _obtener_documento_logistico_completo_nuevo,
    )

    return _obtener_documento_logistico_completo_nuevo(id_documento)


def procesar_recepcion_logistica(
    id_pale_escaneado: str,
    centro_receptor: str,
    usuario_receptor: str,
    items_a_recibir: list,
):
    from src.db.logistica import (
        procesar_recepcion_logistica as _procesar_recepcion_logistica_nueva,
    )

    return _procesar_recepcion_logistica_nueva(
        id_pale_escaneado=id_pale_escaneado,
        centro_receptor=centro_receptor,
        usuario_receptor=usuario_receptor,
        items_a_recibir=items_a_recibir,
    )


def obtener_destinos_traspaso():
    """Devuelve destinos disponibles desde tablas maestras."""
    destinos = []
    try:
        ensure_schema()
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                for tabla in ("almacen", "tiendas"):
                    if not tabla_existe(tabla):
                        continue
                    cur.execute(
                        f"SELECT nombre FROM {tabla} WHERE COALESCE(activo, 1) = 1 ORDER BY nombre ASC"
                    )
                    for fila in cur.fetchall():
                        nombre = str(
                            fila[0] if not isinstance(fila, dict) else fila["nombre"]
                        ).strip()
                        if nombre and nombre not in destinos:
                            destinos.append(nombre)
    except Exception as e:
        logger.error(f"Error en obtener_destinos_traspaso: {e}")

    return destinos or ["ALMACEN CENTRAL", "TIENDA 01", "TIENDA 02", "TIENDA 03"]


# ============================================================
# BLOQUE AUDITORÍA
# ============================================================


def log_auditoria(
    usuario: str,
    accion: str,
    tabla_afectada: str = None,
    detalles: str = None,
    ip_origen: str = None,
):
    """Registra una acción en la tabla de auditoría (bajo la empresa/tienda activas)."""
    try:
        _emp, _tnd = _tenant_actual_mov()
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO auditoria_logs (usuario, accion, tabla_afectada, detalles, "
                    "ip_origen, id_empresa, id_tienda) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (usuario, accion, tabla_afectada, detalles, ip_origen, _emp, _tnd),
                )
            conn.commit()
    except Exception as e:
        logger.error(f"Error al registrar auditoría: {e}")


# ============================================================
# BLOQUE UTILIDADES INTERNAS (NORMALIZACIÓN DE PALÉS)
# ============================================================


def _normalizar_pales_desde_articulos(articulos, pesos_pales=None):
    pesos_pales = pesos_pales or {}
    pales = {}

    for articulo in articulos or []:
        if isinstance(articulo, dict):
            codigo = str(articulo.get("codigo") or "").strip().upper()
            nombre = str(articulo.get("nombre") or codigo).strip()
            cantidad = int(articulo.get("cantidad") or 0)
            id_visual = (
                str(
                    articulo.get("pale")
                    or articulo.get("id_visual_pale")
                    or articulo.get("id_visual")
                    or "PALE1"
                )
                .upper()
                .replace(" ", "")
            )
        else:
            codigo = str(articulo[0] or "").strip().upper()
            nombre = str(articulo[1] or codigo).strip()
            cantidad = int(articulo[2] or 0)
            id_visual = "PALE1"

        if not codigo or cantidad <= 0:
            continue

        pale = pales.setdefault(
            id_visual,
            {
                "id_visual": id_visual,
                "peso": pesos_pales.get(id_visual),
                "articulos": [],
            },
        )
        pale["articulos"].append(
            {"codigo": codigo, "nombre": nombre, "cantidad": cantidad}
        )

    return pales
