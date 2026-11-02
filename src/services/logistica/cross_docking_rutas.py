"""
Cross-docking a RUTAS DE REPARTO (petición explícita: automatizar el flujo de salida Producción ->
Logística -> Reparto). Distinto y complementario al cross-dock YA EXISTENTE
(`services/expediciones.py::aplicar_cross_docking`), que empareja una recepción con DEMANDA DE VENTA
pendiente (pedido cliente/online/B2B) — este módulo empareja un `documento_logistico` (originado por
Producción o por un Traspaso) con una RUTA/CAMIÓN de `services.transporte` que ya va hacia el mismo
centro destino, evitando que la mercancía pase por estantería. Migración 0321 (columnas de enlace).

Reutiliza tal cual: `db.logistica` (tabla/documento), `services.transporte` (rutas/paradas),
`db.kardex` (movimiento CROSS_DOCKING, ya existía como tipo), `db.stock_almacen` (descuento del
almacén de origen — la mercancía sale físicamente hacia el camión, igual que
`registrar_documento_traspaso_pedido_online` descuenta el origen con `decrementar_stock`, NUNCA
`traspasar_stock`, porque el destino no es un almacén con ficha propia sino "en el camión"),
`services.eventos` (bus ya existente, primer consumidor/productor real de logística).
"""

import logging

from src.db.conexion import obtener_conexion, transaccion

logger = logging.getLogger("logistica.cross_docking_rutas")

_RUTAS_ABIERTAS = ("planificada", "en_ruta")


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


def buscar_ruta_disponible_para_centro(id_centro_destino, *, id_empresa=None) -> dict | None:
    """Primera ruta/parada ABIERTA (`planificada`/`en_ruta`, nunca `cerrada`) que ya va hacia
    `id_centro_destino`, la más próxima en fecha (petición explícita: "el primer camión o ruta
    disponible"). `None` si no hay ninguna — caso normal, no es un error."""
    emp = _emp(id_empresa)
    if not id_centro_destino or not emp:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT r.id AS id_ruta, r.fecha, r.id_vehiculo, r.conductor, r.estado, "
                "p.id AS id_parada, p.cliente, p.direccion "
                "FROM transporte_rutas r JOIN transporte_paradas p ON p.id_ruta = r.id "
                "WHERE r.id_empresa=%s AND p.id_centro_destino=%s AND p.estado='pendiente' "
                "AND r.estado IN ('planificada','en_ruta') "
                "ORDER BY r.fecha ASC, r.id ASC LIMIT 1",
                (emp, id_centro_destino))
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            return dict(zip(cols, row)) if row else None
    except Exception as e:
        logger.error("buscar_ruta_disponible_para_centro(%s): %s", id_centro_destino, e)
        return None


def _lineas_documento(id_documento, *, id_empresa=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT codigo_articulo, nombre_articulo, cantidad_enviada FROM "
                "documentos_logisticos_lineas WHERE id_documento=%s", (id_documento,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error("_lineas_documento(%s): %s", id_documento, e)
        return []


def vincular_documento_a_ruta(id_documento, id_ruta, id_parada, *, id_empresa=None,
                              usuario=None) -> dict:
    """Vincula un `documento_logistico` a la ruta/parada encontrada: registra el cross-dock en el
    kárdex (tipo `CROSS_DOCKING`, ya existente — no se inventa un tipo nuevo), descuenta el almacén
    de ORIGEN del documento (la mercancía sale físicamente hacia el camión) y marca el documento como
    enlazado. Nunca lanza — best-effort, igual que el resto de la capa de kárdex/eventos."""
    emp = _emp(id_empresa)
    usuario = _usuario(usuario)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_almacen_origen FROM documentos_logisticos WHERE id_documento=%s",
                        (id_documento,))
            fila = cur.fetchone()
            id_almacen_origen = fila[0] if fila else None

        lineas = _lineas_documento(id_documento, id_empresa=emp)
        from src.db import kardex
        for ln in lineas:
            cod = ln.get("codigo_articulo")
            cant = int(ln.get("cantidad_enviada") or 0)
            if not cod or cant <= 0:
                continue
            if id_almacen_origen:
                try:
                    from src.db import stock_almacen as SA
                    SA.decrementar_stock(cod, id_almacen_origen, cant, id_empresa=emp)
                except Exception as e:
                    logger.warning("vincular_documento_a_ruta decrementar_stock(%s): %s", cod, e)
            kardex.registrar_movimiento(
                cod, "CROSS_DOCKING", cant, id_documento=id_documento, origen="PRODUCCION/LOGISTICA",
                destino=f"ruta:{id_ruta}", usuario=usuario, id_empresa=emp,
                id_almacen_origen=id_almacen_origen, idempotente=True,
                observaciones=f"Cross-docking automático a ruta de reparto #{id_ruta}")

        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE documentos_logisticos SET id_ruta=%s, id_parada=%s, estado='EN TRANSITO' "
                "WHERE id_documento=%s", (id_ruta, id_parada, id_documento))

        try:
            from src.services import eventos as _EV
            _EV.publicar("LOGISTICA_CROSS_DOCK_RUTA", id_empresa=emp, origen="logistica:cross_docking",
                         ref_entidad="documento_logistico", ref_id=id_documento,
                         payload={"id_ruta": id_ruta, "id_parada": id_parada})
        except Exception:
            pass

        return {"ok": True, "id_documento": id_documento, "id_ruta": id_ruta, "id_parada": id_parada}
    except Exception as e:
        logger.error("vincular_documento_a_ruta(%s): %s", id_documento, e)
        return {"ok": False, "error": "error_interno"}


