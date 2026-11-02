"""
Capa de datos de COMPRAS (E2) — pedidos, recepción, costes, facturas, informes.

Ciclo: proveedor → pedido → recepción (stock + movimientos) → costes → factura.
Multiempresa por `id_empresa`. Reutiliza `articulos`/`movimientos_stock` existentes
sin romper TPV/stock/catálogo. Operaciones que mueven stock son ATÓMICAS
(`transaccion()`).

Este módulo crece por subfases (E2.2 pedidos; E2.3 recepción; E2.4 costes;
E2.5 facturas; E2.6 informes).
"""

import logging
import uuid as _uuid

from src.db.conexion import (EMPRESA_DEFAULT_ID, _fila_a_dict, _filas_a_dicts,
                             ensure_schema, obtener_conexion, transaccion)

logger = logging.getLogger("compras_db")

ESTADOS_PEDIDO = ("BORRADOR", "ENVIADO", "PARCIAL", "RECIBIDO", "CANCELADO")
# Transiciones permitidas.
_TRANSICIONES = {
    "BORRADOR": {"ENVIADO", "CANCELADO"},
    "ENVIADO": {"PARCIAL", "RECIBIDO", "CANCELADO"},
    "PARCIAL": {"PARCIAL", "RECIBIDO", "CANCELADO"},
    "RECIBIDO": set(),
    "CANCELADO": set(),
}


def _empresa(id_empresa=None):
    # IOC v3 (Bloque V): seam de identidad delegado en la fachada de datos (db -> db).
    try:
        from src.db.identidad_contexto import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        if id_empresa:
            return id_empresa
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return EMPRESA_DEFAULT_ID


def _hoy():
    import datetime as _dt
    return _dt.date.today().strftime("%Y-%m-%d")


# ── Pedidos de compra (E2.2) ─────────────────────────────────────────────────
def crear_pedido(id_proveedor=None, lineas=None, observaciones=None, usuario=None,
                 id_empresa=None, id_almacen=None, descuento=None,
                 origen_flujo: str | None = None) -> int | None:
    """Crea un pedido en BORRADOR con sus líneas. `lineas`: [{codigo, descripcion,
    cantidad, precio_unitario}]. Calcula subtotales y total. CMP.2: dirige el pedido a
    `id_almacen` (destino) y aplica el `descuento` del proveedor (si no se indica, toma el
    de su ficha). Un proveedor BLOQUEADO no puede generar pedidos (devuelve None).

    `origen_flujo` (opcional): distingue el CIRCUITO que originó el pedido (p.ej.
    "reposicion" desde el auto-aprovisionamiento) para el evento de actividad. Si no se
    indica, se mantiene el `origen="compras"` genérico (compatibilidad total con el resto
    de llamadores: GUI manual, ecommerce, compras_pro)."""
    id_empresa = _empresa(id_empresa)
    lineas = lineas or []
    # CMP.2: validar proveedor no bloqueado + condiciones comerciales.
    if id_proveedor:
        try:
            from src.db import proveedores
            if proveedores.esta_bloqueado(id_proveedor, id_empresa):
                logger.warning("crear_pedido: proveedor %s BLOQUEADO", id_proveedor)
                return None
            if descuento is None:
                cond = proveedores.condiciones_comerciales(id_proveedor, id_empresa)
                descuento = float(cond.get("descuento") or 0)
        except Exception:
            pass
    descuento = float(descuento or 0)
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO compras_pedidos (id_empresa, id_proveedor, estado, "
                "observaciones, usuario, id_almacen, descuento) VALUES (%s,%s,'BORRADOR',%s,%s,%s,%s)",
                (id_empresa, id_proveedor, observaciones, usuario, id_almacen, descuento))
            pid = cur.lastrowid
            # Código de referencia (numero) + UUID único de pedido (trazabilidad QR, migr 0211).
            cur.execute("UPDATE compras_pedidos SET numero=%s, uuid=%s WHERE id_pedido=%s",
                        (f"PC{pid:06d}", str(_uuid.uuid4()), pid))
            bruto = _insertar_lineas(cur, pid, lineas)
            total = round(bruto * (1 - descuento / 100.0), 2)
            cur.execute("UPDATE compras_pedidos SET total=%s WHERE id_pedido=%s", (total, pid))
        # Fase 2 (motor de eventos/distribucion): publicacion OBSERVACIONAL, aditiva y bulletproof.
        try:
            from src.services import eventos as _EV
            # `origen="compras:<origen_flujo>"` cuando el llamador lo indica (p.ej. el
            # auto-aprovisionamiento pasa "reposicion"): `crear_pedido` es compartida por la GUI
            # manual, ecommerce y compras_pro, y por defecto (`origen_flujo=None`) se mantiene el
            # `origen="compras"` genérico de siempre — cero cambio para esos llamadores.
            _EV.publicar("PEDIDO_RECIBIDO", id_empresa=id_empresa,
                         origen=(f"compras:{origen_flujo}" if origen_flujo else "compras"),
                         ref_entidad="compras_pedido", ref_id=pid,
                         payload={"id_proveedor": id_proveedor, "total": total})
        except Exception:
            pass
        return pid
    except Exception as e:
        logger.error("crear_pedido: %s", e)
        return None


def _insertar_lineas(cur, id_pedido, lineas) -> float:
    total = 0.0
    for ln in lineas:
        cant = int(ln.get("cantidad") or 0)
        precio = round(float(ln.get("precio_unitario") or 0), 2)
        subtotal = round(cant * precio, 2)
        total += subtotal
        # pvp_sugerido (migr 0211): PVP dinámico calculado en la tramitación (coste × margen), opcional.
        pvp = ln.get("pvp_sugerido")
        pvp = round(float(pvp), 2) if pvp not in (None, "") else None
        cur.execute(
            "INSERT INTO compras_pedidos_lineas (id_pedido, codigo_articulo, descripcion, "
            "cantidad, precio_unitario, subtotal, pvp_sugerido) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (id_pedido, ln.get("codigo") or ln.get("codigo_articulo"),
             ln.get("descripcion"), cant, precio, subtotal, pvp))
    return round(total, 2)


