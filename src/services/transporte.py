"""
Transporte / Flota + rutas de reparto (función base `transporte.reparto`, R8).

Gestión de FLOTA (vehículos; se enlazan a un activo GMAO para su mantenimiento) y RUTAS de reparto con
paradas y líneas. Al ENTREGAR una parada, la mercancía sale del stock por la política ÚNICA
(`db/salida_stock.salida_stock_oficial` → clamp + kárdex `SALIDA_REPARTO` + FEFO, idempotente). Reutiliza
los motores de stock GENERALES (N7 — sin lógica de stock paralela). Multi-tenant por `id_empresa`.

Es una FUNCIÓN BASE gateada por versión (`verticales.visible("transporte.reparto")`, visible en Supermarket/
Retail/Pharmacy); el servicio en sí es general.
"""

import datetime as _dt
import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion,
                             transaccion)

logger = logging.getLogger("transporte")


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


# ── Flota (vehículos; enlazados a GMAO para mantenimiento) ────────────────────
def _crear_activo_gmao_vehiculo(matricula, descripcion, coste_adquisicion, id_empresa) -> int | None:
    from src.services.gmao import activos as _A
    return _A.crear_activo(matricula, descripcion or f"Vehículo {matricula}",
                           tipo="vehiculo", fecha_compra=_dt.date.today().strftime("%Y-%m-%d"),
                           coste_adquisicion=coste_adquisicion or 0, id_empresa=id_empresa)


def crear_vehiculo(matricula, descripcion=None, capacidad_kg=None, conductor=None, coste_adquisicion=0,
                   id_empresa=None) -> int | None:
    """Da de alta un vehículo. Best-effort: lo registra también como ACTIVO GMAO (tipo 'vehiculo') para que su
    mantenimiento (OT/preventivo) reutilice GMAO, guardando `id_activo`. `coste_adquisicion` (precio de compra,
    obligatorio en la GUI) se persiste en el propio activo GMAO (`activos.coste_adquisicion`/`fecha_compra`) —
    misma tabla/columna que maquinaria, para que `gmao.activos.gastos_activos_periodo` lo recoja igual.

    El enlace es best-effort A PROPÓSITO (un fallo puntual de GMAO no debe impedir dar de alta el
    vehículo), pero un vehículo sin `id_activo` queda invisible en Mantenimiento — por eso
    `listar_vehiculos` repara el enlace de forma perezosa en cada lectura (ver `_reparar_vinculo_gmao`),
    así cualquier vehículo que se quedara sin enlazar (fallo transitorio, o de antes de este cableado)
    termina apareciendo en GMAO sin intervención manual."""
    emp = _emp(id_empresa)
    matricula = (matricula or "").strip()
    if not matricula:
        return None
    id_activo = None
    try:
        id_activo = _crear_activo_gmao_vehiculo(matricula, descripcion, coste_adquisicion, emp)
    except Exception as e:
        logger.warning("crear_vehiculo GMAO activo: %s", e)
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO transporte_vehiculos (id_empresa, matricula, descripcion, capacidad_kg, "
                        "conductor, id_activo) VALUES (%s,%s,%s,%s,%s,%s)",
                        (emp, matricula, descripcion, capacidad_kg, conductor, id_activo))
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_vehiculo: %s", e)
        return None


def _reparar_vinculo_gmao(vehiculos: list, id_empresa) -> None:
    """Auto-reparación (pedido explícito — Reparto y Mantenimiento deben quedar siempre cableados):
    cualquier vehículo listado con `id_activo` ausente (creación anterior a este cableado, o un fallo
    puntual de GMAO en su momento) se enlaza AHORA a un activo GMAO tipo 'vehiculo' — mismo criterio
    que la creación normal, reutilizando `crear_activo` (que ya es idempotente por `codigo`/matrícula
    vía `ON DUPLICATE KEY UPDATE`, nunca duplica el activo si ya existe). Muta `vehiculos` in-place y
    persiste el enlace; nunca lanza — un fallo de reparación no debe romper el listado."""
    for v in vehiculos:
        if v.get("id_activo"):
            continue
        matricula = (v.get("matricula") or "").strip()
        if not matricula:
            continue
        try:
            id_activo = _crear_activo_gmao_vehiculo(matricula, v.get("descripcion"), 0, id_empresa)
            if not id_activo:
                continue
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE transporte_vehiculos SET id_activo=%s WHERE id=%s",
                            (id_activo, v["id"]))
                conn.commit()
            v["id_activo"] = id_activo
        except Exception as e:
            logger.warning("_reparar_vinculo_gmao vehiculo=%s: %s", v.get("id"), e)


