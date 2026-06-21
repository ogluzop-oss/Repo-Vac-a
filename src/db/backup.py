"""
Copia de seguridad previa a migraciones (C4) — prioriza la seguridad del dato.

Estrategia: `mysqldump` como primera opción; si no está disponible, export lógico
(CREATE TABLE + INSERTs) de la base. Cada backup guarda un sidecar JSON con los
metadatos (fecha, versión objetivo de migración, base, método, tablas, resultado)
y se aplica una política de RETENCIÓN configurable.

Nunca contiene secretos en el nombre/metadatos; la contraseña de `mysqldump` se
pasa por entorno (`MYSQL_PWD`), nunca por línea de comandos.
"""

import json
import logging
import os
import shutil
import subprocess
from datetime import datetime

from src.db.conexion import DB_CONFIG, obtener_conexion

logger = logging.getLogger("db.backup")


def _dir_backups() -> str:
    try:
        from src.utils.recursos import ruta_datos
        base = ruta_datos("backups")
    except Exception:
        base = os.path.join("documentos", "backups")
    os.makedirs(base, exist_ok=True)
    return base


def _retencion() -> int:
    try:
        return max(1, int(os.getenv("MIGRACIONES_BACKUP_RETENCION", "10")))
    except ValueError:
        return 10


def _aplicar_retencion():
    """Conserva solo los N backups más recientes (borra .sql y su .json)."""
    carpeta = _dir_backups()
    sqls = sorted((f for f in os.listdir(carpeta) if f.endswith(".sql")), reverse=True)
    for viejo in sqls[_retencion():]:
        for f in (viejo, viejo[:-4] + ".json"):
            ruta = os.path.join(carpeta, f)
            if os.path.exists(ruta):
                try:
                    os.remove(ruta)
                except OSError:
                    pass


def _mysqldump(ruta_sql: str, db: str) -> bool:
    exe = shutil.which("mysqldump")
    if not exe:
        return False
    cmd = [exe, "-h", str(DB_CONFIG.get("host", "127.0.0.1")),
           "-P", str(DB_CONFIG.get("port", 3306)),
           "-u", str(DB_CONFIG.get("user", "root")),
           "--single-transaction", "--routines", "--events", db]
    entorno = dict(os.environ)
    if DB_CONFIG.get("password"):
        entorno["MYSQL_PWD"] = str(DB_CONFIG["password"])   # nunca en la línea de comandos
    try:
        with open(ruta_sql, "wb") as fh:
            r = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, env=entorno, timeout=600)
        if r.returncode == 0:
            return True
        logger.warning("mysqldump falló (%s): %s", r.returncode, r.stderr[:200])
    except Exception as e:
        logger.warning("mysqldump no utilizable: %s", e)
    return False


def _export_logico(ruta_sql: str) -> list:
    """Respaldo lógico (CREATE TABLE + INSERTs) si no hay mysqldump. Devuelve las
    tablas exportadas."""
    tablas = []
    with obtener_conexion() as conn, conn.cursor() as cur, open(ruta_sql, "w", encoding="utf-8") as fh:
        fh.write("SET FOREIGN_KEY_CHECKS=0;\n")
        cur.execute("SHOW TABLES")
        nombres = [r[0] if not isinstance(r, dict) else list(r.values())[0] for r in cur.fetchall()]
        for t in nombres:
            cur.execute(f"SHOW CREATE TABLE `{t}`")
            fila = cur.fetchone()
            ddl = fila[1] if not isinstance(fila, dict) else list(fila.values())[1]
            fh.write(f"\n-- {t}\nDROP TABLE IF EXISTS `{t}`;\n{ddl};\n")
            cur.execute(f"SELECT * FROM `{t}`")
            filas = cur.fetchall()
            cols = [d[0] for d in cur.description]
            for f in filas:
                vals = f if not isinstance(f, dict) else [f[c] for c in cols]
                vals_sql = ", ".join(_sql_valor(v) for v in vals)
                fh.write(f"INSERT INTO `{t}` (`{'`,`'.join(cols)}`) VALUES ({vals_sql});\n")
            tablas.append(t)
        fh.write("\nSET FOREIGN_KEY_CHECKS=1;\n")
    return tablas