def obtener_pedido(id_pedido, id_empresa=None) -> dict | None:
    """Cabecera + líneas del pedido."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_pedidos WHERE id_pedido=%s AND id_empresa=%s",
                        (id_pedido, id_empresa))
            cab = _fila_a_dict(cur, cur.fetchone())
            if not cab:
                return None
            cur.execute("SELECT * FROM compras_pedidos_lineas WHERE id_pedido=%s ORDER BY id",
                        (id_pedido,))
            cab["lineas"] = _filas_a_dicts(cur, cur.fetchall())
            return cab
    except Exception as e:
        logger.error("obtener_pedido(%s): %s", id_pedido, e)
        return None


def listar_pedidos(id_empresa=None, estado=None, id_proveedor=None, limite=500) -> list:
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if estado:
        filtros.append("estado=%s"); params.append(estado)
    if id_proveedor:
        filtros.append("id_proveedor=%s"); params.append(id_proveedor)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_pedidos WHERE " + " AND ".join(filtros)
                        + " ORDER BY id_pedido DESC LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_pedidos: %s", e)
        return []


def modificar_lineas(id_pedido, lineas, id_empresa=None) -> bool:
    """Reemplaza las líneas de un pedido (solo en BORRADOR) y recalcula el total."""
    id_empresa = _empresa(id_empresa)
    ped = obtener_pedido(id_pedido, id_empresa)
    if not ped or ped["estado"] != "BORRADOR":
        return False
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM compras_pedidos_lineas WHERE id_pedido=%s", (id_pedido,))
            total = _insertar_lineas(cur, id_pedido, lineas)
            cur.execute("UPDATE compras_pedidos SET total=%s WHERE id_pedido=%s", (total, id_pedido))
        return True
    except Exception as e:
        logger.error("modificar_lineas(%s): %s", id_pedido, e)
        return False


def cambiar_estado(id_pedido, nuevo_estado, id_empresa=None) -> bool:
    """Cambia el estado validando la transición permitida."""
    id_empresa = _empresa(id_empresa)
    if nuevo_estado not in ESTADOS_PEDIDO:
        return False
    ped = obtener_pedido(id_pedido, id_empresa)
    if not ped:
        return False
    if nuevo_estado != ped["estado"] and nuevo_estado not in _TRANSICIONES.get(ped["estado"], set()):
        logger.warning("Transición no permitida %s->%s (pedido %s)", ped["estado"], nuevo_estado, id_pedido)
        return False
    campos = "estado=%s"
    params = [nuevo_estado]
    if nuevo_estado == "ENVIADO":
        campos += ", fecha_envio=NOW()"
    if nuevo_estado == "RECIBIDO":
        campos += ", fecha_recepcion=NOW()"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE compras_pedidos SET {campos} WHERE id_pedido=%s AND id_empresa=%s",
                        (*params, id_pedido, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("cambiar_estado(%s): %s", id_pedido, e)
        return False


def enviar_pedido(id_pedido, id_empresa=None) -> bool:
    return cambiar_estado(id_pedido, "ENVIADO", id_empresa)


def enviar_todos_borradores(id_empresa=None, ids=None) -> dict:
    """Tramita EN LOTE todos los pedidos BORRADOR de la empresa (o solo los `ids` indicados): pasa cada
    uno a ENVIADO. Cada pedido se envía por separado (transacción propia en `cambiar_estado`), de modo
    que un fallo NO aborta el resto y no se colapsa con muchos pedidos de distintos proveedores.
    Devuelve {total, enviados, fallidos, ids_enviados}."""
    emp = _empresa(id_empresa)
    borradores = listar_pedidos(id_empresa=emp, estado="BORRADOR")
    if ids is not None:
        objetivo = {int(x) for x in ids}
        borradores = [p for p in borradores if int(p.get("id_pedido")) in objetivo]
    enviados, fallidos, ok_ids = 0, 0, []
    for p in borradores:
        pid = p.get("id_pedido")
        try:
            if enviar_pedido(pid, id_empresa=emp):
                enviados += 1; ok_ids.append(pid)
            else:
                fallidos += 1
        except Exception as e:
            logger.error("enviar_todos_borradores(%s): %s", pid, e)
            fallidos += 1
    return {"total": len(borradores), "enviados": enviados, "fallidos": fallidos, "ids_enviados": ok_ids}


def cancelar_pedido(id_pedido, id_empresa=None) -> bool:
    return cambiar_estado(id_pedido, "CANCELADO", id_empresa)


# ── Recepción contra pedido (E2.3) ───────────────────────────────────────────
def recibir(id_pedido, lineas_recibidas, usuario=None, observaciones=None,
            id_empresa=None) -> dict | None:
    """Registra una recepción (parcial o total) de un pedido. `lineas_recibidas`:
    [{id_linea|codigo, cantidad}]. Suma a cantidad_recibida, ACTUALIZA STOCK
    (articulos.Stock_total/Stock_central) y genera movimientos_stock. Recalcula el
    estado del pedido (PARCIAL/RECIBIDO). Todo ATÓMICO. Devuelve
    {id_recepcion, estado_pedido, unidades} o None."""
    id_empresa = _empresa(id_empresa)
    ped = obtener_pedido(id_pedido, id_empresa)
    if not ped or ped["estado"] not in ("ENVIADO", "PARCIAL"):
        logger.warning("recibir: pedido %s no recepcionable (estado %s)",
                       id_pedido, ped.get("estado") if ped else None)
        return None
    lineas_por_id = {ln["id"]: ln for ln in ped["lineas"]}
    # CMP.3: destino = almacén del pedido o, si no, el almacén central de la empresa.
    destino = ped.get("id_almacen")
    try:
        from src.db import stock_almacen as SA
        if not destino:
            destino = SA.almacen_central(id_empresa)
    except Exception:
        SA = None
    _entradas = []   # (codigo, cant, lote, caducidad, fabricacion, prov_origen)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO compras_recepciones (id_empresa, id_pedido, usuario, "
                        "observaciones) VALUES (%s,%s,%s,%s)",
                        (id_empresa, id_pedido, usuario, observaciones))
            rid = cur.lastrowid
            unidades = 0
            for rec in lineas_recibidas:
                cant = int(rec.get("cantidad") or 0)
                if cant <= 0:
                    continue
                lp = lineas_por_id.get(rec.get("id_linea"))
                if lp is None and rec.get("codigo"):
                    lp = next((x for x in ped["lineas"]
                               if x["codigo_articulo"] == rec["codigo"]), None)
                codigo = (lp or {}).get("codigo_articulo") or rec.get("codigo")
                id_linea = (lp or {}).get("id")
                lote = (rec.get("lote") or "").strip() or None
                caduc = rec.get("fecha_caducidad") or rec.get("caducidad")
                fabric = rec.get("fecha_fabricacion")
                prov_ori = rec.get("proveedor_origen")
                cur.execute("INSERT INTO compras_recepciones_lineas (id_recepcion, "
                            "id_linea_pedido, codigo_articulo, cantidad, lote, fecha_caducidad, "
                            "fecha_fabricacion, proveedor_origen, id_almacen) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (rid, id_linea, codigo, cant, lote, caduc, fabric, prov_ori, destino))
                if id_linea is not None:
                    cur.execute("UPDATE compras_pedidos_lineas SET cantidad_recibida="
                                "cantidad_recibida+%s WHERE id=%s", (cant, id_linea))
                if codigo:
                    precio = round(float((lp or {}).get("precio_unitario") or 0), 2)
                    cur.execute("SELECT COALESCE(Stock_total,0) FROM articulos WHERE codigo=%s",
                                (codigo,))
                    fila_prev = cur.fetchone()
                    stock_previo = (fila_prev[0] if fila_prev and not isinstance(fila_prev, dict)
                                    else (list(fila_prev.values())[0] if fila_prev else None))
                    if fila_prev is not None and precio > 0:
                        actualizar_costes_entrada(cur, codigo, int(stock_previo or 0), cant, precio,
                                                  id_empresa=id_empresa)
                    cur.execute(
                        "INSERT INTO movimientos_stock (codigo_articulo, tipo_movimiento, "
                        "cantidad, id_documento, origen, usuario, observaciones, id_almacen_destino) "
                        "VALUES (%s,'ENTRADA_COMPRA',%s,%s,%s,%s,%s,%s)",
                        (codigo, cant, f"PC{id_pedido}-R{rid}", "compra", usuario,
                         f"Recepción compra pedido {id_pedido}", destino))
                    _entradas.append((codigo, cant, lote, caduc, fabric, prov_ori))
                unidades += cant
            cur.execute("UPDATE compras_recepciones SET total_unidades=%s WHERE id_recepcion=%s",
                        (unidades, rid))
            cur.execute("SELECT SUM(GREATEST(cantidad-cantidad_recibida,0)) AS pendiente, "
                        "SUM(cantidad_recibida) AS recibido FROM compras_pedidos_lineas "
                        "WHERE id_pedido=%s", (id_pedido,))
            r = cur.fetchone()
            pendiente = (r["pendiente"] if isinstance(r, dict) else r[0]) or 0
            recibido = (r["recibido"] if isinstance(r, dict) else r[1]) or 0
            nuevo = "RECIBIDO" if pendiente == 0 else ("PARCIAL" if recibido > 0 else ped["estado"])
            extra = ", fecha_recepcion=NOW()" if nuevo == "RECIBIDO" else ""
            cur.execute(f"UPDATE compras_pedidos SET estado=%s{extra} WHERE id_pedido=%s",
                        (nuevo, id_pedido))
        # CMP.3: entrada de stock en el ALMACÉN DESTINO (stock_almacen = fuente de verdad,
        # recalcula la caché) + lote/caducidad (INV.3) + FEFO. Best-effort, tras commit.
        try:
            from src.db import stock_almacen as SA2, lotes as L
            for codigo, cant, lote, caduc, fabric, prov_ori in _entradas:
                SA2.incrementar_stock(codigo, destino, cant, id_empresa=id_empresa)
                if lote:
                    L.registrar_entrada(codigo, lote, cant, fecha_caducidad=caduc,
                                        id_empresa=id_empresa, id_almacen=destino,
                                        origen="compra", id_documento=f"PC{id_pedido}-R{rid}",
                                        usuario=usuario, id_recepcion_origen=rid)
        except Exception as e:
            logger.warning("recibir: sync multialmacén/lotes pedido %s: %s", id_pedido, e)
        return {"id_recepcion": rid, "estado_pedido": nuevo, "unidades": unidades,
                "id_almacen": destino}
    except Exception as e:
        logger.error("recibir(%s): %s", id_pedido, e)
        return None


def actualizar_costes_entrada(cur, codigo, stock_previo, cantidad, precio, *, id_empresa=None) -> None:
    """Actualiza costes del artículo tras una entrada de stock (E2.4; expuesta como función
    PÚBLICA reutilizable en Fase B — Landed Cost, antes privada como `_actualizar_costes`):
    último/actual = precio de la entrada; medio = media ponderada por existencias
    ((medio_old·stock_previo + precio·cantidad) / (stock_previo+cantidad)). Llamada por
    `recibir()` (compra vía pedido, único call site histórico — ahora pasa `id_empresa`
    explícitamente), por `services.compras.b2b_pedidos.recibir_mercancia()` (cierre del bug
    histórico: la recepción B2B nunca actualizaba coste_medio/coste_actual) y por
    `prorratear_costes_recepcion()` (recalculo con el coste LANDED). Filtra por `id_empresa`
    (bug multiempresa cerrado: el UPDATE no distinguía artículos homónimos de otra empresa) —
    IMPORTANTE: pásalo siempre que se conozca (como hacen los tres llamadores anteriores); sin
    él cae al contexto/empresa por defecto vía `_empresa()`, que en un entorno multiempresa real
    puede no ser la empresa del artículo que se está actualizando. Tolerante si faltan columnas
    (instalaciones antiguas sin migración 0011)."""
    id_empresa = _empresa(id_empresa)
    try:
        cur.execute("SELECT COALESCE(coste_medio,0) FROM articulos WHERE codigo=%s AND id_empresa=%s",
                    (codigo, id_empresa))
        r = cur.fetchone()
        medio_old = float((r[0] if r and not isinstance(r, dict) else
                           (list(r.values())[0] if r else 0)) or 0)
        prev = max(int(stock_previo or 0), 0)
        nuevo_total = prev + int(cantidad)
        medio = round(((medio_old * prev) + (precio * cantidad)) / nuevo_total, 2) if nuevo_total else precio
        cur.execute("UPDATE articulos SET ultimo_coste=%s, coste_actual=%s, coste_medio=%s "
                    "WHERE codigo=%s AND id_empresa=%s", (precio, precio, medio, codigo, id_empresa))
    except Exception as e:
        logger.debug("No se pudieron actualizar costes (%s): %s", codigo, e)


def obtener_costes(codigo) -> dict:
    """Costes de aprovisionamiento del artículo."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT ultimo_coste, coste_actual, coste_medio FROM articulos "
                        "WHERE codigo=%s", (codigo,))
            r = cur.fetchone()
            if not r:
                return {}
            if isinstance(r, dict):
                return {k: float(v or 0) for k, v in r.items()}
            return {"ultimo_coste": float(r[0] or 0), "coste_actual": float(r[1] or 0),
                    "coste_medio": float(r[2] or 0)}
    except Exception as e:
        logger.error("obtener_costes(%s): %s", codigo, e)
        return {}


