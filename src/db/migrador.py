"""
Motor de MIGRACIONES versionadas (C4) — propio, numerado, preparado para SaaS.

- Migraciones = módulos Python en `src/database/migraciones/NNNN_*.py` con
  `VERSION`, `DESCRIPCION`, `aplicar(cur)` y opcional `revertir(cur)`.
- Registro/auditoría en la tabla `schema_migraciones` (versión, descripción,
  checksum, fecha, duración, ejecutor/proceso, resultado, tenant).
- **Baseline 0001** envuelve el `ensure_schema()` actual (idempotente): seguro en
  BD nueva y existente. Las instalaciones ya desplegadas se **sellan** (stamp) sin
  re-ejecutar nada destructivo.
- **Preparado para SaaS**: todas las operaciones aceptan una `conexion_fn` (fábrica
  de conexión) → ejecutable por cada base/tenant de forma independiente, y desde
  procesos de despliegue. Por defecto usa la conexión activa.
- Seguridad del dato primero: backup automático previo a aplicar pendientes.
  Las migraciones NUNCA deben contener secretos (usar el sistema de claves de C1).
"""

import getpass
import hashlib
import importlib
import logging
import os
import pkgutil
import time

from src.db.conexion import obtener_conexion

logger = logging.getLogger("db.migrador")

_PAQUETE = "src.database.migraciones"


# ── Descubrimiento de migraciones ────────────────────────────────────────────
class _Migracion:
    def __init__(self, modulo):
        self.version = str(getattr(modulo, "VERSION"))
        self.descripcion = getattr(modulo, "DESCRIPCION", "")
        self.aplicar = getattr(modulo, "aplicar", None)
        self.revertir = getattr(modulo, "revertir", None)
        self.reversible = bool(getattr(modulo, "REVERSIBLE", self.revertir is not None))
        self.requiere_backup = bool(getattr(modulo, "REQUIERE_BACKUP", True))
        self.checksum = _checksum_modulo(modulo)