def listar_vehiculos(id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transporte_vehiculos WHERE id_empresa=%s ORDER BY id DESC", (emp,))
            vehiculos = _filas_a_dicts(cur, cur.fetchall())
        if any(not v.get("id_activo") for v in vehiculos):
            _reparar_vinculo_gmao(vehiculos, emp)
        return vehiculos
    except Exception as e:
        logger.error("listar_vehiculos: %s", e)
        return []


# ── Rutas de reparto ──────────────────────────────────────────────────────────
def _fecha(f):
    if isinstance(f, (_dt.date, _dt.datetime)):
        return f.strftime("%Y-%m-%d")
    return str(f)[:10] if f else _dt.date.today().strftime("%Y-%m-%d")


def crear_ruta(fecha=None, id_vehiculo=None, conductor=None, paradas=None, id_empresa=None,
               usuario=None, id_conductor=None) -> int | None:
    """Crea una ruta 'planificada' con sus paradas y líneas. `paradas` = [{cliente, direccion,
    lineas:[{codigo, cantidad}], id_centro_destino?, id_almacen_destino?}]. `id_centro_destino`
    (migr. 0321, petición explícita de cross-docking automático): enlaza la parada a un centro
    REGISTRADO (`db.centros`), para que Producción/Logística puedan encontrar "una ruta ya va hacia
    este centro" sin tener que interpretar texto libre de `direccion`. `id_conductor` (INT, opcional)
    enlaza la ruta a un usuario para que el móvil pueda filtrar "mis rutas" — `conductor` (texto)
    sigue siendo el nombre mostrado."""
    emp = _emp(id_empresa)
    fecha = _fecha(fecha)
    paradas = paradas or []
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO transporte_rutas (id_empresa, fecha, id_vehiculo, conductor, "
                        "id_conductor, estado, usuario) VALUES (%s,%s,%s,%s,%s,'planificada',%s)",
                        (emp, fecha, id_vehiculo, conductor, id_conductor, _usuario(usuario)))
            id_ruta = cur.lastrowid
            for i, p in enumerate(paradas, start=1):
                cur.execute("INSERT INTO transporte_paradas (id_ruta, id_empresa, orden, cliente, "
                            "direccion, id_centro_destino, id_almacen_destino) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (id_ruta, emp, p.get("orden", i), p.get("cliente"), p.get("direccion"),
                             p.get("id_centro_destino"), p.get("id_almacen_destino")))
                id_parada = cur.lastrowid
                for l in (p.get("lineas") or []):
                    cod = (l.get("codigo") or l.get("codigo_articulo") or "").strip()
                    if not cod:
                        continue
                    cur.execute("INSERT INTO transporte_paradas_lineas (id_parada, id_empresa, "
                                "codigo_articulo, cantidad) VALUES (%s,%s,%s,%s)",
                                (id_parada, emp, cod, int(l.get("cantidad") or 0)))
            return id_ruta
    except Exception as e:
        logger.error("crear_ruta: %s", e)
        return None


def iniciar_ruta(id_ruta, id_empresa=None) -> bool:
    emp = _emp(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE transporte_rutas SET estado='en_ruta' WHERE id=%s AND id_empresa=%s "
                        "AND estado='planificada'", (id_ruta, emp))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("iniciar_ruta: %s", e)
        return False


def entregar_parada(id_parada, id_empresa=None, usuario=None) -> dict:
    """Entrega una parada: por cada línea DESCUENTA stock por la política ÚNICA (kárdex SALIDA_REPARTO,
    idempotente por documento). Marca la parada 'entregada'. Idempotente (si ya estaba entregada, no repite)."""
    emp = _emp(id_empresa)
    usuario = _usuario(usuario)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transporte_paradas WHERE id=%s AND id_empresa=%s", (id_parada, emp))
            parada = _fila_a_dict(cur, cur.fetchone())
            if not parada:
                return {"ok": False, "error": "Parada no encontrada.", "entregadas": 0}
            if parada.get("estado") == "entregada":
                return {"ok": True, "entregadas": 0, "ya": True}
            cur.execute("SELECT * FROM transporte_paradas_lineas WHERE id_parada=%s AND id_empresa=%s",
                        (id_parada, emp))
            lineas = _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("entregar_parada/leer: %s", e)
        return {"ok": False, "error": str(e), "entregadas": 0}

    from src.db.salida_stock import salida_stock_oficial
    entregadas = 0
    faltante_total = 0
    for l in lineas:
        cod = l.get("codigo_articulo")
        cant = int(l.get("cantidad") or 0)
        if not cod or cant <= 0:
            continue
        try:
            r = salida_stock_oficial(cod, cant, id_documento=f"reparto:{id_parada}:{cod}",
                                     id_empresa=emp, tipo="SALIDA_REPARTO", contexto="reparto",
                                     usuario=usuario, observaciones=f"Reparto parada {id_parada}")
            faltante_total += int((r or {}).get("faltante") or 0)
            entregadas += 1
        except Exception as e:
            logger.error("entregar_parada/salida %s: %s", cod, e)

    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE transporte_paradas_lineas SET entregado=cantidad WHERE id_parada=%s "
                        "AND id_empresa=%s", (id_parada, emp))
            cur.execute("UPDATE transporte_paradas SET estado='entregada', entregado=%s WHERE id=%s "
                        "AND id_empresa=%s",
                        (_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), id_parada, emp))
    except Exception as e:
        logger.error("entregar_parada/marcar: %s", e)
        return {"ok": False, "error": str(e), "entregadas": entregadas}
    return {"ok": True, "entregadas": entregadas, "faltante": faltante_total}