def listar_recepciones(id_pedido, id_empresa=None) -> list:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_recepciones WHERE id_pedido=%s AND id_empresa=%s "
                        "ORDER BY id_recepcion", (id_pedido, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_recepciones(%s): %s", id_pedido, e)
        return []


# ── Facturas de proveedor (E2.5) ─────────────────────────────────────────────
def registrar_factura(id_proveedor=None, numero_factura=None, lineas=None,
                      id_pedido=None, id_recepcion=None, base=None, iva=None,
                      fecha_factura=None, observaciones=None, id_empresa=None,
                      tipo_documento="factura", id_factura_rectificada=None,
                      id_recepciones=None, retencion_pct=None, retencion_importe=None) -> int | None:
    """Registra una factura/abono/rectificativa de proveedor (CMP.5). Si no se pasan
    base/iva, base = suma de líneas e iva = 0. `id_recepciones` permite conciliación n:m.
    Los abonos/rectificativas se contabilizan en negativo.

    AEAT-3: retención IRPF de profesionales opcional. Si `retencion_pct`/`retencion_importe`,
    se almacena y el total a pagar = base + iva − retención. SIN retención el comportamiento
    es idéntico al anterior (total = base + iva)."""
    id_empresa = _empresa(id_empresa)
    lineas = lineas or []
    base_calc = round(sum(int(l.get("cantidad") or 0) * round(float(l.get("precio_unitario") or 0), 2)
                          for l in lineas), 2)
    base_f = round(float(base), 2) if base is not None else base_calc
    iva_f = round(float(iva or 0), 2)
    # Retención: si llega el importe se usa; si solo el %, se calcula sobre la base.
    ret_pct = round(float(retencion_pct or 0), 2)
    if retencion_importe is not None:
        ret_imp = round(float(retencion_importe), 2)
    elif ret_pct:
        ret_imp = round(base_f * ret_pct / 100, 2)
    else:
        ret_imp = 0.0
    # FASE C (simetría compras↔ventas): mismo motor ÚNICO de exención/ISP que ya usa
    # `facturas_cliente.crear_factura` (`utils/fiscalidad.calcular_fiscalidad`), aplicado aquí a
    # proveedores intracomunitarios/extracomunitarios (`proveedores.perfil_fiscal`). NO-OP para
    # proveedores domésticos (perfil general): `iva_f` no se toca, comportamiento IDÉNTICO al
    # actual (total = base + iva − retención).
    try:
        from src.utils import fiscalidad as _FISC
        from src.db import proveedores as _PROV
        _perfil = _PROV.perfil_fiscal(id_proveedor) if id_proveedor else None
    except Exception:
        _FISC = None
        _perfil = None
    if _FISC is not None and _perfil and (_perfil.get("exento") or _perfil.get("isp")
                                          or _perfil.get("intracomunitario")):
        _fisc = _FISC.calcular_fiscalidad([{"subtotal": base_f, "iva": 0}],
                                          perfil=_perfil, id_empresa=id_empresa)
        iva_f = round(float(_fisc.get("cuota") or 0), 2)   # exención/ISP real → IVA repercutido 0
    total_f = round(base_f + iva_f - ret_imp, 2)
    es_negativo = tipo_documento in ("abono", "rectificativa")
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO compras_facturas (id_empresa, id_proveedor, id_pedido, id_recepcion, "
                "numero_factura, fecha_factura, base, iva, total, observaciones, tipo_documento, "
                "id_factura_rectificada, retencion_pct, retencion_importe) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_proveedor, id_pedido, id_recepcion, numero_factura,
                 fecha_factura, base_f, iva_f, total_f, observaciones, tipo_documento,
                 id_factura_rectificada, ret_pct, ret_imp))
            fid = cur.lastrowid
            for _rid in (id_recepciones or []):   # conciliación n:m
                cur.execute("INSERT INTO compras_factura_recepciones (id_empresa, id_factura, "
                            "id_recepcion, importe) VALUES (%s,%s,%s,%s) "
                            "ON DUPLICATE KEY UPDATE importe=VALUES(importe)",
                            (id_empresa, fid, _rid, 0))
            for l in lineas:
                cant = int(l.get("cantidad") or 0)
                precio = round(float(l.get("precio_unitario") or 0), 2)
                cur.execute(
                    "INSERT INTO compras_facturas_lineas (id_factura, codigo_articulo, "
                    "descripcion, cantidad, precio_unitario, subtotal) VALUES (%s,%s,%s,%s,%s,%s)",
                    (fid, l.get("codigo") or l.get("codigo_articulo"), l.get("descripcion"),
                     cant, precio, round(cant * precio, 2)))
        # E6.5: encola el asiento de compra (no-op si la contabilidad está apagada).
        # CMP.5: abonos/rectificativas se contabilizan en negativo (signo invertido).
        try:
            from src.services.contabilidad.posting import encolar_compra
            signo = -1 if es_negativo else 1
            encolar_compra(fid, signo * total_f, fecha_factura or _hoy(), id_empresa=id_empresa,
                           base=signo * base_f, iva=signo * iva_f, subtipo=tipo_documento,
                           retencion=signo * ret_imp)
        except Exception:
            pass
        # Gobierno: lanza la cadena de aprobación por importe si aplica alguna regla sembrada
        # (p.ej. APR_FACTURA_10000) — antes esta cadena no se disparaba nunca para facturas de
        # proveedor, pese a existir. Best-effort: si Gobierno/Workflow no está disponible, no bloquea
        # el alta de la factura (ya contabilizada arriba).
        try:
            from src.services.gobierno import aprobaciones
            aprobaciones.iniciar_aprobacion("factura", fid, importe=total_f, id_empresa=id_empresa)
        except Exception as e:
            logger.debug("iniciar_aprobacion factura %s: %s", fid, e)
        return fid
    except Exception as e:
        logger.error("registrar_factura: %s", e)
        return None


def obtener_factura(id_factura, id_empresa=None) -> dict | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_facturas WHERE id_factura=%s AND id_empresa=%s",
                        (id_factura, id_empresa))
            cab = _fila_a_dict(cur, cur.fetchone())
            if not cab:
                return None
            cur.execute("SELECT * FROM compras_facturas_lineas WHERE id_factura=%s ORDER BY id",
                        (id_factura,))
            cab["lineas"] = _filas_a_dicts(cur, cur.fetchall())
            return cab
    except Exception as e:
        logger.error("obtener_factura(%s): %s", id_factura, e)
        return None