def evaluar_cross_docking_automatico(id_documento, *, id_empresa=None, usuario=None) -> dict:
    """Punto de entrada único (petición explícita: "el sistema evaluará automáticamente"): dado un
    `documento_logistico` recién creado (desde Producción o desde un Traspaso) con un
    `id_centro_destino` ya fijado, busca una ruta/camión abierto hacia ese centro y, si existe, lo
    vincula de inmediato (evitando permanencia en almacén); si no hay ninguna ruta disponible, el
    documento queda igual que antes de esta función — pendiente de expedición normal, sin bloquear
    nada. Nunca lanza."""
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_centro_destino FROM documentos_logisticos WHERE id_documento=%s",
                        (id_documento,))
            fila = cur.fetchone()
        id_centro_destino = fila[0] if fila else None
        if not id_centro_destino:
            return {"ok": True, "cross_dockeado": False, "motivo": "sin_centro_destino"}
        ruta = buscar_ruta_disponible_para_centro(id_centro_destino, id_empresa=emp)
        if not ruta:
            return {"ok": True, "cross_dockeado": False, "motivo": "sin_ruta_disponible"}
        r = vincular_documento_a_ruta(id_documento, ruta["id_ruta"], ruta["id_parada"],
                                      id_empresa=emp, usuario=usuario)
        r["cross_dockeado"] = bool(r.get("ok"))
        r["ruta"] = ruta
        return r
    except Exception as e:
        logger.error("evaluar_cross_docking_automatico(%s): %s", id_documento, e)
        return {"ok": False, "cross_dockeado": False, "error": "error_interno"}


def validar_y_cerrar_expedicion(id_documento, *, usuario=None, id_empresa=None) -> dict:
    """Acción de un solo clic (petición explícita B.3): valida el albarán, confirma el stock como
    "en tránsito" (ya lo está desde el cross-dock — `estado='EN TRANSITO'`) y cierra la expedición.
    Idempotente: si ya estaba validado, no hace nada."""
    emp = _emp(id_empresa)
    usuario = _usuario(usuario)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT validado, estado FROM documentos_logisticos WHERE id_documento=%s",
                        (id_documento,))
            fila = cur.fetchone()
            if not fila:
                return {"ok": False, "error": "documento_no_encontrado"}
            if fila[0]:
                return {"ok": True, "ya_validado": True}
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE documentos_logisticos SET validado=1, estado='EN TRANSITO', "
                "usuario_receptor=COALESCE(usuario_receptor, %s) WHERE id_documento=%s",
                (usuario, id_documento))
        try:
            from src.db.conexion import log_auditoria
            log_auditoria("logistica", "EXPEDICION_VALIDADA", "documentos_logisticos", id_documento)
        except Exception:
            pass
        return {"ok": True, "ya_validado": False}
    except Exception as e:
        logger.error("validar_y_cerrar_expedicion(%s): %s", id_documento, e)
        return {"ok": False, "error": "error_interno"}


def documentos_cross_docking(id_empresa=None, *, limite=200) -> dict:
    """{'cross_dockeados': [...], 'pendientes': [...]} — alimenta la pestaña "Envío Directo" de
    Smart Logistics (petición explícita: "registrándose visualmente en la sección de Envío Directo /
    Cross-Docking"). `cross_dockeados` = documentos ya enlazados a una ruta (`id_ruta` no nulo);
    `pendientes` = documentos con centro destino fijado pero sin ruta disponible todavía (quedan
    pendientes de expedición normal, no es un error ni un bloqueo)."""
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT d.id_documento, d.tipo_documento, d.origen, d.destino, d.estado, d.validado, "
                "d.id_ruta, d.id_parada, d.fecha_creacion, r.fecha AS fecha_ruta, "
                "v.matricula, r.conductor "
                "FROM documentos_logisticos d "
                "LEFT JOIN transporte_rutas r ON r.id = d.id_ruta "
                "LEFT JOIN transporte_vehiculos v ON v.id = r.id_vehiculo "
                "WHERE d.id_empresa=%s AND d.id_ruta IS NOT NULL "
                "ORDER BY d.fecha_creacion DESC LIMIT %s", (emp, limite))
            cols = [c[0] for c in cur.description]
            cross_dockeados = [dict(zip(cols, r)) for r in cur.fetchall()]

            cur.execute(
                "SELECT id_documento, tipo_documento, origen, destino, estado, fecha_creacion "
                "FROM documentos_logisticos WHERE id_empresa=%s AND id_centro_destino IS NOT NULL "
                "AND id_ruta IS NULL AND estado IN ('PENDIENTE','EN PREPARACION') "
                "ORDER BY fecha_creacion DESC LIMIT %s", (emp, limite))
            cols2 = [c[0] for c in cur.description]
            pendientes = [dict(zip(cols2, r)) for r in cur.fetchall()]
        return {"cross_dockeados": cross_dockeados, "pendientes": pendientes}
    except Exception as e:
        logger.error("documentos_cross_docking: %s", e)
        return {"cross_dockeados": [], "pendientes": []}
