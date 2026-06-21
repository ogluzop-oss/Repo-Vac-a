"""
Caja avanzada (VTA.7) — sesiones de caja y movimientos de efectivo.

Apertura/cierre de sesión por tienda/caja, entradas/salidas de efectivo, arqueo con
diferencia. Aditivo y complementario al Cierre Z (no lo sustituye). Multiempresa/multitienda.
Sin Qt.
"""

import datetime as _dt
import logging

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion, transaccion

logger = logging.getLogger("ventas.caja")

TIPOS_MOV = ("entrada", "salida", "venta", "retirada", "ingreso", "incidencia")


def _emp(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return id_empresa or EMPRESA_DEFAULT_ID


def _tienda(id_tienda=None):
    if id_tienda is not None:
        return id_tienda
    try:
        from src.db.empresa import tienda_actual_id
        return tienda_actual_id()
    except Exception:
        return None


def abrir_sesion(caja=None, fondo_inicial=0, id_tienda=None, usuario=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO caja_sesiones (id_empresa, id_tienda, caja, estado, "
                        "fondo_inicial, usuario_apertura) VALUES (%s,%s,%s,'abierta',%s,%s)",
                        (id_empresa, _tienda(id_tienda), caja, round(float(fondo_inicial or 0), 2),
                         usuario))
            return cur.lastrowid
    except Exception as e:
        logger.error("abrir_sesion: %s", e); return None


def registrar_movimiento(id_sesion, tipo, importe, concepto=None, usuario=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    if tipo not in TIPOS_MOV:
        tipo = "incidencia"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO caja_movimientos (id_empresa, id_sesion, tipo, importe, "
                        "concepto, usuario) VALUES (%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_sesion, tipo, round(float(importe or 0), 2), concepto, usuario))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("registrar_movimiento: %s", e); return None


def arqueo(id_sesion, id_empresa=None) -> dict:
    """Saldo esperado = fondo_inicial + entradas/ventas/ingresos - salidas/retiradas."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(fondo_inicial,0) FROM caja_sesiones WHERE id=%s AND id_empresa=%s",
                        (id_sesion, id_empresa))
            r = cur.fetchone()
            fondo = float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else 0
            cur.execute("SELECT tipo, COALESCE(SUM(importe),0) FROM caja_movimientos "
                        "WHERE id_sesion=%s AND id_empresa=%s GROUP BY tipo", (id_sesion, id_empresa))
            por_tipo = {(x[0] if not isinstance(x, dict) else list(x.values())[0]):
                        float((x[1] if not isinstance(x, dict) else list(x.values())[1]) or 0)
                        for x in cur.fetchall()}
        entradas = sum(por_tipo.get(t, 0) for t in ("entrada", "venta", "ingreso"))
        salidas = sum(por_tipo.get(t, 0) for t in ("salida", "retirada"))
        return {"fondo_inicial": fondo, "entradas": round(entradas, 2), "salidas": round(salidas, 2),
                "esperado": round(fondo + entradas - salidas, 2), "por_tipo": por_tipo}
    except Exception as e:
        logger.error("arqueo: %s", e); return {"esperado": 0.0}


def cerrar_sesion(id_sesion, importe_declarado, usuario=None, id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    a = arqueo(id_sesion, id_empresa)
    declarado = round(float(importe_declarado or 0), 2)
    diferencia = round(declarado - a.get("esperado", 0), 2)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE caja_sesiones SET estado='cerrada', importe_declarado=%s, "
                        "diferencia=%s, usuario_cierre=%s, fecha_cierre=%s WHERE id=%s AND id_empresa=%s",
                        (declarado, diferencia, usuario, _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                         id_sesion, id_empresa))
        return {"esperado": a.get("esperado", 0), "declarado": declarado, "diferencia": diferencia}
    except Exception as e:
        logger.error("cerrar_sesion: %s", e); return {"diferencia": None}


def obtener_sesion(id_sesion, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM caja_sesiones WHERE id=%s AND id_empresa=%s", (id_sesion, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_sesion: %s", e); return None


def sesiones_abiertas(id_empresa=None, id_tienda=None) -> list:
    id_empresa = _emp(id_empresa)
    cond, params = ["id_empresa=%s", "estado='abierta'"], [id_empresa]
    if id_tienda is not None:
        cond.append("id_tienda=%s"); params.append(id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM caja_sesiones WHERE {' AND '.join(cond)} ORDER BY id DESC", params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("sesiones_abiertas: %s", e); return []