def listar_facturas(id_empresa=None, id_proveedor=None, id_pedido=None, limite=500) -> list:
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if id_proveedor:
        filtros.append("id_proveedor=%s"); params.append(id_proveedor)
    if id_pedido:
        filtros.append("id_pedido=%s"); params.append(id_pedido)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_facturas WHERE " + " AND ".join(filtros)
                        + " ORDER BY id_factura DESC LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_facturas: %s", e)
        return []


def validar_factura(id_factura, tolerancia=0.01, id_empresa=None) -> dict:
    """Valida la factura contra el total del pedido vinculado. Marca 'validada' si
    coincide (±tolerancia) o 'con_diferencias' si no. Devuelve el diagnóstico."""
    id_empresa = _empresa(id_empresa)
    fac = obtener_factura(id_factura, id_empresa)
    if not fac:
        return {"ok": False, "error": "factura inexistente"}
    referencia = None
    if fac.get("id_pedido"):
        ped = obtener_pedido(fac["id_pedido"], id_empresa)
        referencia = float(ped["total"]) if ped else None
    diff = None if referencia is None else round(float(fac["total"]) - referencia, 2)
    coincide = referencia is not None and abs(diff) <= tolerancia
    estado = "validada" if coincide else ("con_diferencias" if referencia is not None else "registrada")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE compras_facturas SET estado=%s WHERE id_factura=%s AND id_empresa=%s",
                        (estado, id_factura, id_empresa))
            conn.commit()
    except Exception as e:
        logger.error("validar_factura(%s): %s", id_factura, e)
    return {"ok": coincide, "estado": estado, "total_factura": float(fac["total"]),
            "total_pedido": referencia, "diferencia": diff}


# ── Informes de compras (E2.6) ───────────────────────────────────────────────
def _rango(cur_sql, params, desde, hasta, campo):
    if desde:
        cur_sql.append(f"{campo}>=%s"); params.append(desde)
    if hasta:
        cur_sql.append(f"{campo}<=%s"); params.append(hasta)


#: `compras_facturas.total` se guarda SIEMPRE en positivo (magnitud del documento), también para
#: abono/rectificativa — el signo real solo se aplicaba hasta ahora al asiento contable
#: (`encolar_compra`/`_asiento_compra`, ver `registrar_factura`). Los informes agregados de ESTA
#: sección (gasto NETO por proveedor/periodo) necesitan el mismo signo que ya usa esa contabilización
#: para no duplicar/invertir el efecto de un abono (p.ej. un rappel liquidado vía
#: `b2b_rappels.liquidar_rappel` → `registrar_abono`): sin este signo, un abono SUMABA en vez de
#: RESTAR el gasto agregado. `_SQL_TOTAL_NETO` centraliza la expresión para no repetirla/desincronizarla.
_SQL_TOTAL_NETO = ("CASE WHEN tipo_documento IN ('abono','rectificativa') THEN -total ELSE total END")


def compras_por_proveedor(desde=None, hasta=None, id_empresa=None) -> list:
    """Gasto NETO facturado por proveedor (facturas registradas, abonos/rectificativas en
    negativo — ver `_SQL_TOTAL_NETO`). [{id_proveedor, proveedor, facturas, total}]."""
    id_empresa = _empresa(id_empresa)
    filtros, params = ["f.id_empresa=%s"], [id_empresa]
    _rango(filtros, params, desde, hasta, "f.fecha_factura")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT f.id_proveedor, COALESCE(p.razon_social,'(sin proveedor)') AS proveedor, "
                f"COUNT(*) AS facturas, COALESCE(SUM({_SQL_TOTAL_NETO}),0) AS total "
                "FROM compras_facturas f LEFT JOIN proveedores p ON p.id_proveedor=f.id_proveedor "
                "WHERE " + " AND ".join(filtros) + " GROUP BY f.id_proveedor, proveedor "
                "ORDER BY total DESC", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("compras_por_proveedor: %s", e)
        return []


def compras_por_periodo(desde=None, hasta=None, id_empresa=None) -> list:
    """Gasto NETO facturado agrupado por mes (AAAA-MM), abonos/rectificativas en negativo (ver
    `_SQL_TOTAL_NETO`). [{periodo, facturas, total}]."""
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s", "fecha_factura IS NOT NULL"], [id_empresa]
    _rango(filtros, params, desde, hasta, "fecha_factura")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DATE_FORMAT(fecha_factura,'%%Y-%%m') AS periodo, COUNT(*) AS facturas, "
                f"COALESCE(SUM({_SQL_TOTAL_NETO}),0) AS total FROM compras_facturas WHERE "
                + " AND ".join(filtros) + " GROUP BY periodo ORDER BY periodo", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("compras_por_periodo: %s", e)
        return []


def costes_por_articulo(id_empresa=None, limite=500) -> list:
    """Compras por artículo (líneas de factura): unidades, gasto y precio medio.
    [{codigo_articulo, unidades, gasto, precio_medio}]."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT l.codigo_articulo, COALESCE(SUM(l.cantidad),0) AS unidades, "
                "COALESCE(SUM(l.subtotal),0) AS gasto FROM compras_facturas_lineas l "
                "JOIN compras_facturas f ON f.id_factura=l.id_factura "
                "WHERE f.id_empresa=%s AND l.codigo_articulo IS NOT NULL "
                "GROUP BY l.codigo_articulo ORDER BY gasto DESC LIMIT %s",
                (id_empresa, int(limite)))
            filas = _filas_a_dicts(cur, cur.fetchall())
        for r in filas:
            u = float(r.get("unidades") or 0)
            r["precio_medio"] = round(float(r.get("gasto") or 0) / u, 2) if u else 0.0
        return filas
    except Exception as e:
        logger.error("costes_por_articulo: %s", e)
        return []


def historico_pedidos(id_empresa=None, id_proveedor=None, limite=500) -> list:
    """Histórico de pedidos con nombre de proveedor."""
    id_empresa = _empresa(id_empresa)
    filtros, params = ["c.id_empresa=%s"], [id_empresa]
    if id_proveedor:
        filtros.append("c.id_proveedor=%s"); params.append(id_proveedor)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT c.id_pedido, c.numero, c.estado, c.total, c.fecha, "
                "COALESCE(p.razon_social,'') AS proveedor FROM compras_pedidos c "
                "LEFT JOIN proveedores p ON p.id_proveedor=c.id_proveedor "
                "WHERE " + " AND ".join(filtros) + " ORDER BY c.id_pedido DESC LIMIT %s",
                (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("historico_pedidos: %s", e)
        return []


def crear_pedido_desde_propuestas(propuesta_ids=None, id_proveedor=None, usuario=None,
                                  id_empresa=None, origen_flujo: str | None = None) -> int | None:
    """E2.7 — Convierte sugerencias de reabastecimiento (estado 'pendiente') en un
    pedido de compra BORRADOR. Reutiliza `reabastecimiento.listar_propuestas` y los
    costes del artículo como precio estimado; marca las propuestas como 'pedido'.
    Si `propuesta_ids` es None, toma todas las pendientes. `origen_flujo` (opcional) se
    reenvía a `crear_pedido` para distinguir el circuito en el evento de actividad."""
    try:
        from src.db import reabastecimiento as R
    except Exception as e:
        logger.error("reabastecimiento no disponible: %s", e)
        return None
    pendientes = R.listar_propuestas(("pendiente",))
    if propuesta_ids is not None:
        ids = set(propuesta_ids)
        pendientes = [p for p in pendientes if p["id"] in ids]
    if not pendientes:
        return None
    lineas = []
    for p in pendientes:
        costes = obtener_costes(p["codigo"]) or {}
        precio = costes.get("coste_actual") or costes.get("ultimo_coste") or 0
        lineas.append({"codigo": p["codigo"], "descripcion": p.get("nombre"),
                       "cantidad": int(p.get("cantidad") or 0), "precio_unitario": precio})
    pid = crear_pedido(id_proveedor=id_proveedor, lineas=lineas, usuario=usuario,
                       observaciones="Generado desde reabastecimiento", id_empresa=id_empresa,
                       origen_flujo=origen_flujo)
    if pid:
        for p in pendientes:
            R.cambiar_estado_propuesta(p["id"], "pedido")
    return pid


def proveedores_mas_utilizados(id_empresa=None, limite=20) -> list:
    """Ranking de proveedores por nº de pedidos (excluye CANCELADO)."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT c.id_proveedor, COALESCE(p.razon_social,'(sin proveedor)') AS proveedor, "
                "COUNT(*) AS pedidos, COALESCE(SUM(c.total),0) AS total FROM compras_pedidos c "
                "LEFT JOIN proveedores p ON p.id_proveedor=c.id_proveedor "
                "WHERE c.id_empresa=%s AND c.estado<>'CANCELADO' "
                "GROUP BY c.id_proveedor, proveedor ORDER BY pedidos DESC, total DESC LIMIT %s",
                (id_empresa, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("proveedores_mas_utilizados: %s", e)
        return []


# ════════════════════════════════════════════════════════════════════════════
# CMP.3 — INCIDENCIAS DE RECEPCIÓN
# ════════════════════════════════════════════════════════════════════════════
def registrar_incidencia(tipo, cantidad=0, id_pedido=None, id_recepcion=None,
                         id_proveedor=None, codigo=None, descripcion=None, usuario=None,
                         id_empresa=None) -> int | None:
    """Registra una incidencia (danado|faltante|exceso|rechazo|error_prov|otros)."""
    id_empresa = _empresa(id_empresa)
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO compras_incidencias (id_empresa, id_pedido, id_recepcion, "
                        "id_proveedor, codigo_articulo, tipo, cantidad, descripcion, usuario) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_pedido, id_recepcion, id_proveedor, codigo, tipo,
                         int(cantidad or 0), descripcion, usuario))
            return cur.lastrowid
    except Exception as e:
        logger.error("registrar_incidencia: %s", e)
        return None