def _checksum_modulo(modulo) -> str:
    try:
        with open(modulo.__file__, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return ""


def _nombres_modulos() -> list:
    """Nombres de módulos de migración (NNNN_*). Combina el escaneo del paquete
    (desarrollo) con la lista explícita `MODULOS` (garantiza el descubrimiento en
    el .exe, donde pkgutil no ve el archivo PYZ)."""
    nombres = set()
    try:
        paquete = importlib.import_module(_PAQUETE)
        try:
            for _f, modname, _p in pkgutil.iter_modules(paquete.__path__):
                nombres.add(modname)
        except Exception:
            pass
        nombres |= set(getattr(paquete, "MODULOS", []) or [])
    except Exception as e:
        logger.error("No se pudo cargar el paquete de migraciones: %s", e)
    return [n for n in nombres if n[:4].isdigit() and "_" in n]


def descubrir() -> list:
    """Migraciones ordenadas por versión."""
    migs = []
    for modname in _nombres_modulos():
        try:
            mod = importlib.import_module(f"{_PAQUETE}.{modname}")
            migs.append(_Migracion(mod))
        except Exception as e:
            logger.error("Migración '%s' no se pudo cargar: %s", modname, e)
    return sorted(migs, key=lambda m: m.version)


# ── Registro / auditoría ─────────────────────────────────────────────────────
def _asegurar_tabla(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migraciones (
            version     VARCHAR(20)  NOT NULL,
            descripcion VARCHAR(255)          DEFAULT NULL,
            checksum    CHAR(64)              DEFAULT NULL,
            aplicada_en DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            duracion_ms INT                   DEFAULT NULL,
            ejecutor    VARCHAR(120)          DEFAULT NULL,
            tenant      VARCHAR(120)          DEFAULT NULL,
            resultado   VARCHAR(20)  NOT NULL DEFAULT 'ok',
            PRIMARY KEY (version)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def _aplicadas(cur) -> set:
    cur.execute("SELECT version FROM schema_migraciones WHERE resultado IN ('ok','stamp')")
    return {r[0] if not isinstance(r, dict) else r["version"] for r in cur.fetchall()}


def _ejecutor() -> str:
    try:
        return (os.getenv("MIGRACIONES_EJECUTOR")
                or f"{getpass.getuser()}@{os.getenv('COMPUTERNAME', 'host')}")[:120]
    except Exception:
        return "desconocido"


def _tenant() -> str:
    from src.db.conexion import DB_CONFIG
    return str(DB_CONFIG.get("database", ""))[:120]


def _registrar(cur, mig, duracion_ms, resultado):
    cur.execute(
        "INSERT INTO schema_migraciones "
        "(version, descripcion, checksum, duracion_ms, ejecutor, tenant, resultado) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE descripcion=VALUES(descripcion), checksum=VALUES(checksum), "
        "aplicada_en=CURRENT_TIMESTAMP, duracion_ms=VALUES(duracion_ms), "
        "ejecutor=VALUES(ejecutor), tenant=VALUES(tenant), resultado=VALUES(resultado)",
        (mig.version, mig.descripcion[:255], mig.checksum, duracion_ms,
         _ejecutor(), _tenant(), resultado))


def _instalacion_existente(cur) -> bool:
    """True si la BD ya tiene esquema previo (tablas núcleo) → se sella la baseline."""
    try:
        cur.execute("SHOW TABLES LIKE 'usuarios'")
        return cur.fetchone() is not None
    except Exception:
        return False


# ── API pública ──────────────────────────────────────────────────────────────
def estado(conexion_fn=None) -> list:
    """Estado de cada migración: {version, descripcion, aplicada}."""
    conexion_fn = conexion_fn or obtener_conexion
    migs = descubrir()
    with conexion_fn() as conn, conn.cursor() as cur:
        _asegurar_tabla(cur)
        conn.commit()
        aplicadas = _aplicadas(cur)
    return [{"version": m.version, "descripcion": m.descripcion,
             "aplicada": m.version in aplicadas} for m in migs]


def aplicar_pendientes(conexion_fn=None, backup=True) -> dict:
    """Aplica en orden las migraciones pendientes. Hace BACKUP previo si hay
    pendientes. La baseline (0001) se SELLA (no se re-ejecuta) si la BD ya existía.
    Devuelve {aplicadas, selladas, backup, error}."""
    conexion_fn = conexion_fn or obtener_conexion
    migs = descubrir()
    with conexion_fn() as conn, conn.cursor() as cur:
        _asegurar_tabla(cur)
        conn.commit()
        aplicadas = _aplicadas(cur)
        existente = _instalacion_existente(cur)
    pendientes = [m for m in migs if m.version not in aplicadas]
    res = {"aplicadas": [], "selladas": [], "backup": None, "error": None}
    if not pendientes:
        return res

    # Backup previo (seguridad del dato primero), solo si hay trabajo real.
    pendientes_reales = [m for m in pendientes
                         if not (m.version == "0001" and existente)]
    if backup and pendientes_reales and any(m.requiere_backup for m in pendientes_reales):
        try:
            from src.db import backup as _bk
            res["backup"] = _bk.crear_backup(version_objetivo=pendientes[-1].version)
            if res["backup"].get("resultado") != "ok":
                logger.warning("Backup previo no OK; se continúa con precaución.")
        except Exception as e:
            logger.warning("No se pudo crear backup previo: %s", e)

    for m in pendientes:
        # Baseline en BD existente → sellar sin ejecutar (no destructivo).
        if m.version == "0001" and existente:
            with conexion_fn() as conn, conn.cursor() as cur:
                _registrar(cur, m, 0, "stamp")
                conn.commit()
            res["selladas"].append(m.version)
            continue
        t0 = time.time()
        try:
            if m.version == "0001":
                # Baseline en BD nueva: delega en el esquema idempotente actual.
                from src.db import conexion as _cx
                _cx.ensure_schema(force=True)
            else:
                with conexion_fn() as conn, conn.cursor() as cur:
                    m.aplicar(cur)
                    conn.commit()
            dur = int((time.time() - t0) * 1000)
            with conexion_fn() as conn, conn.cursor() as cur:
                _registrar(cur, m, dur, "ok")
                conn.commit()
            res["aplicadas"].append(m.version)
            logger.info("Migración %s aplicada (%s ms).", m.version, dur)
        except Exception as e:
            logger.error("Fallo en migración %s: %s", m.version, e)
            res["error"] = f"{m.version}: {e}"
            try:
                with conexion_fn() as conn, conn.cursor() as cur:
                    _registrar(cur, m, int((time.time() - t0) * 1000), "error")
                    conn.commit()
            except Exception:
                pass
            break          # detener: no aplicar siguientes hasta corregir
    return res


def sellar(version, conexion_fn=None) -> bool:
    """Marca como aplicadas (stamp) todas las migraciones hasta `version` sin
    ejecutarlas (para sellar instalaciones existentes a un punto conocido)."""
    conexion_fn = conexion_fn or obtener_conexion
    try:
        with conexion_fn() as conn, conn.cursor() as cur:
            _asegurar_tabla(cur)
            for m in descubrir():
                if m.version <= str(version):
                    _registrar(cur, m, 0, "stamp")
            conn.commit()
        return True
    except Exception as e:
        logger.error("sellar(%s): %s", version, e)
        return False


def revertir(version_objetivo, conexion_fn=None) -> dict:
    """Revierte (downgrade) las migraciones aplicadas posteriores a
    `version_objetivo`, en orden inverso, usando su `revertir()`."""
    conexion_fn = conexion_fn or obtener_conexion
    res = {"revertidas": [], "error": None, "irreversibles": []}
    migs = {m.version: m for m in descubrir()}
    with conexion_fn() as conn, conn.cursor() as cur:
        _asegurar_tabla(cur)
        aplicadas = sorted(_aplicadas(cur), reverse=True)
    for v in aplicadas:
        if v <= str(version_objetivo):
            break
        m = migs.get(v)
        if not m or not m.revertir:
            res["irreversibles"].append(v)
            res["error"] = f"{v} no es reversible"
            break
        try:
            with conexion_fn() as conn, conn.cursor() as cur:
                m.revertir(cur)
                cur.execute("DELETE FROM schema_migraciones WHERE version=%s", (v,))
                conn.commit()
            res["revertidas"].append(v)
        except Exception as e:
            res["error"] = f"{v}: {e}"
            break
    return res