def reportar_incidencia(id_parada, motivo, *, id_empresa=None, usuario=None) -> dict:
    """Registra que una parada NO se pudo entregar (cliente ausente/rechazo/dirección incorrecta/...).
    No toca stock (nada salió). Idempotente: si la parada ya está resuelta (entregada o con otra
    incidencia), no la vuelve a tocar."""
    emp = _emp(id_empresa)
    motivo = (motivo or "").strip()
    if not motivo:
        return {"ok": False, "error": "El motivo de la incidencia es obligatorio."}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT estado FROM transporte_paradas WHERE id=%s AND id_empresa=%s",
                        (id_parada, emp))
            r = cur.fetchone()
            if not r:
                return {"ok": False, "error": "Parada no encontrada."}
            estado = r[0] if not isinstance(r, dict) else list(r.values())[0]
            if estado in ("entregada", "incidencia"):
                return {"ok": True, "ya": True}
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE transporte_paradas SET estado='incidencia', motivo_incidencia=%s "
                        "WHERE id=%s AND id_empresa=%s", (motivo, id_parada, emp))
        return {"ok": True}
    except Exception as e:
        logger.error("reportar_incidencia: %s", e)
        return {"ok": False, "error": str(e)}


def cerrar_ruta(id_ruta, id_empresa=None) -> dict:
    """Cierra la ruta si todas sus paradas están resueltas (entregada/incidencia)."""
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM transporte_paradas WHERE id_ruta=%s AND id_empresa=%s "
                        "AND estado NOT IN ('entregada','incidencia')", (id_ruta, emp))
            r = cur.fetchone()
            pendientes = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else 0
        if pendientes:
            return {"ok": False, "error": f"Quedan {pendientes} parada(s) sin entregar.", "pendientes": pendientes}
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE transporte_rutas SET estado='cerrada' WHERE id=%s AND id_empresa=%s",
                        (id_ruta, emp))
        return {"ok": True}
    except Exception as e:
        logger.error("cerrar_ruta: %s", e)
        return {"ok": False, "error": str(e)}


def listar_rutas(id_empresa=None, fecha=None, id_conductor=None) -> list:
    emp = _emp(id_empresa)
    cond, params = ["id_empresa=%s"], [emp]
    if fecha is not None:
        cond.append("fecha=%s"); params.append(_fecha(fecha))
    if id_conductor is not None:
        cond.append("id_conductor=%s"); params.append(id_conductor)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transporte_rutas WHERE " + " AND ".join(cond)
                        + " ORDER BY fecha DESC, id DESC", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_rutas: %s", e)
        return []