def listar_incidencias(id_empresa=None, estado=None, id_proveedor=None, id_pedido=None) -> list:
    id_empresa = _empresa(id_empresa)
    cond, params = ["id_empresa=%s"], [id_empresa]
    if estado:
        cond.append("estado=%s"); params.append(estado)
    if id_proveedor:
        cond.append("id_proveedor=%s"); params.append(id_proveedor)
    if id_pedido:
        cond.append("id_pedido=%s"); params.append(id_pedido)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM compras_incidencias WHERE {' AND '.join(cond)} "
                        "ORDER BY fecha DESC, id DESC", params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_incidencias: %s", e)
        return []


def resolver_incidencia(id_incidencia, estado="resuelta", id_empresa=None) -> bool:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE compras_incidencias SET estado=%s WHERE id=%s AND id_empresa=%s",
                        (estado, id_incidencia, id_empresa))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("resolver_incidencia: %s", e)
        return False


# ════════════════════════════════════════════════════════════════════════════
# CMP.4 — DEVOLUCIONES A PROVEEDOR
# ════════════════════════════════════════════════════════════════════════════
def _ejecutar_salida_devolucion(did, lineas, id_almacen, id_empresa, usuario):
    """Efecto de stock/kárdex de una devolución a proveedor (DEVOLUCION_PROVEEDOR): decrementa
    `stock_almacen`, consume FEFO (lote indicado o FEFO) y anota en kárdex. Extraído de
    `crear_devolucion` para que `aprobar_devolucion` pueda disparar EXACTAMENTE la misma lógica,
    solo que diferida al momento de la aprobación en vez de a la creación (RMA de autoservicio
    B2B — ver `services.compras.b2b_disputas.solicitar_devolucion_autoservicio`). `lineas` acepta
    tanto los dicts de entrada ("codigo"/"codigo_articulo") como las filas ya leídas de
    `compras_devoluciones_lineas` ("codigo_articulo")."""
    from src.db import stock_almacen as SA2
    from src.db import lotes as L
    from src.db import kardex
    for ln in lineas:
        cod = ln.get("codigo") or ln.get("codigo_articulo")
        cant = int(ln.get("cantidad") or 0)
        if not cod or cant <= 0:
            continue
        SA2.decrementar_stock(cod, id_almacen, cant, id_empresa=id_empresa)
        L.consumir_fefo(cod, cant, tipo="DEVOLUCION_PROVEEDOR", id_empresa=id_empresa,
                        id_documento=f"DEVP{did}", usuario=usuario, id_almacen=id_almacen)
        kardex.registrar_movimiento(cod, "DEVOLUCION_PROVEEDOR", cant, origen="ALMACEN",
                                    destino="PROVEEDOR", id_documento=f"DEVP{did}",
                                    usuario=usuario, id_empresa=id_empresa,
                                    id_almacen_origen=id_almacen,
                                    observaciones=f"Devolución a proveedor #{did}")


def crear_devolucion(id_proveedor=None, lineas=None, motivo=None, id_almacen=None,
                     id_pedido=None, usuario=None, id_empresa=None,
                     estado_inicial="registrada", id_tx=None) -> int | None:
    """Registra una devolución a proveedor. Por defecto (`estado_inicial="registrada"`, el
    comportamiento HISTÓRICO sin cambios — back-office, `portal_empresa_gestion.py`) DESCUENTA stock
    del almacén (stock_almacen) de inmediato, consumiendo lote (FEFO o lote indicado) y registrando
    DEVOLUCION_PROVEEDOR en el kárdex.

    `estado_inicial="pendiente_aprobacion"` (RMA de autoservicio B2B, iniciado por el comprador desde
    `portal_empresa_b2b.py` para un pedido ENTREGADA): el efecto de stock se DIFIERE — no se aplica
    aquí, solo cuando el proveedor apruebe expresamente (`aprobar_devolucion`). `id_tx` enlaza la
    devolución con el pedido B2B (`transaccion_comercial.id_tx`) del que surge, para que la
    aprobación pueda encontrar su escrow/reembolso.

    `lineas`: [{codigo, cantidad, lote?, precio_unitario?, motivo?}]. Devuelve id_devolucion."""
    id_empresa = _empresa(id_empresa)
    lineas = lineas or []
    try:
        from src.db import stock_almacen as SA
        if not id_almacen:
            id_almacen = SA.almacen_central(id_empresa)
    except Exception:
        pass
    try:
        ensure_schema()
        total = 0.0
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO compras_devoluciones (id_empresa, id_proveedor, id_pedido, "
                        "id_almacen, motivo, usuario, estado, id_tx) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_proveedor, id_pedido, id_almacen, motivo, usuario,
                         estado_inicial, id_tx))
            did = cur.lastrowid
            for ln in lineas:
                cod = ln.get("codigo") or ln.get("codigo_articulo")
                cant = int(ln.get("cantidad") or 0)
                if not cod or cant <= 0:
                    continue
                precio = round(float(ln.get("precio_unitario") or 0), 2)
                subtotal = round(cant * precio, 2)
                total += subtotal
                cur.execute("INSERT INTO compras_devoluciones_lineas (id_devolucion, id_empresa, "
                            "codigo_articulo, lote, cantidad, precio_unitario, subtotal, motivo) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                            (did, id_empresa, cod, ln.get("lote"), cant, precio, subtotal,
                             ln.get("motivo")))
            cur.execute("UPDATE compras_devoluciones SET total=%s WHERE id_devolucion=%s",
                        (round(total, 2), did))
        if estado_inicial == "registrada":
            try:
                _ejecutar_salida_devolucion(did, lineas, id_almacen, id_empresa, usuario)
            except Exception as e:
                logger.warning("crear_devolucion: salida stock/lotes #%s: %s", did, e)
        return did
    except Exception as e:
        logger.error("crear_devolucion: %s", e)
        return None


def aprobar_devolucion(id_devolucion, usuario=None, id_empresa=None) -> dict:
    """Aprueba un RMA de autoservicio B2B (`estado='pendiente_aprobacion'`): dispara AHORA el mismo
    efecto de stock/kárdex que `crear_devolucion` aplica de inmediato en el flujo de back-office —
    aquí queda diferido hasta esta aprobación explícita del proveedor. Idempotente: si ya no está
    pendiente, no repite el efecto de stock."""
    id_empresa = _empresa(id_empresa)
    dev = obtener_devolucion(id_devolucion, id_empresa=id_empresa)
    if not dev:
        return {"ok": False, "error": "devolucion_no_encontrada"}
    if dev["estado"] != "pendiente_aprobacion":
        return {"ok": False, "error": f"estado_invalido_para_aprobar ({dev['estado']})"}
    try:
        _ejecutar_salida_devolucion(id_devolucion, dev.get("lineas") or [], dev.get("id_almacen"),
                                    id_empresa, usuario)
    except Exception as e:
        logger.error("aprobar_devolucion: salida stock/lotes #%s: %s", id_devolucion, e)
        return {"ok": False, "error": str(e)}
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE compras_devoluciones SET estado='aprobada' WHERE id_devolucion=%s "
                        "AND id_empresa=%s AND estado='pendiente_aprobacion'",
                        (id_devolucion, id_empresa))
            if cur.rowcount <= 0:
                raise RuntimeError("estado_cambio_concurrentemente")
    except Exception as e:
        logger.error("aprobar_devolucion: update estado #%s: %s", id_devolucion, e)
        return {"ok": False, "error": str(e)}
    return {"ok": True, "id_devolucion": id_devolucion}


