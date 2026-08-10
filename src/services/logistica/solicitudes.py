"""
Solicitudes de traspaso al ALMACÉN CENTRAL (LOGÍSTICA). Una tienda pide mercancía al central desde la función
de recepción; al servirse, el stock se mueve central→tienda con el motor OFICIAL de almacenes
(`db/stock_almacen.traspasar_stock` → kárdex TRASPASO). N7: no crea motor de stock paralelo. Multi-tenant.
"""

import logging

from src.db import stock_almacen as _alm
from src.db.conexion import _fila_a_dict, _filas_a_dicts, obtener_conexion

logger = logging.getLogger("logistica.solicitudes")

ESTADOS = ("PENDIENTE", "SERVIDA", "PARCIAL", "CANCELADA")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _usuario(usuario=None):
    if usuario:
        return usuario
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        return str(u.get("nombre") or u.get("usuario") or "") or None
    except Exception:
        return None


def crear_solicitud(id_tienda, items, *, id_empresa=None, usuario=None, observaciones=None) -> int | None:
    """Crea una solicitud PENDIENTE de la tienda al almacén central. `items` = [{'codigo','cantidad'}, …].
    Resuelve central y el almacén de la tienda con `stock_almacen`. Devuelve el id o None."""
    emp = _emp(id_empresa)
    if not emp or id_tienda is None:
        return None
    central = _alm.almacen_central(emp)
    destino = _alm.almacen_de_tienda(id_tienda, emp)
    if not central or not destino or central == destino:
        logger.debug("crear_solicitud: almacenes no resolubles (central=%s destino=%s)", central, destino)
        return None
    validos = []
    for it in items or []:
        cod = str(it.get("codigo") or "").strip()
        cant = int(it.get("cantidad") or 0)
        if cod and cant > 0:
            validos.append((cod, cant))
    if not validos:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO solicitudes_traspaso (id_empresa, id_tienda, almacen_origen, "
                        "almacen_destino, estado, usuario, observaciones) VALUES (%s,%s,%s,%s,'PENDIENTE',%s,%s)",
                        (emp, int(id_tienda), central, destino, _usuario(usuario), observaciones))
            sid = cur.lastrowid
            cur.executemany("INSERT INTO solicitudes_traspaso_items (id_solicitud, codigo_articulo, "
                            "cantidad_solicitada) VALUES (%s,%s,%s)",
                            [(sid, cod, cant) for cod, cant in validos])
            conn.commit()
        _audit(emp, "SOLICITUD_CENTRAL_CREADA", f"solicitud={sid} tienda={id_tienda} lineas={len(validos)}")
        return sid
    except Exception as e:
        logger.error("crear_solicitud: %s", e)
        return None


def listar_solicitudes(*, id_empresa=None, estado=None, id_tienda=None, limite=200) -> list:
    emp = _emp(id_empresa)
    if not emp:
        return []
    q = "SELECT * FROM solicitudes_traspaso WHERE id_empresa=%s"
    p = [emp]
    if estado:
        q += " AND estado=%s"
        p.append(estado)
    if id_tienda is not None:
        q += " AND id_tienda=%s"
        p.append(int(id_tienda))
    q += " ORDER BY id DESC LIMIT %s"
    p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, tuple(p))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_solicitudes: %s", e)
        return []


def obtener_solicitud(id_solicitud, *, id_empresa=None) -> dict | None:
    """Cabecera + líneas de la solicitud (aislada por empresa)."""
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM solicitudes_traspaso WHERE id=%s AND id_empresa=%s", (id_solicitud, emp))
            cab = _fila_a_dict(cur, cur.fetchone())
            if not cab:
                return None
            cur.execute("SELECT * FROM solicitudes_traspaso_items WHERE id_solicitud=%s ORDER BY id",
                        (id_solicitud,))
            cab["items"] = _filas_a_dicts(cur, cur.fetchall())
            return cab
    except Exception as e:
        logger.debug("obtener_solicitud: %s", e)
        return None


def servir_solicitud(id_solicitud, *, id_empresa=None, usuario=None) -> dict:
    """Sirve la solicitud moviendo del central a la tienda lo disponible (min(pendiente, stock central)) por
    `traspasar_stock`. Estado SERVIDA si se cubre todo, PARCIAL si no. Idempotente por línea (usa lo pendiente)."""
    emp = _emp(id_empresa)
    sol = obtener_solicitud(id_solicitud, id_empresa=emp)
    if not sol:
        return {"ok": False, "error": "solicitud no encontrada"}
    if sol["estado"] not in ("PENDIENTE", "PARCIAL"):
        return {"ok": False, "error": f"estado no servible: {sol['estado']}"}
    central, destino = sol["almacen_origen"], sol["almacen_destino"]
    usr = _usuario(usuario)
    movidas, completa = 0, True
    try:
        for it in sol["items"]:
            pendiente = int(it["cantidad_solicitada"]) - int(it["cantidad_servida"])
            if pendiente <= 0:
                continue
            disp = _alm.obtener_stock_almacen(it["codigo_articulo"], central, emp)
            mover = min(pendiente, disp)
            if mover <= 0:
                completa = False
                continue
            if _alm.traspasar_stock(it["codigo_articulo"], central, destino, mover, id_empresa=emp,
                                    id_documento=f"SOL-{id_solicitud}", usuario=usr):
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE solicitudes_traspaso_items SET cantidad_servida=cantidad_servida+%s "
                                "WHERE id=%s", (mover, it["id"]))
                    conn.commit()
                movidas += mover
                if mover < pendiente:
                    completa = False
            else:
                completa = False
        estado = "SERVIDA" if completa else "PARCIAL"
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE solicitudes_traspaso SET estado=%s, servido=NOW() WHERE id=%s AND id_empresa=%s",
                        (estado, id_solicitud, emp))
            conn.commit()
        _audit(emp, "SOLICITUD_CENTRAL_SERVIDA", f"solicitud={id_solicitud} movidas={movidas} estado={estado}")
        return {"ok": True, "estado": estado, "movidas": movidas}
    except Exception as e:
        logger.error("servir_solicitud: %s", e)
        return {"ok": False, "error": str(e)}


def cancelar_solicitud(id_solicitud, *, id_empresa=None) -> bool:
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE solicitudes_traspaso SET estado='CANCELADA' WHERE id=%s AND id_empresa=%s "
                        "AND estado IN ('PENDIENTE','PARCIAL')", (id_solicitud, emp))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("cancelar_solicitud: %s", e)
        return False


def sugerir_items(id_tienda, *, id_empresa=None, limite=100) -> list:
    """Sugiere líneas a pedir al central: artículos de la tienda por debajo de su objetivo, con la cantidad
    hasta el objetivo (reutiliza el reabastecimiento). Best-effort; lista vacía si no hay datos."""
    emp = _emp(id_empresa)
    try:
        from src.db import reabastecimiento as _re
        propuestas = _re.listar_propuestas(id_empresa=emp) or []
        out = []
        for p in propuestas[:limite]:
            cod = p.get("codigo") or p.get("codigo_articulo")
            cant = int(p.get("cantidad") or p.get("cantidad_sugerida") or 0)
            if cod and cant > 0:
                out.append({"codigo": cod, "cantidad": cant})
        return out
    except Exception as e:
        logger.debug("sugerir_items: %s", e)
        return []


def _audit(id_empresa, accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("logistica", accion, "solicitudes_traspaso", f"{id_empresa}: {detalle}")
    except Exception:
        pass
