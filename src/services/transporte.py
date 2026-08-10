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
def crear_vehiculo(matricula, descripcion=None, capacidad_kg=None, conductor=None, id_empresa=None) -> int | None:
    """Da de alta un vehículo. Best-effort: lo registra también como ACTIVO GMAO (tipo 'vehiculo') para que su
    mantenimiento (OT/preventivo) reutilice GMAO, guardando `id_activo`."""
    emp = _emp(id_empresa)
    matricula = (matricula or "").strip()
    if not matricula:
        return None
    id_activo = None
    try:
        from src.services.gmao import activos as _A
        id_activo = _A.crear_activo(matricula, descripcion or f"Vehículo {matricula}",
                                    tipo="vehiculo", id_empresa=emp)
    except Exception as e:
        logger.debug("crear_vehiculo GMAO activo: %s", e)
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


def listar_vehiculos(id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transporte_vehiculos WHERE id_empresa=%s ORDER BY id DESC", (emp,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_vehiculos: %s", e)
        return []


# ── Rutas de reparto ──────────────────────────────────────────────────────────
def _fecha(f):
    if isinstance(f, (_dt.date, _dt.datetime)):
        return f.strftime("%Y-%m-%d")
    return str(f)[:10] if f else _dt.date.today().strftime("%Y-%m-%d")


def crear_ruta(fecha=None, id_vehiculo=None, conductor=None, paradas=None, id_empresa=None,
               usuario=None) -> int | None:
    """Crea una ruta 'planificada' con sus paradas y líneas. `paradas` = [{cliente, direccion,
    lineas:[{codigo, cantidad}]}]."""
    emp = _emp(id_empresa)
    fecha = _fecha(fecha)
    paradas = paradas or []
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO transporte_rutas (id_empresa, fecha, id_vehiculo, conductor, estado, "
                        "usuario) VALUES (%s,%s,%s,%s,'planificada',%s)",
                        (emp, fecha, id_vehiculo, conductor, _usuario(usuario)))
            id_ruta = cur.lastrowid
            for i, p in enumerate(paradas, start=1):
                cur.execute("INSERT INTO transporte_paradas (id_ruta, id_empresa, orden, cliente, direccion) "
                            "VALUES (%s,%s,%s,%s,%s)",
                            (id_ruta, emp, p.get("orden", i), p.get("cliente"), p.get("direccion")))
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


def listar_rutas(id_empresa=None, fecha=None) -> list:
    emp = _emp(id_empresa)
    cond, params = ["id_empresa=%s"], [emp]
    if fecha is not None:
        cond.append("fecha=%s"); params.append(_fecha(fecha))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transporte_rutas WHERE " + " AND ".join(cond)
                        + " ORDER BY fecha DESC, id DESC", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_rutas: %s", e)
        return []


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