def rechazar_devolucion(id_devolucion, motivo=None, usuario=None, id_empresa=None) -> bool:
    """Rechaza un RMA de autoservicio B2B pendiente de aprobación: SIN efecto de stock. La alegación
    del proveedor (`motivo`) se guarda en `motivo_rechazo` (distinto del `motivo` original del
    comprador)."""
    id_empresa = _empresa(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE compras_devoluciones SET estado='rechazada', motivo_rechazo=%s "
                "WHERE id_devolucion=%s AND id_empresa=%s AND estado='pendiente_aprobacion'",
                ((motivo or "").strip()[:255] or None, id_devolucion, id_empresa))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("rechazar_devolucion #%s: %s", id_devolucion, e)
        return False


def listar_devoluciones_de_tx(id_tx, id_empresa=None) -> list:
    """Devoluciones (RMA de autoservicio B2B) enlazadas a un pedido B2B concreto (`id_tx`) — usado
    por el Portal Empresa para mostrar, en el detalle del pedido, el historial de RMA ya
    solicitados sobre él."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_devoluciones WHERE id_tx=%s AND id_empresa=%s "
                        "ORDER BY fecha DESC", (id_tx, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_devoluciones_de_tx(%s): %s", id_tx, e)
        return []


def obtener_devolucion(id_devolucion, id_empresa=None) -> dict | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_devoluciones WHERE id_devolucion=%s AND id_empresa=%s",
                        (id_devolucion, id_empresa))
            cab = _fila_a_dict(cur, cur.fetchone())
            if not cab:
                return None
            cur.execute("SELECT * FROM compras_devoluciones_lineas WHERE id_devolucion=%s ORDER BY id",
                        (id_devolucion,))
            cab["lineas"] = _filas_a_dicts(cur, cur.fetchall())
            return cab
    except Exception as e:
        logger.error("obtener_devolucion: %s", e)
        return None


def listar_devoluciones(id_empresa=None, id_proveedor=None, estado=None, limite=500) -> list:
    id_empresa = _empresa(id_empresa)
    cond, params = ["id_empresa=%s"], [id_empresa]
    if id_proveedor:
        cond.append("id_proveedor=%s"); params.append(id_proveedor)
    if estado:
        cond.append("estado=%s"); params.append(estado)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM compras_devoluciones WHERE {' AND '.join(cond)} "
                        "ORDER BY id_devolucion DESC LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_devoluciones: %s", e)
        return []


# ════════════════════════════════════════════════════════════════════════════
# CMP.5 — FACTURACIÓN AVANZADA (abonos, rectificativas, conciliación n:m)
# ════════════════════════════════════════════════════════════════════════════
def asociar_recepcion_factura(id_factura, id_recepcion, importe=0.0, id_empresa=None) -> bool:
    """Conciliación n:m: vincula una recepción a una factura con su importe."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO compras_factura_recepciones (id_empresa, id_factura, "
                        "id_recepcion, importe) VALUES (%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE importe=VALUES(importe)",
                        (id_empresa, id_factura, id_recepcion, round(float(importe or 0), 2)))
            conn.commit()
            return True
    except Exception as e:
        logger.error("asociar_recepcion_factura: %s", e)
        return False


def recepciones_de_factura(id_factura, id_empresa=None) -> list:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_recepcion, importe FROM compras_factura_recepciones "
                        "WHERE id_factura=%s AND id_empresa=%s", (id_factura, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("recepciones_de_factura: %s", e)
        return []


def registrar_abono(id_proveedor=None, numero_factura=None, lineas=None, base=None, iva=None,
                    id_factura_rectificada=None, id_empresa=None, fecha_factura=None) -> int | None:
    """Registra un ABONO o RECTIFICATIVA de compra (tipo_documento) y lo contabiliza."""
    tipo = "rectificativa" if id_factura_rectificada else "abono"
    return registrar_factura(id_proveedor=id_proveedor, numero_factura=numero_factura,
                             lineas=lineas, base=base, iva=iva, id_empresa=id_empresa,
                             fecha_factura=fecha_factura, tipo_documento=tipo,
                             id_factura_rectificada=id_factura_rectificada)


# ════════════════════════════════════════════════════════════════════════════
# CMP.6 — COSTES REALES / AMPLIADOS (Landed Cost, Fase B)
# ════════════════════════════════════════════════════════════════════════════
_METODOS_PRORRATEO = ("valor", "cantidad", "peso")


def registrar_coste_extra(tipo, importe, id_recepcion=None, id_pedido=None, descripcion=None,
                          id_empresa=None, metodo_prorrateo="cantidad", id_tx=None) -> int | None:
    """Registra un coste indirecto (transporte/aduanas/importación/seguro/manipulación/otros)
    sobre una recepción de compra (`id_recepcion`) o un pedido B2B ya recibido (`id_tx`, Fase B
    Landed Cost — vía Smart Suppliers, que no tiene fila en `compras_recepciones`). Se exige
    EXACTAMENTE uno de los dos (`id_pedido` sigue siendo un acompañante opcional e independiente,
    igual que antes). `metodo_prorrateo` (valor|cantidad|peso) decide cómo
    `prorratear_costes_recepcion()` reparte este componente entre las líneas recibidas; por
    defecto 'cantidad' (reparto a partes iguales por unidad, comportamiento histórico)."""
    if metodo_prorrateo not in _METODOS_PRORRATEO:
        raise ValueError(f"metodo_prorrateo inválido: {metodo_prorrateo!r} (usa {_METODOS_PRORRATEO})")
    if (id_recepcion is None) == (id_tx is None):
        raise ValueError("registrar_coste_extra: indica EXACTAMENTE uno de id_recepcion o id_tx")
    id_empresa = _empresa(id_empresa)
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO compras_costes_extra (id_empresa, id_recepcion, id_pedido, "
                        "id_tx, tipo, importe, metodo_prorrateo, descripcion) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_recepcion, id_pedido, id_tx, tipo,
                         round(float(importe or 0), 2), metodo_prorrateo, descripcion))
            return cur.lastrowid
    except Exception as e:
        logger.error("registrar_coste_extra: %s", e)
        return None


