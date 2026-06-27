"""
Backup por tenant (FASE SAAS-I).

Exporta los datos de UNA empresa (filtrados por id_empresa) a un JSON, para backup/restauración
parcial y portabilidad. Complementa el backup global (db/backup.py), que sigue intacto.
"""

import datetime as _dt
import json
import logging
import os

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("saas.backup_tenant")

# Tablas con dimensión id_empresa que se incluyen en el export por tenant (núcleo operativo).
_TABLAS = ["ventas", "venta_items", "facturas_cliente", "compras_facturas", "clientes",
           "proveedores", "movimientos_stock", "stock_almacen", "auditoria_logs",
           "contab_asientos", "contab_apuntes", "vencimientos", "movimientos_tesoreria",
           "cuentas_bancarias", "aeat_declaraciones", "wf_instancias", "notificaciones",
           "empresa_licencia", "suscripciones", "facturas_saas"]


def _dir():
    base = os.path.join("documentos", "backups_tenant")
    try:
        from src.utils.recursos import ruta_datos
        base = ruta_datos("backups_tenant")
    except Exception:
        pass
    os.makedirs(base, exist_ok=True)
    return base


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _tabla_tiene_columna(cur, tabla, columna):
    try:
        cur.execute(f"SHOW COLUMNS FROM {tabla} LIKE %s", (columna,))
        return cur.fetchone() is not None
    except Exception:
        return False


def exportar_empresa(id_empresa=None, *, tablas=None) -> dict:
    """Exporta a JSON los registros de la empresa. Devuelve {ruta, tablas, filas}."""
    id_empresa = _emp(id_empresa)
    tablas = tablas or _TABLAS
    data, total = {}, 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for t in tablas:
                if not _tabla_tiene_columna(cur, t, "id_empresa"):
                    continue
                cur.execute(f"SELECT * FROM {t} WHERE id_empresa=%s", (id_empresa,))
                cols = [d[0] for d in cur.description]
                filas = [dict(zip(cols, r)) if not isinstance(r, dict) else r for r in cur.fetchall()]
                data[t] = filas
                total += len(filas)
    except Exception as e:
        logger.error("exportar_empresa: %s", e)
    ruta = os.path.join(_dir(), f"tenant_{id_empresa}_{_dt.datetime.now():%Y%m%d_%H%M%S}.json")
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"id_empresa": id_empresa, "fecha": _dt.datetime.now().isoformat(), "datos": data},
                      f, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("exportar_empresa/escribir: %s", e)
        return {"ruta": None, "tablas": len(data), "filas": total}
    _audit(id_empresa, total)
    return {"ruta": ruta, "tablas": len(data), "filas": total}


def _audit(id_empresa, filas):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("saas", "BACKUP_TENANT", "backups_tenant", f"{id_empresa}: {filas} filas")
    except Exception:
        pass


# ── Restauración por tenant (FASE P1.2) ──────────────────────────────────────
def importar_empresa(ruta, *, id_empresa=None, reemplazar=False) -> dict:
    """Restaura los datos de una empresa desde un JSON de exportar_empresa. Transaccional con
    ROLLBACK ante error. Si `reemplazar`, borra antes los registros existentes de cada tabla
    para esa empresa. Devuelve {ok, tablas, filas, error}. Auditado."""
    id_empresa = _emp(id_empresa)
    try:
        with open(ruta, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        return {"ok": False, "error": f"no se pudo leer: {e}"}
    datos = doc.get("datos", {})
    origen_emp = doc.get("id_empresa")
    res = {"ok": False, "tablas": 0, "filas": 0}
    try:
        from src.db.conexion import transaccion
    except Exception:
        transaccion = None
    try:
        ctx = transaccion() if transaccion else obtener_conexion()
        with ctx as conn, conn.cursor() as cur:
            for tabla, filas in datos.items():
                if not _tabla_tiene_columna(cur, tabla, "id_empresa"):
                    continue
                if reemplazar:
                    cur.execute(f"DELETE FROM {tabla} WHERE id_empresa=%s", (id_empresa,))
                for fila in filas:
                    fila = dict(fila)
                    fila["id_empresa"] = id_empresa          # re-tenantiza al destino
                    fila.pop("id", None)                      # deja autogenerar el PK
                    cols = list(fila.keys())
                    ph = ", ".join(["%s"] * len(cols))
                    try:
                        cur.execute(f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({ph})",
                                    [fila[c] for c in cols])
                        res["filas"] += 1
                    except Exception as e:
                        logger.debug("import fila %s: %s", tabla, e)
                res["tablas"] += 1
            conn.commit()
        res["ok"] = True
        _audit_restore(id_empresa, origen_emp, res["filas"])
    except Exception as e:
        logger.error("importar_empresa (rollback): %s", e)
        res["error"] = str(e)
    return res


def restaurar_empresa(ruta, id_empresa=None) -> dict:
    """Restauración completa (reemplazando los datos existentes de la empresa)."""
    return importar_empresa(ruta, id_empresa=id_empresa, reemplazar=True)


def _audit_restore(id_empresa, origen, filas):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("saas", "RESTORE_TENANT", "backups_tenant", f"{id_empresa} desde {origen}: {filas} filas")
    except Exception:
        pass