def _sql_valor(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"


def crear_backup(version_objetivo: str = "", motivo: str = "pre_migracion") -> dict:
    """Crea un backup de la base activa antes de migrar. Devuelve metadatos
    {ruta, metodo, db, fecha, version_objetivo, tablas, resultado}."""
    db = DB_CONFIG.get("database", "")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre = f"{motivo}_{db}_{ts}.sql"
    ruta = os.path.join(_dir_backups(), nombre)
    meta = {"ruta": ruta, "db": db, "fecha": datetime.now().isoformat(timespec="seconds"),
            "version_objetivo": version_objetivo, "motivo": motivo,
            "metodo": None, "tablas": None, "resultado": "error"}
    try:
        if _mysqldump(ruta, db):
            meta["metodo"] = "mysqldump"
            meta["resultado"] = "ok"
        else:
            meta["tablas"] = _export_logico(ruta)
            meta["metodo"] = "export_logico"
            meta["resultado"] = "ok"
    except Exception as e:
        logger.error("crear_backup: %s", e)
        meta["resultado"] = "error"
        meta["error"] = str(e)[:200]
    # Sidecar de metadatos (sin secretos).
    try:
        with open(ruta[:-4] + ".json", "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass
    _aplicar_retencion()
    try:
        from src.utils.observabilidad import registrar_evento
        registrar_evento("backup", "backup creado" if meta["resultado"] == "ok" else "backup fallido",
                         nivel=("info" if meta["resultado"] == "ok" else "error"),
                         metodo=meta.get("metodo"), db=db)
    except Exception:
        pass
    return meta


# ── Restauración ──────────────────────────────────────────────────────────────
def listar_backups() -> list:
    """Backups disponibles (más recientes primero) con sus metadatos si existen."""
    carpeta = _dir_backups()
    out = []
    for f in sorted((x for x in os.listdir(carpeta) if x.endswith(".sql")), reverse=True):
        ruta = os.path.join(carpeta, f)
        meta = {}
        sidecar = ruta[:-4] + ".json"
        if os.path.exists(sidecar):
            try:
                meta = json.load(open(sidecar, encoding="utf-8"))
            except Exception:
                meta = {}
        out.append({"ruta": ruta, "nombre": f, **meta})
    return out


def _mysql_cli(ruta_sql: str, db: str) -> bool:
    """Restaura con el cliente `mysql` (robusto para dumps de mysqldump)."""
    exe = shutil.which("mysql")
    if not exe:
        return False
    cmd = [exe, "-h", str(DB_CONFIG.get("host", "127.0.0.1")),
           "-P", str(DB_CONFIG.get("port", 3306)),
           "-u", str(DB_CONFIG.get("user", "root")), db]
    entorno = dict(os.environ)
    if DB_CONFIG.get("password"):
        entorno["MYSQL_PWD"] = str(DB_CONFIG["password"])
    try:
        with open(ruta_sql, "rb") as fh:
            r = subprocess.run(cmd, stdin=fh, stderr=subprocess.PIPE, env=entorno, timeout=600)
        if r.returncode == 0:
            return True
        logger.warning("restore mysql CLI falló (%s): %s", r.returncode, r.stderr[:200])
    except Exception as e:
        logger.warning("restore mysql CLI no utilizable: %s", e)
    return False


def _restaurar_pymysql(ruta_sql: str, db: str) -> bool:
    """Restauración portable vía PyMySQL (multi-statement) para el formato lógico.
    Asegura la BD destino y ejecuta el script completo."""
    import pymysql
    cfg = {k: v for k, v in DB_CONFIG.items() if k != "database"}
    cfg["client_flag"] = pymysql.constants.CLIENT.MULTI_STATEMENTS
    sql = open(ruta_sql, encoding="utf-8").read()
    conn = pymysql.connect(**cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db}` DEFAULT CHARACTER SET utf8mb4")
        conn.commit()
        conn.select_db(db)                        # selecciona la BD destino
        with conn.cursor() as cur:
            cur.execute(sql)                      # multi-statement
            while cur.nextset():                  # agota todos los result sets
                pass
        conn.commit()
        return True
    finally:
        conn.close()


def edad_ultimo_backup_horas() -> float | None:
    """Horas desde el último backup creado, o None si no hay ninguno."""
    bks = listar_backups()
    if not bks:
        return None
    try:
        ult = bks[0]
        fecha = ult.get("fecha")
        if fecha:
            t = datetime.fromisoformat(fecha)
        else:  # deriva del mtime del .sql
            t = datetime.fromtimestamp(os.path.getmtime(ult["ruta"]))
        return (datetime.now() - t).total_seconds() / 3600.0
    except Exception as e:
        logger.warning("edad_ultimo_backup_horas: %s", e)
        return None


def backup_si_corresponde(intervalo_horas: int = 24, motivo: str = "programado") -> dict | None:
    """M2 — Programación: crea un backup solo si el último tiene más de `intervalo_horas`
    (o no hay ninguno). Pensado para invocarse al arrancar/cerrar la app (sin daemon).
    Devuelve la metadata del backup creado, o None si no tocaba."""
    edad = edad_ultimo_backup_horas()
    if edad is not None and edad < intervalo_horas:
        return None
    return crear_backup(motivo=motivo)


def verificar_backup(ruta_sql: str | None = None) -> dict:
    """M2 — Verificación de restaurabilidad: restaura el backup en una BD TEMPORAL
    aislada (nunca la activa), comprueba que tiene tablas y la elimina. No altera datos
    de producción. Devuelve {ok, tablas, db_tmp, error?}."""
    if ruta_sql is None:
        bks = listar_backups()
        if not bks:
            return {"ok": False, "error": "no hay backups"}
        ruta_sql = bks[0]["ruta"]
    db_tmp = f"sm_verify_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    out = {"ok": False, "db_tmp": db_tmp, "ruta": ruta_sql, "tablas": 0}
    import pymysql
    cfg = {k: v for k, v in DB_CONFIG.items() if k != "database"}
    try:
        r = restaurar_backup(ruta_sql, db=db_tmp)   # crea/restaura la BD temporal
        if r.get("resultado") != "ok":
            out["error"] = r.get("error", "restauración fallida")
            return out
        conn = pymysql.connect(**cfg)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s",
                            (db_tmp,))
                n = cur.fetchone()
                out["tablas"] = int((n[0] if not isinstance(n, dict) else list(n.values())[0]) or 0)
            out["ok"] = out["tablas"] > 0
        finally:
            conn.close()
        return out
    except Exception as e:
        logger.error("verificar_backup: %s", e)
        out["error"] = str(e)[:200]
        return out
    finally:
        # Limpieza garantizada de la BD temporal.
        try:
            conn2 = pymysql.connect(**cfg)
            with conn2.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS `{db_tmp}`")
            conn2.commit(); conn2.close()
        except Exception:
            pass


def restaurar_backup(ruta_sql: str, db: str | None = None) -> dict:
    """Restaura un backup `.sql` en la base `db` (por defecto, la activa). Usa el
    cliente `mysql` si está disponible; si no, restauración portable vía PyMySQL.
    Devuelve {resultado, metodo, db, ruta}."""
    db = db or DB_CONFIG.get("database", "")
    res = {"ruta": ruta_sql, "db": db, "metodo": None, "resultado": "error"}
    if not ruta_sql or not os.path.exists(ruta_sql):
        res["error"] = "backup inexistente"
        return res
    try:
        if _mysql_cli(ruta_sql, db):
            res.update(metodo="mysql_cli", resultado="ok")
        elif _restaurar_pymysql(ruta_sql, db):
            res.update(metodo="pymysql", resultado="ok")
    except Exception as e:
        logger.error("restaurar_backup: %s", e)
        res["error"] = str(e)[:200]
    try:
        from src.utils.observabilidad import registrar_evento
        registrar_evento("restore", "restauración completada" if res["resultado"] == "ok"
                         else "restauración fallida",
                         nivel=("info" if res["resultado"] == "ok" else "error"),
                         metodo=res.get("metodo"), db=db)
    except Exception:
        pass
    return res