def _recalcular_pmp_landed(cur, codigo, id_empresa, cantidad, precio_base, precio_landed):
    """Recalcula `articulos.coste_medio`/`coste_actual` con el coste LANDED en vez del coste
    base, SUPERSEDIENDO (no acumulando) la actualización PMP que ya hizo
    `actualizar_costes_entrada()` con el coste base en el momento de la recepción (prerrequisito
    Fase B). Sin este paso, el coste indirecto se contaría dos veces si el prorrateo se
    reejecutase, o quedaría "sumado encima" de una media que ya incluía el coste base de estas
    mismas unidades.

    No se reimplementa la media ponderada aparte: se DESHACE algebraicamente la actualización
    previa (con el precio base y la MISMA cantidad/stock_previo que usó la recepción, leyendo
    `Stock_total` actual y restando `cantidad` para obtener ese `stock_previo`) escribiendo en
    `articulos.coste_medio` el valor "de antes de esta recepción", y se vuelve a llamar a
    `actualizar_costes_entrada()` — la única función pública — con el precio LANDED. El resultado
    es matemáticamente idéntico a si la recepción hubiera conocido el coste landed desde el
    principio, sin necesitar un ledger de costes por movimiento (que este módulo no tiene)."""
    cantidad = int(cantidad or 0)
    if cantidad <= 0:
        return
    cur.execute("SELECT COALESCE(Stock_total,0), COALESCE(coste_medio,0) FROM articulos "
                "WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
    r = cur.fetchone()
    if not r:
        return
    if isinstance(r, dict):
        stock_actual, medio_actual = r.get("Stock_total") or 0, r.get("coste_medio") or 0
    else:
        stock_actual, medio_actual = r[0] or 0, r[1] or 0
    stock_actual = int(stock_actual)
    medio_actual = float(medio_actual)
    stock_previo = max(stock_actual - cantidad, 0)
    if stock_previo > 0:
        medio_antes = (medio_actual * stock_actual - float(precio_base) * cantidad) / stock_previo
        cur.execute("UPDATE articulos SET coste_medio=%s WHERE codigo=%s AND id_empresa=%s",
                    (round(medio_antes, 2), codigo, id_empresa))
    actualizar_costes_entrada(cur, codigo, stock_previo, cantidad, float(precio_landed),
                              id_empresa=id_empresa)


def resumen_costes_landed(id_recepcion=None, id_tx=None, id_empresa=None) -> list:
    """Desglose de coste landed por línea recibida, agregado de `compras_costes_extra_lineas`
    entre TODOS los componentes ya prorrateados para esta recepción/tx — para la UI del portal
    (Fase B). Devuelve [{codigo_articulo, cantidad, coste_base_unitario,
    coste_unitario_indirecto, coste_unitario_landed, componentes:[{tipo, importe_asignado}]}]."""
    id_empresa = _empresa(id_empresa)
    if (id_recepcion is None) == (id_tx is None):
        return []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if id_recepcion is not None:
                cur.execute(
                    "SELECT * FROM compras_costes_extra_lineas WHERE id_recepcion=%s "
                    "AND id_empresa=%s ORDER BY id_recepcion_linea, id", (id_recepcion, id_empresa))
            else:
                cur.execute(
                    "SELECT cel.* FROM compras_costes_extra_lineas cel "
                    "JOIN compras_costes_extra cce ON cce.id = cel.id_coste_extra "
                    "WHERE cce.id_tx=%s AND cel.id_empresa=%s ORDER BY cel.codigo_articulo, cel.id",
                    (id_tx, id_empresa))
            filas = _filas_a_dicts(cur, cur.fetchall())
        agrupado = {}
        for f in filas:
            clave = f.get("id_recepcion_linea") or f["codigo_articulo"]
            g = agrupado.setdefault(clave, {
                "codigo_articulo": f["codigo_articulo"], "cantidad": f["cantidad"],
                "coste_base_unitario": float(f["coste_base_unitario"]),
                "coste_unitario_indirecto": 0.0, "componentes": []})
            g["coste_unitario_indirecto"] += float(f["coste_unitario_indirecto"])
            g["componentes"].append({"tipo": f["tipo_coste_extra"],
                                     "importe_asignado": float(f["importe_asignado"])})
        for g in agrupado.values():
            g["coste_unitario_indirecto"] = round(g["coste_unitario_indirecto"], 4)
            g["coste_unitario_landed"] = round(g["coste_base_unitario"] + g["coste_unitario_indirecto"], 4)
        return list(agrupado.values())
    except Exception as e:
        logger.error("resumen_costes_landed: %s", e)
        return []


def prorratear_costes_recepcion(id_recepcion=None, id_tx=None, id_empresa=None, metodo=None) -> dict:
    """Reparte los componentes de coste indirecto (`compras_costes_extra`) SIN prorratear de una
    recepción de compra (`id_recepcion`) o de un pedido B2B ya recibido (`id_tx`) entre sus
    líneas, según `metodo` (cantidad|valor|peso) — si no se indica, se toma de los propios
    componentes pendientes (error claro si mezclan métodos distintos, para no elegir uno al
    azar). Por CADA componente × línea inserta una fila en `compras_costes_extra_lineas`
    (aditivo — nunca sobreescribe ni borra: reejecutar tras añadir un componente nuevo conserva
    el histórico completo). Actualiza el snapshot de `lotes` (coste_unitario_base/indirecto/
    landed, Fase A) para los lotes de esta recepción/tx y recalcula `articulos.coste_medio`/
    `coste_actual` con el coste LANDED — reemplaza, no acumula, el `+=` destructivo de la versión
    anterior de esta función (ver `_recalcular_pmp_landed`). Marca los componentes procesados
    `prorrateado=1` (idempotente, sin cambios en ese mecanismo). Devuelve un resumen por
    artículo."""
    if (id_recepcion is None) == (id_tx is None):
        return {"ok": False, "error": "indica_exactamente_uno_de_id_recepcion_o_id_tx"}
    id_empresa = _empresa(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            # 1) Componentes de coste indirecto pendientes de prorratear.
            if id_recepcion is not None:
                cur.execute("SELECT id, tipo, importe, metodo_prorrateo FROM compras_costes_extra "
                            "WHERE id_recepcion=%s AND id_empresa=%s AND prorrateado=0",
                            (id_recepcion, id_empresa))
            else:
                cur.execute("SELECT id, tipo, importe, metodo_prorrateo FROM compras_costes_extra "
                            "WHERE id_tx=%s AND id_empresa=%s AND prorrateado=0",
                            (id_tx, id_empresa))
            componentes = _filas_a_dicts(cur, cur.fetchall())
            if not componentes:
                return {"ok": True, "prorrateado": 0.0, "componentes": 0, "lineas": 0,
                        "total_distribuido": 0.0, "por_articulo": {}}

            # 2) Método de reparto: el explícito o, si no se indica, el de los componentes
            # pendientes (deben coincidir — mezclarlos en el mismo prorrateo sería ambiguo).
            if metodo is not None:
                if metodo not in _METODOS_PRORRATEO:
                    raise ValueError(f"metodo inválido: {metodo!r} (usa {_METODOS_PRORRATEO})")
                metodo_resuelto = metodo
            else:
                metodos_comp = {c.get("metodo_prorrateo") or "cantidad" for c in componentes}
                if len(metodos_comp) > 1:
                    raise ValueError(
                        "Los componentes de coste pendientes tienen metodo_prorrateo distintos "
                        f"({sorted(metodos_comp)}) — indica `metodo=` explícitamente para desambiguar.")
                metodo_resuelto = metodos_comp.pop()

            # 3) Líneas recibidas: vía A (compras) o vía B2B (transaccion_lineas, Fase B punto 5).
            if id_recepcion is not None:
                cur.execute(
                    "SELECT crl.id AS id_recepcion_linea, crl.codigo_articulo, crl.cantidad, "
                    "COALESCE(cpl.precio_unitario,0) AS precio_unitario "
                    "FROM compras_recepciones_lineas crl "
                    "LEFT JOIN compras_pedidos_lineas cpl ON cpl.id = crl.id_linea_pedido "
                    "WHERE crl.id_recepcion=%s", (id_recepcion,))
                lineas = _filas_a_dicts(cur, cur.fetchall())
                for l in lineas:
                    l["id_recepcion"] = id_recepcion
            else:
                cur.execute(
                    "SELECT codigo_articulo, cantidad, COALESCE(precio_unitario,0) AS precio_unitario "
                    "FROM transaccion_lineas WHERE id_tx=%s", (id_tx,))
                lineas = _filas_a_dicts(cur, cur.fetchall())
                for l in lineas:
                    l["id_recepcion_linea"] = None
                    l["id_recepcion"] = None
            lineas = [l for l in lineas if l.get("codigo_articulo") and int(l.get("cantidad") or 0) > 0]
            if not lineas:
                return {"ok": False, "error": "sin_lineas_recibidas"}

            # 4) Peso de reparto por línea según el método.
            codigos = {l["codigo_articulo"] for l in lineas}
            pesos_articulo = {}
            if metodo_resuelto == "peso" and codigos:
                fmt = ",".join(["%s"] * len(codigos))
                cur.execute(f"SELECT codigo, peso_unitario FROM articulos WHERE codigo IN ({fmt})",
                            tuple(codigos))
                for row in _filas_a_dicts(cur, cur.fetchall()):
                    if row.get("peso_unitario") is not None:
                        pesos_articulo[row["codigo"]] = float(row["peso_unitario"])
            for l in lineas:
                cant = int(l["cantidad"])
                precio = float(l["precio_unitario"] or 0)
                if metodo_resuelto == "valor":
                    l["_peso"], l["_metodo_usado"] = cant * precio, "valor"
                elif metodo_resuelto == "peso":
                    pu = pesos_articulo.get(l["codigo_articulo"])
                    if pu is not None:
                        l["_peso"], l["_metodo_usado"] = cant * pu, "peso"
                    else:   # fallback: artículo sin peso_unitario, esta línea reparte por cantidad.
                        l["_peso"], l["_metodo_usado"] = float(cant), "cantidad"
                else:
                    l["_peso"], l["_metodo_usado"] = float(cant), "cantidad"
            peso_total = sum(l["_peso"] for l in lineas)
            if peso_total <= 0:
                return {"ok": False, "error": "peso_total_reparto_cero"}

            # Cantidad y coste base por artículo (independiente del nº de componentes).
            cantidad_por_articulo, base_por_articulo = {}, {}
            for l in lineas:
                cod = l["codigo_articulo"]
                cant = int(l["cantidad"])
                precio_base = float(l["precio_unitario"] or 0)
                cantidad_por_articulo[cod] = cantidad_por_articulo.get(cod, 0) + cant
                base_por_articulo[cod] = base_por_articulo.get(cod, 0.0) + cant * precio_base

            # 5) Por cada componente × línea: importe_asignado (la última línea absorbe el
            # redondeo para que la suma cuadre EXACTO con el importe del componente) + fila
            # auditable en compras_costes_extra_lineas (aditivo).
            indirecto_por_articulo = {}
            total_distribuido = 0.0
            componentes_aplicados = []
            for comp in componentes:
                importe_comp = round(float(comp["importe"] or 0), 2)
                componentes_aplicados.append(comp["id"])
                if importe_comp == 0:
                    continue
                acumulado = 0.0
                asignados = []
                for i, l in enumerate(lineas):
                    if i == len(lineas) - 1:
                        asignado = round(importe_comp - acumulado, 4)
                    else:
                        asignado = round(importe_comp * (l["_peso"] / peso_total), 4)
                        acumulado += asignado
                    asignados.append(asignado)
                for l, asignado in zip(lineas, asignados):
                    cant = int(l["cantidad"])
                    precio_base = float(l["precio_unitario"] or 0)
                    coste_indirecto_linea = round(asignado / cant, 4) if cant else 0.0
                    coste_landed_linea = round(precio_base + coste_indirecto_linea, 4)
                    cur.execute(
                        "INSERT INTO compras_costes_extra_lineas (id_empresa, id_recepcion, "
                        "id_recepcion_linea, codigo_articulo, cantidad, coste_base_unitario, "
                        "id_coste_extra, tipo_coste_extra, importe_asignado, "
                        "coste_unitario_indirecto, coste_unitario_landed, metodo_usado) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, l.get("id_recepcion"), l.get("id_recepcion_linea"),
                         l["codigo_articulo"], cant, round(precio_base, 4), comp["id"], comp["tipo"],
                         asignado, coste_indirecto_linea, coste_landed_linea, l["_metodo_usado"]))
                    cod = l["codigo_articulo"]
                    indirecto_por_articulo[cod] = indirecto_por_articulo.get(cod, 0.0) + asignado
                    total_distribuido += asignado

            # 6) Snapshot en `lotes` (por id_recepcion_origen/id_tx_origen) + recalculo LANDED
            # (no acumulativo) de articulos.coste_medio/coste_actual.
            resumen_articulos = {}
            for cod, cantidad_art in cantidad_por_articulo.items():
                indirecto_total = indirecto_por_articulo.get(cod, 0.0)
                coste_indirecto_unit = round(indirecto_total / cantidad_art, 4) if cantidad_art else 0.0
                coste_base_unit = round(base_por_articulo.get(cod, 0.0) / cantidad_art, 4) if cantidad_art else 0.0
                coste_landed_unit = round(coste_base_unit + coste_indirecto_unit, 4)
                cur.execute(
                    "UPDATE lotes SET coste_unitario_base=%s, coste_unitario_indirecto=%s, "
                    "coste_unitario_landed=%s WHERE codigo_articulo=%s AND id_empresa=%s "
                    "AND (id_recepcion_origen=%s OR id_tx_origen=%s)",
                    (coste_base_unit, coste_indirecto_unit, coste_landed_unit, cod, id_empresa,
                     id_recepcion, id_tx))
                if indirecto_total:   # nada que recalcular si este artículo no tuvo coste asignado
                    _recalcular_pmp_landed(cur, cod, id_empresa, cantidad_art, coste_base_unit,
                                           coste_landed_unit)
                resumen_articulos[cod] = {
                    "cantidad": cantidad_art, "coste_base": coste_base_unit,
                    "coste_indirecto": coste_indirecto_unit, "coste_landed": coste_landed_unit}

            # 7) Idempotencia: marca los componentes procesados (aunque su importe fuera 0).
            if componentes_aplicados:
                fmt = ",".join(["%s"] * len(componentes_aplicados))
                cur.execute(f"UPDATE compras_costes_extra SET prorrateado=1 WHERE id IN ({fmt}) "
                            f"AND id_empresa=%s", (*componentes_aplicados, id_empresa))

            return {"ok": True, "metodo": metodo_resuelto, "componentes": len(componentes_aplicados),
                    "lineas": len(lineas), "total_distribuido": round(total_distribuido, 2),
                    "por_articulo": resumen_articulos}
    except Exception as e:
        logger.error("prorratear_costes_recepcion(id_recepcion=%s, id_tx=%s): %s",
                     id_recepcion, id_tx, e)
        return {"ok": False, "error": str(e)}


def coste_por_almacen(codigo, id_almacen, id_empresa=None) -> dict:
    """Valoración del stock de un artículo en un almacén = existencias × coste medio."""
    id_empresa = _empresa(id_empresa)
    try:
        from src.db import stock_almacen as SA
        cant = SA.obtener_stock_almacen(codigo, id_almacen, id_empresa)
        c = obtener_costes(codigo)
        medio = float(c.get("coste_medio") or 0)
        return {"cantidad": cant, "coste_medio": medio, "valoracion": round(cant * medio, 2)}
    except Exception as e:
        logger.error("coste_por_almacen: %s", e)
        return {"cantidad": 0, "coste_medio": 0, "valoracion": 0}


# ════════════════════════════════════════════════════════════════════════════
# CMP.8 — HOMOLOGACIÓN Y EVALUACIÓN DE PROVEEDORES
# ════════════════════════════════════════════════════════════════════════════
def calcular_kpis_proveedor(id_proveedor, id_empresa=None) -> dict:
    """KPIs del proveedor a partir de incidencias, devoluciones y pedidos recibidos."""
    id_empresa = _empresa(id_empresa)

    def _n(cur):
        x = cur.fetchone()
        return (x[0] if not isinstance(x, dict) else list(x.values())[0]) or 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM compras_incidencias WHERE id_proveedor=%s "
                        "AND id_empresa=%s", (id_proveedor, id_empresa)); inc = _n(cur)
            cur.execute("SELECT COUNT(*) FROM compras_incidencias WHERE id_proveedor=%s "
                        "AND id_empresa=%s AND tipo='rechazo'", (id_proveedor, id_empresa)); rech = _n(cur)
            cur.execute("SELECT COUNT(*) FROM compras_devoluciones WHERE id_proveedor=%s "
                        "AND id_empresa=%s", (id_proveedor, id_empresa)); dev = _n(cur)
            cur.execute("SELECT COUNT(*) FROM compras_pedidos WHERE id_proveedor=%s "
                        "AND id_empresa=%s AND estado='RECIBIDO'", (id_proveedor, id_empresa)); ped = _n(cur)
        base = max(1, ped)
        valoracion = max(0.0, round(100.0 - (inc + dev + rech * 2) * 100.0 / (base + inc + dev), 2))
        return {"incidencias": inc, "rechazos": rech, "devoluciones": dev,
                "pedidos_recibidos": ped, "valoracion_global": valoracion}
    except Exception as e:
        logger.error("calcular_kpis_proveedor: %s", e)
        return {"incidencias": 0, "rechazos": 0, "devoluciones": 0, "pedidos_recibidos": 0,
                "valoracion_global": 0.0}