# ── Recogidas (pickup) a proveedor — RMA de autoservicio B2B ─────────────────
# Una recogida es conceptualmente la entrega INVERSA de una ruta de reparto (origen=nuestro almacén,
# destino=proveedor), pero NO se modela reutilizando literalmente `crear_ruta`/`entregar_parada`:
# esas dos funciones están construidas, de cabo a rabo, alrededor de una SALIDA de mercancía propia
# (`entregar_parada` llama a `salida_stock_oficial`, que vuelve a descontar stock). Forzar una
# recogida por ahí volvería a descontar stock que YA se descontó al aprobar el RMA
# (`db.compras.aprobar_devolucion`) — doble efecto, justo lo que CLAUDE.md prohíbe ("motores de
# stock paralelos"/efectos duplicados). Juicio documentado: se modela como un registro mínimo propio
# (`transporte_recogidas`, migración 0282) con la MISMA estructura simple (cabecera + máquina de
# estados) que ya usan `transporte_paradas`/`compras_devoluciones` — sin paradas múltiples, sin
# optimización de ruta, sin vehículo/conductor: una recogida de un RMA es un único punto, una única
# vez. Si en el futuro hiciera falta agrupar recogidas en una ruta real (varios RMA del mismo
# proveedor en un mismo viaje), ESO sí reutilizaría `transporte_rutas` como contenedor — no se ha
# construido aquí por no inventar una necesidad que nadie ha pedido todavía.
def generar_orden_recogida(id_devolucion, *, id_proveedor=None, id_tx=None,
                           direccion_origen=None, direccion_destino=None, notas=None,
                           id_empresa=None, usuario=None) -> int | None:
    """Genera la orden de recogida para un RMA ya APROBADO (`db.compras.aprobar_devolucion`): el
    proveedor retira la mercancía que ya se descontó de nuestro almacén. Si no se indican
    direcciones, resuelve `direccion_origen` (nuestra empresa, `db.empresa.info_documento` — misma
    fuente única que usan los generadores de documentos) y `direccion_destino` (el proveedor,
    `db.proveedores.obtener_proveedor().direccion_fiscal`) best-effort; nunca bloquea la creación de
    la orden si una dirección no se pudo resolver (se deja en blanco, honesto, en vez de inventar
    una)."""
    emp = _emp(id_empresa)
    if not direccion_origen:
        try:
            from src.db.empresa import info_documento
            direccion_origen = info_documento(id_empresa=emp).get("direccion_completa") or None
        except Exception:
            direccion_origen = None
    if not direccion_destino and id_proveedor:
        try:
            from src.db.proveedores import obtener_proveedor
            prov = obtener_proveedor(id_proveedor, id_empresa=emp)
            direccion_destino = (prov or {}).get("direccion_fiscal") or None
        except Exception:
            direccion_destino = None
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO transporte_recogidas (id_empresa, id_devolucion, id_tx, id_proveedor, "
                "direccion_origen, direccion_destino, notas, usuario) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (emp, id_devolucion, id_tx, id_proveedor, direccion_origen, direccion_destino,
                 notas, _usuario(usuario)))
            return cur.lastrowid
    except Exception as e:
        logger.error("generar_orden_recogida: %s", e)
        return None


def marcar_recogida(id_recogida, id_empresa=None) -> bool:
    """pendiente → recogido (el transportista retira físicamente la mercancía)."""
    emp = _emp(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE transporte_recogidas SET estado='recogido', recogido_en=NOW() "
                        "WHERE id=%s AND id_empresa=%s AND estado='pendiente'", (id_recogida, emp))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("marcar_recogida: %s", e)
        return False


def marcar_recibida(id_recogida, id_empresa=None) -> bool:
    """recogido → recibido (el proveedor confirma la recepción de la mercancía devuelta)."""
    emp = _emp(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE transporte_recogidas SET estado='recibido', recibido_en=NOW() "
                        "WHERE id=%s AND id_empresa=%s AND estado='recogido'", (id_recogida, emp))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("marcar_recibida: %s", e)
        return False


def listar_recogidas(id_empresa=None, estado=None) -> list:
    emp = _emp(id_empresa)
    cond, params = ["id_empresa=%s"], [emp]
    if estado:
        cond.append("estado=%s"); params.append(estado)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transporte_recogidas WHERE " + " AND ".join(cond)
                        + " ORDER BY id DESC", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_recogidas: %s", e)
        return []


def obtener_recogida(id_recogida, id_empresa=None) -> dict | None:
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transporte_recogidas WHERE id=%s AND id_empresa=%s",
                        (id_recogida, emp))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_recogida: %s", e)
        return None


def obtener_ruta(id_ruta, id_empresa=None) -> dict | None:
    """Cabecera de la ruta + sus paradas (cada una con sus líneas)."""
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transporte_rutas WHERE id=%s AND id_empresa=%s", (id_ruta, emp))
            ruta = _fila_a_dict(cur, cur.fetchone())
            if not ruta:
                return None
            cur.execute("SELECT * FROM transporte_paradas WHERE id_ruta=%s AND id_empresa=%s ORDER BY orden, id",
                        (id_ruta, emp))
            paradas = _filas_a_dicts(cur, cur.fetchall())
            for p in paradas:
                cur.execute("SELECT * FROM transporte_paradas_lineas WHERE id_parada=%s AND id_empresa=%s",
                            (p["id"], emp))
                p["lineas"] = _filas_a_dicts(cur, cur.fetchall())
            ruta["paradas"] = paradas
            return ruta
    except Exception as e:
        logger.error("obtener_ruta: %s", e)
        return None