def registrar_evaluacion(id_proveedor, periodo=None, id_empresa=None, **kpis) -> int | None:
    """Persiste una evaluación de proveedor (usa KPIs calculados si no se pasan)."""
    id_empresa = _empresa(id_empresa)
    if not kpis:
        kpis = calcular_kpis_proveedor(id_proveedor, id_empresa)
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO proveedores_evaluacion (id_empresa, id_proveedor, periodo, "
                        "cumplimiento_plazo, calidad, incidencias, rechazos, devoluciones, "
                        "valoracion_global, observaciones) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_proveedor, periodo,
                         float(kpis.get("cumplimiento_plazo") or 0), float(kpis.get("calidad") or 0),
                         int(kpis.get("incidencias") or 0), int(kpis.get("rechazos") or 0),
                         int(kpis.get("devoluciones") or 0),
                         float(kpis.get("valoracion_global") or 0), kpis.get("observaciones")))
            return cur.lastrowid
    except Exception as e:
        logger.error("registrar_evaluacion: %s", e)
        return None


def listar_evaluaciones(id_proveedor, id_empresa=None) -> list:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM proveedores_evaluacion WHERE id_proveedor=%s AND id_empresa=%s "
                        "ORDER BY fecha DESC", (id_proveedor, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_evaluaciones: %s", e)
        return []


def set_homologacion_estado(id_proveedor, estado, id_empresa=None) -> bool:
    """Estados: pendiente|aprobado|suspendido|bloqueado. 'aprobado'→homologado; 'bloqueado'→bloqueado."""
    id_empresa = _empresa(id_empresa)
    if estado not in ("pendiente", "aprobado", "suspendido", "bloqueado"):
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE proveedores SET homologacion_estado=%s, homologado=%s, bloqueado=%s "
                        "WHERE id_proveedor=%s AND id_empresa=%s",
                        (estado, 1 if estado == "aprobado" else 0,
                         1 if estado == "bloqueado" else 0, id_proveedor, id_empresa))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("set_homologacion_estado: %s", e)
        return False
