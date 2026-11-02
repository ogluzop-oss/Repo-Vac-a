"""
Motor de ingesta (Fase 1). Orquesta lectura → mapeo → validación (dry-run) → carga a los MOTORES OFICIALES
(N7): `db/articulos` (upsert por `codigo`), `db/familias` (alta/vínculo `id_familia`) y stock por `db/stock`
(persistente por tienda) + kárdex (`db/kardex` AJUSTE, traza). Multi-tenant: todo con `id_empresa`. Idempotente:
re-importar el mismo fichero ACTUALIZA (no duplica) y FIJA el stock (no lo suma). Sin PyQt.
"""

import json
import logging
import os

from src.db.conexion import obtener_conexion
from src.services.importacion import lectores, mapeo as _map, validadores
from src.services.importacion.modelo import (
    CLIENTES, PLAN_CONTABLE, PRODUCTOS, PROVEEDORES, SALDOS, TESORERIA, VENTAS_HIST,
    limpiar_texto, parse_fecha, parse_precio, parse_stock,
)

_TERCEROS = (CLIENTES, PROVEEDORES)
_ESPECIALES = (VENTAS_HIST, SALDOS, TESORERIA)

logger = logging.getLogger("importacion.motor")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _tienda(id_empresa, id_tienda=None):
    if id_tienda is not None:
        return id_tienda
    try:
        from src.db.stock import tienda_por_defecto
        return tienda_por_defecto(id_empresa)
    except Exception:
        return None


# ── Análisis + validación (no escriben) ──────────────────────────────────────
def analizar(ruta, entidad=PRODUCTOS, *, usar_ia=False) -> dict:
    """Lee el fichero, detecta columnas y SUGIERE el mapeo (IA si `usar_ia` y hay backend; si no, heurística).
    Devuelve una muestra para confirmar en la UI."""
    try:
        filas, _ = lectores.leer(ruta)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    r = analizar_filas(filas, entidad, usar_ia=usar_ia)
    if r.get("ok"):
        r["formato"] = lectores.detectar_formato(ruta)
    return r


def _columnas(filas) -> list:
    cols = []
    for f in filas:
        for k in f:
            if k and k not in cols:
                cols.append(k)
    return cols


def analizar_filas(filas, entidad=PRODUCTOS, *, usar_ia=False) -> dict:
    """Como `analizar` pero sobre filas YA leídas (conector directo/API/dump SQL). Sugiere el mapeo."""
    columnas = _columnas(filas)
    if usar_ia:
        from src.services.importacion.mapeo_ia import sugerir_mapeo_ia
        sugerido = sugerir_mapeo_ia(columnas, entidad, muestra=filas[:3])
    else:
        sugerido = _map.sugerir_mapeo(columnas, entidad)
    return {"ok": True, "entidad": entidad, "columnas": columnas, "n_filas": len(filas),
            "muestra": filas[:5], "mapeo_sugerido": sugerido,
            "faltan_requeridos": _map.campos_requeridos_faltantes(sugerido, entidad)}


def _canonizar(filas, mapeo):
    """Convierte cada fila de origen a valores canónicos parseados. Devuelve (validas, errores).
    Cada `validas[i]` conserva su posición ORIGINAL en `_fila` (1-based) — necesario para que
    `MigrationEngine.commit()` pueda atar un fallo de fila (p.ej. `crear_articulo` devolviendo False)
    a la fila de staging exacta que lo causó, sin adivinar por coincidencia de código."""
    validas, errores = [], []
    for i, fila in enumerate(filas, start=1):
        c = _map.aplicar_mapeo(fila, mapeo)
        codigo = limpiar_texto(c.get("codigo"))
        if not codigo:
            errores.append({"fila": i, "motivo": "sin código de artículo"})
            continue
        validas.append({
            "_fila": i,
            "codigo": codigo,
            "nombre": limpiar_texto(c.get("nombre")),
            "descripcion": limpiar_texto(c.get("descripcion")),
            "precio": parse_precio(c.get("precio")) if "precio" in mapeo else None,
            "familia": limpiar_texto(c.get("familia")) if "familia" in mapeo else None,
            "stock": parse_stock(c.get("stock")) if "stock" in mapeo else None,
            "stock_central": parse_stock(c.get("stock_central")) if "stock_central" in mapeo else None,
            "stock_esperado": parse_stock(c.get("stock_esperado")) if "stock_esperado" in mapeo else None,
            "imagen": (str(c.get("imagen") or "").strip() or None) if "imagen" in mapeo else None,
        })
    return validas, errores


def simular(ruta, mapeo=None, *, entidad=PRODUCTOS, id_empresa=None) -> dict:
    """Dry-run: valida y clasifica sin escribir nada. Informe con nuevos/actualizados, con stock y familias."""
    try:
        filas, _ = lectores.leer(ruta)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return simular_filas(filas, mapeo, entidad=entidad, id_empresa=id_empresa)


def simular_filas(filas, mapeo=None, *, entidad=PRODUCTOS, id_empresa=None) -> dict:
    """Dry-run sobre filas ya leídas (conector/API/dump)."""
    id_empresa = _emp(id_empresa)
    columnas = _columnas(filas)
    mapeo = mapeo or _map.sugerir_mapeo(columnas, entidad)
    faltan = _map.campos_requeridos_faltantes(mapeo, entidad)
    if faltan:
        return {"ok": False, "error": f"faltan campos obligatorios: {', '.join(faltan)}", "mapeo": mapeo}
    if entidad in _TERCEROS:
        return _simular_terceros(filas, mapeo, entidad, id_empresa)
    if entidad in _ESPECIALES:
        return _simular_generico(filas, mapeo, entidad)
    validas, errores = _canonizar(filas, mapeo)
    codigos = [v["codigo"] for v in validas]
    existentes = _codigos_existentes(codigos, id_empresa)
    familias = sorted({v["familia"] for v in validas if v["familia"]})
    resumen = {
        "total": len(filas), "validas": len(validas), "con_error": len(errores),
        "nuevos": sum(1 for c in codigos if c not in existentes),
        "actualizados": sum(1 for c in codigos if c in existentes),
        "con_stock": sum(1 for v in validas if v["stock"] is not None),
        "con_stock_central": sum(1 for v in validas if v.get("stock_central") is not None),
        "con_stock_esperado": sum(1 for v in validas if v.get("stock_esperado") is not None),
        "con_imagen": sum(1 for v in validas if v.get("imagen")),
        "familias": familias,
    }
    return {"ok": True, "mapeo": mapeo, "resumen": resumen, "errores": errores[:200]}


def _codigos_existentes(codigos, id_empresa) -> set:
    if not codigos:
        return set()
    out = set()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for i in range(0, len(codigos), 500):          # troceado para IN grande
                trozo = codigos[i:i + 500]
                ph = ",".join(["%s"] * len(trozo))
                cur.execute(f"SELECT codigo FROM articulos WHERE codigo IN ({ph}) AND id_empresa=%s",
                            (*trozo, id_empresa))
                out.update(r[0] if not isinstance(r, dict) else r["codigo"] for r in cur.fetchall())
    except Exception as e:
        logger.debug("_codigos_existentes: %s", e)
    return out


# ── Carga (escribe en los motores oficiales) ─────────────────────────────────
def _resolver_familias(nombres, id_empresa):
    """get-or-create de familias por nombre (case-insensitive). Devuelve ({nombre_lower: id}, n_creadas)."""
    from src.db.familias import crear_familia, listar_familias
    idx, creadas = {}, 0
    try:
        for f in listar_familias(id_empresa, solo_activas=False):
            idx[str(f.get("nombre") or "").strip().lower()] = f.get("id")
    except Exception:
        pass
    cache = {}
    for n in nombres:
        key = n.strip().lower()
        if key in idx:
            cache[key] = idx[key]
            continue
        fid = crear_familia(n, id_empresa=id_empresa)
        if fid:
            idx[key] = fid
            cache[key] = fid
            creadas += 1
    return cache, creadas


def _dir_imagenes():
    d = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                      "documentos", "importacion", "imagenes"))
    os.makedirs(d, exist_ok=True)
    return d


def _resolver_imagen(valor, codigo, id_empresa):
    """Lleva la imagen de ORIGEN a una RUTA LOCAL que Smart Manager puede mostrar (`articulos.imagen` la carga
    con QPixmap). URL http(s) → descarga; ruta de fichero local existente → copia a la carpeta de importación;
    en otro caso o ante error → None. Best-effort: nunca rompe la carga."""
    import re as _re
    valor = str(valor or "").strip()
    if not valor:
        return None
    carpeta = os.path.join(_dir_imagenes(), str(id_empresa))
    try:
        os.makedirs(carpeta, exist_ok=True)
    except Exception:
        return None
    safe = _re.sub(r"[^A-Za-z0-9_.-]", "_", str(codigo))[:80] or "img"
    try:
        low = valor.lower()
        if low.startswith(("http://", "https://")):
            import urllib.request
            ext = os.path.splitext(low.split("?")[0])[1]
            if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
                ext = ".jpg"
            destino = os.path.join(carpeta, f"{safe}{ext}")
            req = urllib.request.Request(valor, headers={"User-Agent": "SmartManager"})
            with urllib.request.urlopen(req, timeout=15) as r, open(destino, "wb") as fh:
                fh.write(r.read())
            return destino if os.path.exists(destino) and os.path.getsize(destino) > 0 else None
        if os.path.isfile(valor):
            import shutil
            ext = os.path.splitext(valor)[1] or ".jpg"
            destino = os.path.join(carpeta, f"{safe}{ext}")
            shutil.copyfile(valor, destino)
            return destino
    except Exception as e:
        logger.debug("resolver imagen (%s): %s", codigo, e)
    return None


def ejecutar(ruta, mapeo=None, *, entidad=PRODUCTOS, id_empresa=None, id_tienda=None, usuario=None,
             trazar_kardex=True) -> dict:
    """Carga real desde un FICHERO. Delega en `ejecutar_filas`."""
    try:
        filas, _ = lectores.leer(ruta)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return ejecutar_filas(filas, mapeo, entidad=entidad, id_empresa=id_empresa, id_tienda=id_tienda,
                          usuario=usuario, trazar_kardex=trazar_kardex,
                          origen=os.path.basename(str(ruta)), formato=lectores.detectar_formato(ruta))


def ejecutar_filas(filas, mapeo=None, *, entidad=PRODUCTOS, id_empresa=None, id_tienda=None, usuario=None,
                   trazar_kardex=True, origen="(datos)", formato=None) -> dict:
    """Carga real sobre filas ya leídas (conector directo/API/dump). Transaccional para artículos+stock;
    kárdex después (best-effort). Idempotente. Auditada."""
    id_empresa = _emp(id_empresa)
    if not id_empresa:
        return {"ok": False, "error": "sin empresa (tenant) destino"}
    columnas = _columnas(filas)
    mapeo = mapeo or _map.sugerir_mapeo(columnas, entidad)
    faltan = _map.campos_requeridos_faltantes(mapeo, entidad)
    if faltan:
        return {"ok": False, "error": f"faltan campos obligatorios: {', '.join(faltan)}"}
    res = _ejecutar_por_entidad(entidad, filas, mapeo, id_empresa, id_tienda=id_tienda, usuario=usuario,
                                trazar_kardex=trazar_kardex)
    res["id_trabajo"] = _registrar_trabajo(id_empresa, origen, entidad, formato, len(filas),
                                           res.get("cargados", 0),
                                           res.get("errores_n", len(res.get("errores", []))),
                                           usuario, estado=("completado" if res.get("ok") else "error"))
    return res


def _ejecutar_por_entidad(entidad, filas, mapeo, id_empresa, *, id_tienda=None, usuario=None,
                          trazar_kardex=True) -> dict:
    """Despacho único ENTIDAD -> `_cargar_*` (motor OFICIAL de cada una). Compartido por `ejecutar_filas`
    (carga real de un fichero/conector), `MigrationEngine.simulate()` (misma llamada, sobre una conexión
    simulada que siempre revierte) y `MigrationEngine.commit()` (misma llamada, por tanda) — un solo
    punto de verdad de "qué función de dominio corresponde a cada entidad", nunca tres copias."""
    if entidad == CLIENTES:
        return _cargar_terceros(filas, mapeo, id_empresa, "cliente")
    if entidad == PROVEEDORES:
        return _cargar_terceros(filas, mapeo, id_empresa, "proveedor")
    if entidad == VENTAS_HIST:
        return _cargar_ventas_hist(filas, mapeo, id_empresa)
    if entidad == SALDOS:
        return _cargar_saldos(filas, mapeo, id_empresa, usuario)
    if entidad == TESORERIA:
        return _cargar_tesoreria(filas, mapeo, id_empresa, usuario)
    if entidad == PLAN_CONTABLE:
        return _cargar_plan_contable(filas, mapeo, id_empresa)
    return _cargar_productos(filas, mapeo, id_empresa, id_tienda, usuario, trazar_kardex)


def _cargar_productos(filas, mapeo, id_empresa, id_tienda, usuario, trazar_kardex) -> dict:
    """Carga de PRODUCTOS: alta/actualización idempotente vía los motores OFICIALES `db.articulos.
    crear_articulo`/`actualizar_articulo` (Fase A — antes era un `INSERT...ON DUPLICATE KEY UPDATE`
    crudo aquí mismo, que saltaba `ARTICULO_CREADO`/`ARTICULO_MODIFICADO` y cualquier otra regla que
    viva en `db/articulos.py`). Cambio de rendimiento DELIBERADO y documentado: N inserts/updates por
    fila en vez de un único `executemany` — es el precio de que cada alta/edición pase de verdad por
    el dominio (eventos/auditoría reales). Las columnas `articulos.Stock_total`/`Stock_tienda`
    (denormalizadas, distintas de la tabla `stock_tienda`) se fijan vía `db.articulos.marcar_repuestos`
    (mismo UPDATE que ya existía ahí, reutilizado en vez de duplicar SQL). La tabla `stock_tienda`
    (stock real por tienda) SIGUE en SQL directo: no existe una función de dominio "fijar stock
    absoluto de una tienda" a la que rutear (documentado; no se inventa una aquí)."""
    validas, errores = _canonizar(filas, mapeo)
    if not validas:
        return {"ok": False, "error": "no hay filas válidas", "errores": errores[:200],
                "errores_n": len(errores)}

    # Familias (get-or-create) → id_familia por fila.
    fam_cache, fam_creadas = {}, 0
    if "familia" in mapeo:
        nombres = {v["familia"] for v in validas if v["familia"]}
        fam_cache, fam_creadas = _resolver_familias(nombres, id_empresa)

    # Imágenes: descarga/copia a carpeta local → ruta por código (solo las que se resuelven). Se muestran en
    # la ficha del artículo (`articulos.imagen`).
    img_cache = {}
    if "imagen" in mapeo:
        for v in validas:
            if v.get("imagen"):
                ruta = _resolver_imagen(v["imagen"], v["codigo"], id_empresa)
                if ruta:
                    img_cache[v["codigo"]] = ruta

    hay_stock = "stock" in mapeo
    codigos = [v["codigo"] for v in validas]
    existentes = _codigos_existentes(codigos, id_empresa)

    from src.db.articulos import actualizar_articulo, crear_articulo
    cargados = 0
    fallos_fila = []
    for v in validas:
        id_familia = fam_cache.get((v["familia"] or "").strip().lower()) if v["familia"] else None
        imagen = img_cache.get(v["codigo"])
        try:
            if v["codigo"] in existentes:
                campos = {}
                if "nombre" in mapeo and v["nombre"]:
                    campos["nombre"] = v["nombre"]
                if "descripcion" in mapeo and v["descripcion"]:
                    campos["descripcion"] = v["descripcion"]
                if "precio" in mapeo and v["precio"] is not None:
                    campos["precio"] = v["precio"]
                if id_familia:
                    campos["id_familia"] = id_familia
                if imagen:
                    campos["imagen"] = imagen
                ok = actualizar_articulo(v["codigo"], id_empresa=id_empresa, **campos) if campos else True
            else:
                # Sin nombre mapeado/vacío: `crear_articulo` exige nombre no vacío -> se usa el código
                # como nombre provisional en vez de descartar la fila (mismo espíritu que el INSERT
                # crudo anterior, que sí admitía nombre NULL).
                ok = crear_articulo(v["codigo"], v["nombre"] or v["codigo"],
                                    precio=(v["precio"] if v["precio"] is not None else 0),
                                    id_familia=id_familia, imagen=imagen, id_empresa=id_empresa)
                if ok:
                    existentes.add(v["codigo"])
        except Exception as e:
            ok = False
            logger.error("_cargar_productos(%s): %s", v["codigo"], e)
        if ok:
            cargados += 1
        else:
            fallos_fila.append({"fila": v["_fila"], "codigo": v["codigo"],
                                "motivo": "no se pudo crear/actualizar el artículo (ver logs)"})

    # Columnas denormalizadas `articulos.Stock_total`/`Stock_tienda` -> vía dominio (`marcar_repuestos`,
    # mismo UPDATE que ya usaba Fase 3/reposición; se reutiliza en vez de duplicar el SQL aquí).
    if hay_stock:
        items = [(v["codigo"], v["stock"], v["stock"]) for v in validas if v["stock"] is not None]
        if items:
            try:
                from src.db.articulos import marcar_repuestos
                marcar_repuestos(items, id_empresa=id_empresa)
            except Exception as e:
                logger.error("_cargar_productos marcar_repuestos: %s", e)

    # Stock persistente POR TIENDA (tabla `stock_tienda`, distinta de las columnas de arriba) — sin
    # función de dominio equivalente (ver docstring); se mantiene como upsert directo, igual que antes.
    tid = _tienda(id_empresa, id_tienda) if hay_stock else None
    if hay_stock and tid is not None:
        st = [[id_empresa, tid, v["codigo"], (v["stock"] or 0)] for v in validas if v["stock"] is not None]
        if st:
            try:
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO stock_tienda (id_empresa, id_tienda, codigo_articulo, stock) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE stock=VALUES(stock)", st)
                    conn.commit()
            except Exception as e:
                logger.error("_cargar_productos stock: %s", e)

    # Kárdex (traza de existencias inicial) — best-effort, fuera de la transacción de stock.
    con_stock = sum(1 for v in validas if v["stock"] is not None)
    if trazar_kardex and hay_stock:
        try:
            from src.db.kardex import registrar_movimiento
            for v in validas:
                if v["stock"] is not None:
                    registrar_movimiento(v["codigo"], "AJUSTE", v["stock"], id_empresa=id_empresa,
                                         id_tienda=tid, usuario=usuario, observaciones="Importación inicial")
        except Exception as e:
            logger.debug("kardex import: %s", e)

    # Stock de ALMACÉN CENTRAL — granularidad real por ubicación (pedido explícito). Vía
    # `stock_almacen.ajustar_stock`: es la fuente de verdad REAL (no una columna caché suelta),
    # auto-recalcula `articulos.Stock_central`/`Stock_total` y da de alta el artículo en el sistema
    # de almacenes si todavía no lo estaba — a diferencia del bloque "stock" de arriba (columna
    # denormalizada directa, precedente histórico que se conserva tal cual por compatibilidad).
    con_stock_central = 0
    if "stock_central" in mapeo:
        items_central = [(v["codigo"], v["stock_central"]) for v in validas
                         if v.get("stock_central") is not None]
        if items_central:
            try:
                from src.db import stock_almacen as _salm
                id_almacen_central = _salm.almacen_central(id_empresa)
                if id_almacen_central:
                    for codigo, valor in items_central:
                        if _salm.ajustar_stock(codigo, id_almacen_central, valor, id_empresa):
                            con_stock_central += 1
                else:
                    logger.error("_cargar_productos stock_central: no se pudo resolver el almacén central")
            except Exception as e:
                logger.error("_cargar_productos stock_central: %s", e)

    # Stock esperado (umbral mínimo de reposición) — función NUEVA y estrecha
    # (`db.articulos.marcar_stock_esperado`): SOLO toca `Stock_esperado`, sin los efectos
    # secundarios de `marcar_repuesto_exportado` (que pertenece al flujo de recepción de pedidos a
    # reposición, un proceso distinto de una importación de datos plana).
    con_stock_esperado = 0
    if "stock_esperado" in mapeo:
        items_esperado = [(v["codigo"], v["stock_esperado"]) for v in validas
                          if v.get("stock_esperado") is not None]
        if items_esperado:
            try:
                from src.db.articulos import marcar_stock_esperado
                con_stock_esperado = marcar_stock_esperado(items_esperado, id_empresa=id_empresa)
            except Exception as e:
                logger.error("_cargar_productos stock_esperado: %s", e)

    return {"ok": cargados > 0, "cargados": cargados, "familias_creadas": fam_creadas, "con_stock": con_stock,
            "con_stock_central": con_stock_central, "con_stock_esperado": con_stock_esperado,
            "imagenes": len(img_cache), "errores": errores[:200], "errores_n": len(errores) + len(fallos_fila),
            "fallos_fila": fallos_fila}


def _simular_terceros(filas, mapeo, entidad, id_empresa) -> dict:
    """Dry-run de clientes/proveedores: valida nombre y clasifica nuevos/actualizados por NIF (sin escribir)."""
    tipo = "cliente" if entidad == CLIENTES else "proveedor"
    validas, errores = [], []
    for i, fila in enumerate(filas, start=1):
        c = _map.aplicar_mapeo(fila, mapeo)
        if not limpiar_texto(c.get("nombre")):
            errores.append({"fila": i, "motivo": "sin nombre/razón social"})
            continue
        validas.append(limpiar_texto(c.get("nif")))
    nuevos = actualizados = 0
    for nif in validas:
        if nif and _buscar_tercero(nif, id_empresa, tipo):
            actualizados += 1
        else:
            nuevos += 1
    resumen = {"total": len(filas), "validas": len(validas), "con_error": len(errores),
               "nuevos": nuevos, "actualizados": actualizados, "con_stock": 0, "familias": []}
    return {"ok": True, "mapeo": mapeo, "resumen": resumen, "errores": errores[:200]}


# ── Carga de CLIENTES / PROVEEDORES (terceros) ───────────────────────────────
def _cargar_terceros(filas, mapeo, id_empresa, tipo) -> dict:
    """Alta/actualización idempotente de clientes o proveedores (dedupe por NIF/CIF). Reutiliza db/clientes y
    db/proveedores (N7). Sin NIF no hay dedupe → se crea siempre."""
    validas, errores = [], []
    for i, fila in enumerate(filas, start=1):
        c = _map.aplicar_mapeo(fila, mapeo)
        nombre = limpiar_texto(c.get("nombre"))
        if not nombre:
            errores.append({"fila": i, "motivo": "sin nombre/razón social"})
            continue
        validas.append({"_fila": i, "nombre": nombre, "nif": limpiar_texto(c.get("nif")),
                        "email": limpiar_texto(c.get("email")), "telefono": limpiar_texto(c.get("telefono")),
                        "direccion": limpiar_texto(c.get("direccion"))})
    if not validas:
        return {"ok": False, "error": "no hay filas válidas", "errores": errores[:200],
                "errores_n": len(errores)}
    creados = actualizados = 0
    fallos_fila = []
    for v in validas:
        existente = _buscar_tercero(v["nif"], id_empresa, tipo) if v["nif"] else None
        if existente:
            if _actualizar_tercero(existente, v, id_empresa, tipo):
                actualizados += 1
            else:
                fallos_fila.append({"fila": v["_fila"], "codigo": v["nif"] or v["nombre"],
                                    "motivo": f"no se pudo actualizar el {tipo} (ver logs)"})
        elif _crear_tercero(v, id_empresa, tipo):
            creados += 1
        else:
            fallos_fila.append({"fila": v["_fila"], "codigo": v["nif"] or v["nombre"],
                                "motivo": f"no se pudo crear el {tipo} (ver logs)"})
    return {"ok": (creados + actualizados) > 0, "cargados": creados + actualizados, "creados": creados,
            "actualizados": actualizados, "errores": errores[:200],
            "errores_n": len(errores) + len(fallos_fila), "fallos_fila": fallos_fila}


def _buscar_tercero(nif, id_empresa, tipo):
    tabla, col = ("clientes", "nif") if tipo == "cliente" else ("proveedores", "cif_nif")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT id FROM {tabla} WHERE {col}=%s AND id_empresa=%s LIMIT 1", (nif, id_empresa))
            r = cur.fetchone()
            return (r[0] if not isinstance(r, dict) else r["id"]) if r else None
    except Exception as e:
        logger.debug("_buscar_tercero: %s", e)
        return None


def _crear_tercero(v, id_empresa, tipo) -> bool:
    try:
        if tipo == "cliente":
            from src.db.clientes import crear_cliente
            return bool(crear_cliente(v["nombre"], nif=v["nif"], telefono=v["telefono"], email=v["email"],
                                      direccion=v["direccion"], id_empresa=id_empresa))
        from src.db.proveedores import crear_proveedor
        return bool(crear_proveedor(v["nombre"], cif_nif=v["nif"], email=v["email"], telefono=v["telefono"],
                                    direccion_fiscal=v["direccion"], id_empresa=id_empresa))
    except Exception as e:
        logger.debug("_crear_tercero: %s", e)
        return False


def _actualizar_tercero(idt, v, id_empresa, tipo) -> bool:
    try:
        if tipo == "cliente":
            from src.db.clientes import actualizar_cliente
            campos = {k: v[k] for k in ("nombre", "telefono", "email", "direccion") if v.get(k)}
            return actualizar_cliente(idt, id_empresa, **campos) if campos else True
        from src.db.proveedores import actualizar_proveedor
        campos = {}
        for canon, columna in (("nombre", "razon_social"), ("email", "email"), ("telefono", "telefono"),
                               ("direccion", "direccion_fiscal")):
            if v.get(canon):
                campos[columna] = v[canon]
        return actualizar_proveedor(idt, id_empresa, **campos) if campos else True
    except Exception as e:
        logger.debug("_actualizar_tercero: %s", e)
        return False


# ── Fase 5-B: histórico de ventas · saldos de apertura · tesorería · documentos ─
def _simular_generico(filas, mapeo, entidad) -> dict:
    """Dry-run genérico (histórico/saldos/tesorería): valida la presencia de los campos obligatorios."""
    from src.services.importacion.modelo import CAMPOS
    req = [c for c, (r, _s) in CAMPOS.get(entidad, {}).items() if r]
    validas, errs = 0, []
    for i, fila in enumerate(filas, start=1):
        c = _map.aplicar_mapeo(fila, mapeo)
        faltan = [k for k in req if not limpiar_texto(c.get(k))]
        if faltan:
            if len(errs) < 200:
                errs.append({"fila": i, "motivo": f"falta {', '.join(faltan)}"})
        else:
            validas += 1
    resumen = {"total": len(filas), "validas": validas, "con_error": len(filas) - validas,
               "nuevos": validas, "actualizados": 0, "con_stock": 0, "familias": []}
    return {"ok": True, "mapeo": mapeo, "resumen": resumen, "errores": errs}


def _cargar_ventas_hist(filas, mapeo, id_empresa) -> dict:
    """Histórico de ventas → `ventas_historicas` vía `db.ventas_historicas.registrar_venta_historica`
    (Fase A: antes era un `INSERT...ON DUPLICATE KEY UPDATE` crudo aquí mismo; se extrae a `db/` para
    que TODA la importación rutee por la capa de dominio, aunque esta tabla en concreto sea un mirror
    de solo-forecasting sin eventos/auditoría propios — ver el docstring del wrapper). NO toca `ventas`
    ni finanzas. Idempotente por (empresa, fecha, código)."""
    from src.db.ventas_historicas import registrar_venta_historica
    errores, fallos_fila = [], []
    cargados = 0
    for i, fila in enumerate(filas, start=1):
        c = _map.aplicar_mapeo(fila, mapeo)
        fecha = parse_fecha(c.get("fecha"))
        codigo = limpiar_texto(c.get("codigo"))
        if not fecha or not codigo:
            errores.append({"fila": i, "motivo": "falta fecha o código válidos"})
            continue
        cant = parse_precio(c.get("cantidad")) if "cantidad" in mapeo else None
        imp = parse_precio(c.get("importe")) if "importe" in mapeo else None
        ok = registrar_venta_historica(fecha, codigo, cantidad=(cant or 0), importe=(imp or 0),
                                       id_empresa=id_empresa)
        if ok:
            cargados += 1
        else:
            fallos_fila.append({"fila": i, "codigo": codigo,
                                "motivo": "no se pudo registrar la venta histórica (ver logs)"})
    if cargados == 0:
        return {"ok": False, "error": "no hay filas válidas", "errores": errores[:200],
                "errores_n": len(errores) + len(fallos_fila), "fallos_fila": fallos_fila}
    return {"ok": True, "cargados": cargados, "errores": errores[:200],
            "errores_n": len(errores) + len(fallos_fila), "fallos_fila": fallos_fila}


def _cargar_saldos(filas, mapeo, id_empresa, usuario) -> dict:
    """Saldos de apertura → UN asiento de apertura (motor contable, doble partida). Idempotente (ref_origen).
    Si Σdebe≠Σhaber, el motor lo rechaza y se informa (no se inventa un cuadre)."""
    import datetime as _dt
    lineas, errores = [], []
    for i, fila in enumerate(filas, start=1):
        c = _map.aplicar_mapeo(fila, mapeo)
        cuenta = limpiar_texto(c.get("cuenta"))
        if not cuenta:
            errores.append({"fila": i, "motivo": "sin cuenta contable"})
            continue
        debe = parse_precio(c.get("debe")) if "debe" in mapeo else None
        haber = parse_precio(c.get("haber")) if "haber" in mapeo else None
        if debe is None and haber is None and "saldo" in mapeo:      # saldo con signo → debe/haber
            s = parse_precio(c.get("saldo")) or 0
            debe, haber = (s, 0) if s >= 0 else (0, -s)
        debe, haber = debe or 0, haber or 0
        if debe == 0 and haber == 0:
            errores.append({"fila": i, "motivo": "saldo nulo"})
            continue
        lineas.append({"_fila": i, "cuenta": cuenta, "debe": debe, "haber": haber,
                       "descripcion": limpiar_texto(c.get("descripcion")) or "Apertura"})
    if not lineas:
        return {"ok": False, "error": "no hay líneas válidas", "errores": errores[:200],
                "errores_n": len(errores)}
    try:
        from src.services.contabilidad.asientos import crear_asiento
        res = crear_asiento(_dt.date.today(), lineas, concepto="Apertura (importación de saldos)",
                            tipo="apertura", origen="importacion", ref_origen="apertura-import",
                            idempotente=True, usuario=usuario, id_empresa=id_empresa)
    except Exception as e:
        logger.error("_cargar_saldos: %s", e)
        res = None
    if not res:
        # El asiento es ATÓMICO (doble partida): si falla, falla para TODAS las líneas del lote por
        # igual (no es decomponible fila a fila como el resto de entidades) — se listan todas en
        # `fallos_fila` para que `MigrationEngine.commit()` pueda registrar el detalle por fila igual
        # que con las demás entidades, en vez de un único error de lote sin trazabilidad.
        motivo = ("el asiento de apertura no cuadra (Σdebe≠Σhaber) o el ejercicio está cerrado; "
                 "revisa los saldos.")
        fallos_fila = [{"fila": ln["_fila"], "codigo": ln["cuenta"], "motivo": motivo} for ln in lineas]
        return {"ok": False, "error": motivo, "errores": errores[:200],
                "errores_n": len(errores) + len(fallos_fila), "fallos_fila": fallos_fila}
    return {"ok": True, "cargados": len(lineas), "id_asiento": res.get("id"),
            "errores": errores[:200], "errores_n": len(errores)}


def _cargar_tesoreria(filas, mapeo, id_empresa, usuario) -> dict:
    """Cuentas bancarias con saldo inicial (motor de tesorería; valida IBAN por fila)."""
    from src.db.tesoreria import crear_cuenta
    creados, errores = 0, []
    for i, fila in enumerate(filas, start=1):
        c = _map.aplicar_mapeo(fila, mapeo)
        nombre = limpiar_texto(c.get("nombre"))
        iban = limpiar_texto(c.get("iban"))
        if not nombre or not iban:
            errores.append({"fila": i, "motivo": "falta nombre o IBAN"})
            continue
        saldo = parse_precio(c.get("saldo")) if "saldo" in mapeo else 0
        try:
            cid = crear_cuenta(nombre, iban, titular=limpiar_texto(c.get("titular")),
                               bic=limpiar_texto(c.get("bic")), entidad=limpiar_texto(c.get("banco")),
                               saldo_inicial=saldo or 0, usuario=usuario, id_empresa=id_empresa)
            if cid:
                creados += 1
        except Exception as e:                       # IBAN/BIC inválido u otros → error por fila
            errores.append({"fila": i, "motivo": str(e)})
    if creados == 0:
        return {"ok": False, "error": "ninguna cuenta válida (revisa los IBAN)", "errores": errores[:200],
                "errores_n": len(errores)}
    return {"ok": True, "cargados": creados, "errores": errores[:200], "errores_n": len(errores)}


def _cargar_plan_contable(filas, mapeo, id_empresa) -> dict:
    """Alta de cuentas del Plan Contable (`services/contabilidad/cuentas.crear_cuenta`). Entidad nueva
    (Fase A): el negocio pide poder importar el Plan Contable como "1º Configuración Base" — ANTES que
    SALDOS, que ya exige que la cuenta exista (`validadores.validar_saldos`). Get-or-create: una cuenta
    con ese código que YA existe cuenta como éxito sin duplicar (mismo criterio que `_cargar_terceros`
    con el NIF), en vez de fallar por clave duplicada."""
    from src.services.contabilidad.cuentas import crear_cuenta, obtener_cuenta
    validas, errores = [], []
    for i, fila in enumerate(filas, start=1):
        c = _map.aplicar_mapeo(fila, mapeo)
        codigo = limpiar_texto(c.get("codigo"))
        nombre = limpiar_texto(c.get("nombre"))
        if not codigo or not nombre:
            errores.append({"fila": i, "motivo": "falta código o nombre de cuenta"})
            continue
        validas.append({"_fila": i, "codigo": codigo, "nombre": nombre,
                        "tipo": limpiar_texto(c.get("tipo")) or "otro",
                        "naturaleza": limpiar_texto(c.get("naturaleza")) or "deudora"})
    if not validas:
        return {"ok": False, "error": "no hay filas válidas", "errores": errores[:200],
                "errores_n": len(errores)}
    cargados = 0
    fallos_fila = []
    for v in validas:
        try:
            if obtener_cuenta(v["codigo"], id_empresa):
                cargados += 1                              # ya existe: get-or-create, sin duplicar
                continue
            if crear_cuenta(v["codigo"], v["nombre"], v["tipo"], v["naturaleza"], id_empresa=id_empresa):
                cargados += 1
            else:
                fallos_fila.append({"fila": v["_fila"], "codigo": v["codigo"],
                                    "motivo": "no se pudo crear la cuenta contable (ver logs)"})
        except Exception as e:
            logger.error("_cargar_plan_contable(%s): %s", v["codigo"], e)
            fallos_fila.append({"fila": v["_fila"], "codigo": v["codigo"], "motivo": str(e)})
    return {"ok": cargados > 0, "cargados": cargados, "errores": errores[:200],
            "errores_n": len(errores) + len(fallos_fila), "fallos_fila": fallos_fila}


def importar_documentos(rutas, *, tipo="otros", id_empresa=None, usuario=None) -> dict:
    """Registra documentos HISTÓRICOS como adjuntos (read-only) en el centro documental. Idempotente por ruta."""
    import os as _os
    from src.db.documentos import registrar_documento
    registrados, errores = 0, []
    for r in rutas or []:
        if not _os.path.exists(r):
            errores.append({"ruta": r, "motivo": "no existe"})
            continue
        try:
            did = registrar_documento(r, tipo=tipo, id_empresa=id_empresa, id_usuario=usuario)
            if did:
                registrados += 1
            else:
                errores.append({"ruta": r, "motivo": "no registrado"})
        except Exception as e:
            errores.append({"ruta": r, "motivo": str(e)})
    return {"ok": True, "registrados": registrados, "errores": errores}


# ── Auditoría / reanudación ──────────────────────────────────────────────────
def _registrar_trabajo(id_empresa, origen, entidad, formato, total, ok, err, usuario,
                       estado="completado") -> int | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO import_trabajos (id_empresa, fichero, entidad, formato, filas_total, "
                        "filas_ok, filas_error, estado, usuario) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, str(origen)[:255], entidad, formato, total, ok, err, estado,
                         str(usuario) if usuario else None))
            tid = cur.lastrowid
            conn.commit()
            return tid
    except Exception as e:
        logger.debug("_registrar_trabajo: %s", e)
        return None


def trabajos_recientes(id_empresa=None, *, limite=20) -> list:
    """Historial de importaciones del tenant (auditoría/reanudación). Los de estado 'error' son reintentables:
    la carga es idempotente, así que re-ejecutar el mismo origen no duplica."""
    id_empresa = _emp(id_empresa)
    if not id_empresa:
        return []
    try:
        from src.db.conexion import _filas_a_dicts
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM import_trabajos WHERE id_empresa=%s ORDER BY id DESC LIMIT %s",
                        (id_empresa, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("trabajos_recientes: %s", e)
        return []


# ── Conectores de alto nivel (gated por plan: el conector directo = api.access) ──
def _permite_conector(id_empresa) -> bool:
    """El conector DIRECTO (BD/ODBC/API) es capacidad avanzada → requiere `api.access` (PRO/PLUS). La
    importación por FICHERO es flujo principal y NUNCA se gatea. Degradable: sin SaaS → permitido (legacy)."""
    try:
        from src.services.saas import entitlements
        return entitlements.can("api.access", id_empresa)
    except Exception:
        return True


_MSG_PLAN = "El conector directo (BD/ODBC/API) requiere plan PRO o superior (capacidad api.access)."


def importar_desde_bd(query, *, id_empresa=None, conexion=None, url=None, mapeo=None, entidad=PRODUCTOS,
                      **kw) -> dict:
    """Importa ejecutando un SELECT en la BD de ORIGEN (DBAPI o SQLAlchemy). Gated por plan."""
    id_empresa = _emp(id_empresa)
    if not _permite_conector(id_empresa):
        return {"ok": False, "error": _MSG_PLAN}
    from src.services.importacion import conector
    try:
        filas = conector.leer_consulta(query, conexion=conexion, url=url)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return ejecutar_filas(filas, mapeo, entidad=entidad, id_empresa=id_empresa, origen="bd-directa",
                          formato="sql", **kw)


def importar_desde_odbc(dsn, query, *, id_empresa=None, mapeo=None, entidad=PRODUCTOS, **kw) -> dict:
    id_empresa = _emp(id_empresa)
    if not _permite_conector(id_empresa):
        return {"ok": False, "error": _MSG_PLAN}
    from src.services.importacion import conector
    try:
        filas = conector.leer_odbc(dsn, query)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return ejecutar_filas(filas, mapeo, entidad=entidad, id_empresa=id_empresa, origen="odbc",
                          formato="odbc", **kw)


def importar_desde_api(url, *, id_empresa=None, fetch=None, mapeo=None, entidad=PRODUCTOS, **kw) -> dict:
    id_empresa = _emp(id_empresa)
    if not _permite_conector(id_empresa):
        return {"ok": False, "error": _MSG_PLAN}
    from src.services.importacion import conector
    try:
        filas = conector.leer_api(url, fetch=fetch)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return ejecutar_filas(filas, mapeo, entidad=entidad, id_empresa=id_empresa, origen="api",
                          formato="api", **kw)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# MigrationEngine (Fase A) — ciclo de vida por ETAPAS: stage → validate → simulate → commit.
#
# Tablas nuevas (migración 0272): `migracion_lotes_staging`/`migracion_filas_staging` (staging) e
# `import_trabajos_errores` (detalle de errores de una importación YA ejecutada de verdad). Se apila
# en "un solo motor" (este módulo, no uno paralelo): `commit()` reutiliza EXACTAMENTE el mismo
# despachador `_ejecutar_por_entidad`/`_cargar_*` que ya usa `ejecutar_filas` — staging no es un motor
# nuevo, es una fase previa (dry-run real) delante del mismo motor de siempre.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _fila_a_dict_staging(cur, fila):
    from src.db.conexion import _fila_a_dict
    return _fila_a_dict(cur, fila)


def _obtener_lote_staging(id_lote_staging) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM migracion_lotes_staging WHERE id=%s", (id_lote_staging,))
            return _fila_a_dict_staging(cur, cur.fetchone())
    except Exception as e:
        logger.error("_obtener_lote_staging(%s): %s", id_lote_staging, e)
        return None


def _listar_filas_staging(id_lote_staging, *, estados=None) -> list:
    from src.db.conexion import _filas_a_dicts
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if estados:
                ph = ",".join(["%s"] * len(estados))
                cur.execute(f"SELECT * FROM migracion_filas_staging WHERE id_lote_staging=%s "
                            f"AND estado IN ({ph}) ORDER BY numero_fila", (id_lote_staging, *estados))
            else:
                cur.execute("SELECT * FROM migracion_filas_staging WHERE id_lote_staging=%s "
                            "ORDER BY numero_fila", (id_lote_staging,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("_listar_filas_staging(%s): %s", id_lote_staging, e)
        return []


def stage(filas, entidad, id_empresa=None, usuario=None, mapeo=None, *, external_id_campo=None) -> int | None:
    """Apila un LOTE en staging (`migracion_lotes_staging`/`migracion_filas_staging`) SIN escribir nada
    en producción. `filas` son las filas de ORIGEN sin mapear (mismo formato que `ejecutar_filas`) —
    a propósito, distinto del literal `datos_mapeados` de la especificación: `stage()` necesita la fila
    ORIGINAL para poblar `datos_originales` a la vez que `datos_mapeados` (`mapeo.aplicar_mapeo`), y
    además encaja con la firma que ya usan `analizar_filas`/`simular_filas`/`ejecutar_filas` en este
    mismo módulo. `external_id_campo` (opcional) = nombre de la columna DE ORIGEN que sirve de
    identificador del sistema legado (trazabilidad); si no se indica, `external_id` queda NULL.
    Devuelve el `id` del lote o `None` si falla."""
    id_empresa = _emp(id_empresa)
    if not id_empresa:
        return None
    columnas = _columnas(filas)
    mapeo = mapeo or _map.sugerir_mapeo(columnas, entidad)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO migracion_lotes_staging (id_empresa, entidad, estado, mapeo, usuario) "
                "VALUES (%s,%s,'borrador',%s,%s)",
                (id_empresa, entidad, json.dumps(mapeo, ensure_ascii=False),
                 str(usuario) if usuario else None))
            id_lote = cur.lastrowid
            filas_ins = []
            for i, fila in enumerate(filas, start=1):
                mapeada = _map.aplicar_mapeo(fila, mapeo)
                ext = limpiar_texto(fila.get(external_id_campo)) if external_id_campo else None
                filas_ins.append((id_lote, i, ext,
                                  json.dumps(fila, ensure_ascii=False, default=str),
                                  json.dumps(mapeada, ensure_ascii=False, default=str)))
            if filas_ins:
                cur.executemany(
                    "INSERT INTO migracion_filas_staging (id_lote_staging, numero_fila, external_id, "
                    "datos_originales, datos_mapeados) VALUES (%s,%s,%s,%s,%s)", filas_ins)
            conn.commit()
            return id_lote
    except Exception as e:
        logger.error("stage(%s): %s", entidad, e)
        return None


def validate(id_lote_staging) -> dict:
    """Valida CADA fila del lote (tipos/formato + integridad referencial + reglas de negocio ERP, ver
    `validadores.py`) y actualiza su `estado` (`valido|advertencia|error`). No escribe nada en
    producción. Devuelve `{validos, advertencias, errores, detalle}` — `detalle` solo trae las filas
    CON hallazgos (silenciar 10 000 filas "sin novedad" no aporta)."""
    lote = _obtener_lote_staging(id_lote_staging)
    if not lote:
        return {"ok": False, "error": "lote de staging no encontrado"}
    entidad, id_empresa = lote["entidad"], lote["id_empresa"]
    filas = _listar_filas_staging(id_lote_staging)
    if not filas:
        return {"ok": False, "error": "el lote no tiene filas"}
    contexto = validadores.construir_contexto(entidad, id_empresa)
    validos = advertencias = errores_n = 0
    detalle = []
    actualizaciones = []
    for f in filas:
        try:
            datos = json.loads(f.get("datos_mapeados") or "{}")
        except Exception:
            datos = {}
        hallazgos = validadores.validar_fila(entidad, datos, id_empresa=id_empresa, contexto=contexto)
        estado = validadores.estado_desde_hallazgos(hallazgos)
        actualizaciones.append((estado, f["id"]))
        if estado == "valido":
            validos += 1
        elif estado == "advertencia":
            advertencias += 1
        else:
            errores_n += 1
        if hallazgos:
            # `id_fila` (Fase B, GUI): id REAL de `migracion_filas_staging` — necesario para que el
            # panel de diagnóstico pueda editar en línea el valor de ESA fila exacta
            # (`actualizar_fila_staging`) sin tener que adivinarlo a partir de `numero_fila`. Clave
            # NUEVA añadida al dict; no rompe a ningún consumidor existente de `detalle`.
            detalle.append({"id_fila": f["id"], "fila": f["numero_fila"], "estado": estado,
                            "hallazgos": hallazgos})
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.executemany("UPDATE migracion_filas_staging SET estado=%s WHERE id=%s", actualizaciones)
            cur.execute("UPDATE migracion_lotes_staging SET estado='simulado' WHERE id=%s",
                        (id_lote_staging,))
            conn.commit()
    except Exception as e:
        logger.error("validate update(%s): %s", id_lote_staging, e)
    return {"ok": True, "total": len(filas), "validos": validos, "advertencias": advertencias,
            "errores": errores_n, "detalle": detalle[:500]}


def _filas_canonicas_e_identidad(filas_staging) -> tuple:
    """De filas de staging (con `datos_mapeados` ya bajo claves canónicas) reconstruye la pareja
    (filas, mapeo) que espera `_ejecutar_por_entidad`/`_cargar_*`: como el dato YA está bajo su nombre
    de campo canónico, el 'mapeo columna origen -> campo canónico' es la identidad campo->campo."""
    filas = []
    campos = set()
    for f in filas_staging:
        try:
            datos = json.loads(f.get("datos_mapeados") or "{}")
        except Exception:
            datos = {}
        filas.append(datos)
        campos.update(datos.keys())
    return filas, {c: c for c in campos}


# ── simulate(): dry-run REAL "crear y deshacer" ──────────────────────────────────────────────────
# Diseño (revisado): la primera versión compartía UNA conexión entre todos los módulos de dominio
# (monkeypatch de `obtener_conexion`/`transaccion`), como haría un SAVEPOINT clásico. Se descartó tras
# reproducir en vivo, de forma FIABLE (no es una sospecha, es un repro de laboratorio: ver commits de
# esta rama), que ese parcheo — incluso restaurado correctamente antes de que `simulate()` retorne —
# deja el pool de conexiones en un estado donde el SIGUIENTE `commit()` real falla con
# `pymysql.err.InterfaceError` (socket ya cerrado) en un porcentaje alto de casos; resetear el pool
# (`conexion._resetear_pool`) tampoco lo arregla, así que NO es una conexión pool "de verdad"
# corrupta — es la propia mecánica de compartir una conexión entre N módulos de dominio distintos la
# que resulta demasiado fragil en esta capa (cada función de dominio abre/cierra su PROPIA conexión
# por diseño; no hay un punto de extensión pensado para esto). Aceptar ese riesgo en el camino de
# escritura REAL (`commit()`) no era razonable solo para que `simulate()` sea "elegante".
#
# La alternativa aquí: EJECUTAR DE VERDAD (conexiones normales, sin parchear nada) solo las filas
# cuya CLAVE NATURAL confirma que serían un ALTA nueva (comprobado ANTES, por lectura), y deshacerlas
# con un DELETE preciso por esa misma clave justo después — nunca comparte conexiones ni parchea
# ningún módulo, así que no puede reproducir el problema de arriba. Las filas que ya existen (serían
# ACTUALIZACIONES) NO se ejecutan aquí — se reportan aparte; su verificación estructural ya la cubre
# `validate()`. SALDOS es la única excepción real: un asiento contable es INMUTABLE y con hash
# encadenado (`services/contabilidad/asientos.py`) — crear uno de verdad y borrarlo arriesgaría
# corromper el encadenado de asientos reales posteriores, así que se queda con una comprobación
# ESTRUCTURAL (cuadre + cuentas existentes, lo mismo que ya hace `validadores.validar_saldos`) sin
# tocar la BD en absoluto.
def _simular_productos(filas, id_empresa) -> dict:
    codigos = [f["codigo"] for f in filas if limpiar_texto(f.get("codigo"))]
    existentes = _codigos_existentes(codigos, id_empresa)
    nuevas = [f for f in filas if limpiar_texto(f.get("codigo")) and f["codigo"] not in existentes]
    actualizarian = len([f for f in filas if limpiar_texto(f.get("codigo"))]) - len(nuevas)
    if not nuevas:
        return {"ok": True, "simulados": 0, "fallidos": 0,
                "detalle": {"actualizarian": actualizarian, "nota": "sin filas nuevas que crear"}}
    from src.db.familias import listar_familias
    try:
        familias_antes = {str(f.get("nombre") or "").strip().lower()
                          for f in listar_familias(id_empresa, solo_activas=False)}
    except Exception:
        familias_antes = set()
    mapeo_identidad = {c: c for fila in nuevas for c in fila}
    res = _cargar_productos(nuevas, mapeo_identidad, id_empresa, None, "(simulacion)", True)
    codigos_creados = [f["codigo"] for f in nuevas]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            ph = ",".join(["%s"] * len(codigos_creados))
            cur.execute(f"DELETE FROM movimientos_stock WHERE codigo_articulo IN ({ph}) "
                        f"AND id_empresa=%s", (*codigos_creados, id_empresa))
            cur.execute(f"DELETE FROM stock_tienda WHERE codigo_articulo IN ({ph}) AND id_empresa=%s",
                        (*codigos_creados, id_empresa))
            cur.execute(f"DELETE FROM articulos WHERE codigo IN ({ph}) AND id_empresa=%s",
                        (*codigos_creados, id_empresa))
            cur.execute(f"DELETE FROM eventos WHERE id_empresa=%s AND ref_entidad='articulo' "
                        f"AND ref_id IN ({ph})", (id_empresa, *codigos_creados))
            conn.commit()
        familias_despues = listar_familias(id_empresa, solo_activas=False)
        nuevas_familias = [f for f in familias_despues
                           if str(f.get("nombre") or "").strip().lower() not in familias_antes]
        if nuevas_familias:
            with obtener_conexion() as conn, conn.cursor() as cur:
                for f in nuevas_familias:
                    cur.execute("SELECT COUNT(*) FROM articulos WHERE id_familia=%s", (f["id"],))
                    r = cur.fetchone()
                    n = r[0] if not isinstance(r, dict) else list(r.values())[0]
                    if not n:                          # solo si nadie más la referencia ya
                        cur.execute("DELETE FROM familias_producto WHERE id=%s", (f["id"],))
                conn.commit()
    except Exception as e:
        logger.error("_simular_productos deshacer: %s", e)
    cargados = int(res.get("cargados", 0) or 0)
    detalle = dict(res)
    if actualizarian:
        detalle["actualizarian"] = actualizarian
    return {"ok": bool(res.get("ok")), "simulados": cargados,
            "fallidos": len(nuevas) - cargados, "detalle": detalle}


def _simular_terceros_nuevos(filas, id_empresa, tipo) -> dict:
    tabla, col = ("clientes", "nif") if tipo == "cliente" else ("proveedores", "cif_nif")
    con_nif = [f for f in filas if limpiar_texto(f.get("nif"))]
    sin_nif = len(filas) - len(con_nif)
    nifs = [f["nif"] for f in con_nif]
    existentes = set()
    if nifs:
        with obtener_conexion() as conn, conn.cursor() as cur:
            ph = ",".join(["%s"] * len(nifs))
            cur.execute(f"SELECT {col} FROM {tabla} WHERE {col} IN ({ph}) AND id_empresa=%s",
                        (*nifs, id_empresa))
            existentes = {(r[0] if not isinstance(r, dict) else r[col]) for r in cur.fetchall()}
    nuevas = [f for f in con_nif if f["nif"] not in existentes]
    actualizarian = len(con_nif) - len(nuevas)
    if not nuevas:
        return {"ok": True, "simulados": 0, "fallidos": 0,
                "detalle": {"actualizarian": actualizarian,
                           "sin_nif_no_simuladas": sin_nif,
                           "nota": "sin NIF no hay clave natural fiable para un dry-run seguro; esas "
                                   "filas SÍ se crearán en commit() (siempre se crea sin NIF)"}}
    mapeo_identidad = {c: c for fila in nuevas for c in fila}
    res = _cargar_terceros(nuevas, mapeo_identidad, id_empresa, tipo)
    nifs_creados = [f["nif"] for f in nuevas]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            ph = ",".join(["%s"] * len(nifs_creados))
            # Ids ANTES de borrar (solo `crear_cliente` publica evento; `crear_proveedor` no publica
            # ninguno hoy — ver `db/proveedores.py`, así que para proveedores esto no encuentra nada).
            cur.execute(f"SELECT id FROM {tabla} WHERE {col} IN ({ph}) AND id_empresa=%s",
                        (*nifs_creados, id_empresa))
            ids_creados = [str(r[0] if not isinstance(r, dict) else r["id"]) for r in cur.fetchall()]
            cur.execute(f"DELETE FROM {tabla} WHERE {col} IN ({ph}) AND id_empresa=%s",
                        (*nifs_creados, id_empresa))
            if ids_creados:
                ph_id = ",".join(["%s"] * len(ids_creados))
                cur.execute(f"DELETE FROM eventos WHERE id_empresa=%s AND ref_entidad='cliente' "
                            f"AND ref_id IN ({ph_id})", (id_empresa, *ids_creados))
            conn.commit()
    except Exception as e:
        logger.error("_simular_terceros_nuevos deshacer(%s): %s", tipo, e)
    cargados = int(res.get("cargados", 0) or 0)
    detalle = dict(res)
    detalle["actualizarian"] = actualizarian
    detalle["sin_nif_no_simuladas"] = sin_nif
    return {"ok": bool(res.get("ok")), "simulados": cargados,
            "fallidos": len(nuevas) - cargados, "detalle": detalle}


def _simular_ventas_hist(filas, id_empresa) -> dict:
    validas = [f for f in filas if limpiar_texto(f.get("codigo")) and parse_fecha(f.get("fecha"))]
    claves = [(f["codigo"], parse_fecha(f["fecha"])) for f in validas]
    existentes = set()
    if claves:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cond = " OR ".join(["(codigo_articulo=%s AND fecha=%s)"] * len(claves))
            params = [v for par in claves for v in par]
            cur.execute(f"SELECT codigo_articulo, fecha FROM ventas_historicas WHERE id_empresa=%s "
                        f"AND ({cond})", (id_empresa, *params))
            for r in cur.fetchall():
                cod = r[0] if not isinstance(r, dict) else r["codigo_articulo"]
                fch = r[1] if not isinstance(r, dict) else r["fecha"]
                existentes.add((cod, str(fch)))
    nuevas = [f for f in validas if (f["codigo"], parse_fecha(f["fecha"])) not in existentes]
    actualizarian = len(validas) - len(nuevas)
    if not nuevas:
        return {"ok": True, "simulados": 0, "fallidos": 0, "detalle": {"actualizarian": actualizarian}}
    mapeo_identidad = {c: c for fila in nuevas for c in fila}
    res = _cargar_ventas_hist(nuevas, mapeo_identidad, id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            claves_creadas = [(f["codigo"], parse_fecha(f["fecha"])) for f in nuevas]
            cond = " OR ".join(["(codigo_articulo=%s AND fecha=%s)"] * len(claves_creadas))
            params = [v for par in claves_creadas for v in par]
            cur.execute(f"DELETE FROM ventas_historicas WHERE id_empresa=%s AND ({cond})",
                        (id_empresa, *params))
            conn.commit()
    except Exception as e:
        logger.error("_simular_ventas_hist deshacer: %s", e)
    cargados = int(res.get("cargados", 0) or 0)
    detalle = dict(res)
    detalle["actualizarian"] = actualizarian
    return {"ok": bool(res.get("ok")), "simulados": cargados,
            "fallidos": len(nuevas) - cargados, "detalle": detalle}


def _simular_tesoreria(filas, id_empresa) -> dict:
    # `_cargar_tesoreria` NUNCA deduplica (cada fila crea SIEMPRE una cuenta nueva) -> todo el lote es
    # "alta nueva"; se puede simular entero.
    mapeo_identidad = {c: c for fila in filas for c in fila}
    ibans_antes = set()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM cuentas_bancarias WHERE id_empresa=%s", (id_empresa,))
            ibans_antes = {(r[0] if not isinstance(r, dict) else r["id"]) for r in cur.fetchall()}
    except Exception as e:
        logger.debug("_simular_tesoreria snapshot: %s", e)
    res = _cargar_tesoreria(filas, mapeo_identidad, id_empresa, "(simulacion)")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM cuentas_bancarias WHERE id_empresa=%s", (id_empresa,))
            ids_despues = {(r[0] if not isinstance(r, dict) else r["id"]) for r in cur.fetchall()}
            nuevos = ids_despues - ibans_antes
            if nuevos:
                ph = ",".join(["%s"] * len(nuevos))
                cur.execute(f"DELETE FROM cuentas_bancarias WHERE id IN ({ph})", tuple(nuevos))
            conn.commit()
    except Exception as e:
        logger.error("_simular_tesoreria deshacer: %s", e)
    cargados = int(res.get("cargados", 0) or 0)
    return {"ok": bool(res.get("ok")), "simulados": cargados,
            "fallidos": len(filas) - cargados, "detalle": res}


def _simular_plan_contable(filas, id_empresa) -> dict:
    from src.services.contabilidad.cuentas import obtener_cuenta
    con_codigo = [f for f in filas if limpiar_texto(f.get("codigo"))]
    nuevas = [f for f in con_codigo if not obtener_cuenta(f["codigo"], id_empresa)]
    actualizarian = len(con_codigo) - len(nuevas)
    if not nuevas:
        return {"ok": True, "simulados": 0, "fallidos": 0, "detalle": {"actualizarian": actualizarian}}
    mapeo_identidad = {c: c for fila in nuevas for c in fila}
    res = _cargar_plan_contable(nuevas, mapeo_identidad, id_empresa)
    codigos_creados = [f["codigo"] for f in nuevas]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            ph = ",".join(["%s"] * len(codigos_creados))
            cur.execute(f"DELETE FROM contab_cuentas WHERE codigo IN ({ph}) AND id_empresa=%s",
                        (*codigos_creados, id_empresa))
            conn.commit()
    except Exception as e:
        logger.error("_simular_plan_contable deshacer: %s", e)
    cargados = int(res.get("cargados", 0) or 0)
    detalle = dict(res)
    detalle["actualizarian"] = actualizarian
    return {"ok": bool(res.get("ok")), "simulados": cargados,
            "fallidos": len(nuevas) - cargados, "detalle": detalle}


def _simular_saldos_estructural(filas, id_empresa) -> dict:
    """SALDOS no se ejecuta de verdad en `simulate()` (ver nota de diseño arriba): se revalida
    ESTRUCTURALMENTE con el mismo validador que `validate()` (cuadre + cuentas existentes en el Plan
    Contable), sin tocar la BD. `simulados` cuenta líneas sin hallazgos de error."""
    contexto = validadores.construir_contexto(SALDOS, id_empresa)
    validas = fallidas = 0
    detalle_filas = []
    for f in filas:
        hallazgos = validadores.validar_fila(SALDOS, f, id_empresa=id_empresa, contexto=contexto)
        if any(h["severidad"] == "error" for h in hallazgos):
            fallidas += 1
            detalle_filas.append({"cuenta": f.get("cuenta"), "hallazgos": hallazgos})
        else:
            validas += 1
    return {"ok": fallidas == 0, "simulados": validas, "fallidos": fallidas,
            "detalle": {"nota": "SALDOS: comprobación ESTRUCTURAL (no se postea un asiento real de "
                                "prueba — un asiento contable es inmutable y con hash encadenado; "
                                "ver docstring de simulate()).",
                       "detalle_errores": detalle_filas[:200]}}


def simulate(id_lote_staging) -> dict:
    """Dry-run: para la mayoría de entidades, ejecuta de verdad SOLO las filas cuya clave natural
    confirma que serían un alta NUEVA (comprobado antes, por lectura) y las deshace con un DELETE
    preciso justo después — nunca deja rastro en las tablas de producción para esas filas. Las filas
    que ya existirían (serían actualizaciones) NO se ejecutan aquí; su verificación es estructural
    (mismo motor que `validate()`). SALDOS es la excepción: comprobación 100% estructural, sin escribir
    nada, por la naturaleza inmutable/hash-encadenada de los asientos contables (ver
    `_simular_saldos_estructural`). Solo considera filas en estado `valido`/`advertencia`."""
    lote = _obtener_lote_staging(id_lote_staging)
    if not lote:
        return {"ok": False, "error": "lote de staging no encontrado"}
    entidad, id_empresa = lote["entidad"], lote["id_empresa"]
    filas_staging = _listar_filas_staging(id_lote_staging, estados=("valido", "advertencia"))
    if not filas_staging:
        return {"ok": True, "simulados": 0, "fallidos": 0, "detalle": {},
                "aviso": "no hay filas válidas/con advertencia para simular (ejecuta validate() primero)"}
    filas, _mapeo_identidad = _filas_canonicas_e_identidad(filas_staging)

    try:
        if entidad == PRODUCTOS:
            return _simular_productos(filas, id_empresa)
        if entidad == CLIENTES:
            return _simular_terceros_nuevos(filas, id_empresa, "cliente")
        if entidad == PROVEEDORES:
            return _simular_terceros_nuevos(filas, id_empresa, "proveedor")
        if entidad == VENTAS_HIST:
            return _simular_ventas_hist(filas, id_empresa)
        if entidad == TESORERIA:
            return _simular_tesoreria(filas, id_empresa)
        if entidad == PLAN_CONTABLE:
            return _simular_plan_contable(filas, id_empresa)
        if entidad == SALDOS:
            return _simular_saldos_estructural(filas, id_empresa)
    except Exception as e:
        logger.error("simulate(%s): %s", id_lote_staging, e)
        return {"ok": False, "error": str(e), "simulados": 0, "fallidos": len(filas_staging)}
    return {"ok": False, "error": f"entidad no soportada: {entidad}"}


def _marcar_lote(id_lote_staging, estado, *, id_trabajo=None) -> None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if id_trabajo is not None:
                cur.execute("UPDATE migracion_lotes_staging SET estado=%s, id_trabajo=%s WHERE id=%s",
                            (estado, id_trabajo, id_lote_staging))
            else:
                cur.execute("UPDATE migracion_lotes_staging SET estado=%s WHERE id=%s",
                            (estado, id_lote_staging))
            conn.commit()
    except Exception as e:
        logger.error("_marcar_lote(%s): %s", id_lote_staging, e)


def _registrar_errores_trabajo(id_trabajo, tanda_staging, errores_canon, fallos_fila) -> None:
    """Vuelca los hallazgos de UNA tanda (`_cargar_*`: `errores` indexado por posición 1-based DENTRO
    de la tanda, `fallos_fila` indexado igual vía la clave `_fila` que añadió `_canonizar`/`_cargar_*`)
    a `import_trabajos_errores`, resolviendo `numero_fila` contra la fila de staging REAL de esa
    posición — así el futuro Historial (Fase B) puede señalar la fila exacta del fichero de origen."""
    if id_trabajo is None or (not errores_canon and not fallos_fila):
        return
    filas = []
    for e in errores_canon or []:
        pos = e.get("fila")
        numero_fila = tanda_staging[pos - 1]["numero_fila"] if pos and 0 < pos <= len(tanda_staging) else None
        filas.append((id_trabajo, numero_fila, None, None, "error", e.get("motivo")))
    for f in fallos_fila or []:
        pos = f.get("fila")
        numero_fila = tanda_staging[pos - 1]["numero_fila"] if pos and 0 < pos <= len(tanda_staging) else None
        filas.append((id_trabajo, numero_fila, "codigo", f.get("codigo"), "error", f.get("motivo")))
    if not filas:
        return
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO import_trabajos_errores (id_trabajo, numero_fila, campo, valor_original, "
                "severidad, motivo) VALUES (%s,%s,%s,%s,%s,%s)", filas)
            conn.commit()
    except Exception as e:
        logger.error("_registrar_errores_trabajo(%s): %s", id_trabajo, e)


def commit(id_lote_staging, *, tamano_lote=300, on_progreso=None, debe_continuar=None,
          id_tienda=None) -> dict:
    """Ejecuta REALMENTE el lote (solo filas `valido`/`advertencia`; las `error` se saltan) a través
    del MISMO `_ejecutar_por_entidad` que usa `ejecutar_filas`/`simulate()` — en tandas de `tamano_lote`
    filas (300 por defecto) para trocear el trabajo y agregar contadores incrementalmente.

    `id_tienda`: centro/tienda al que se escribe el stock importado (PRODUCTOS). Pedido explícito de
    negocio: la migración debe ir SIEMPRE al centro al que está conectado el usuario, nunca "a todos
    los centros" ni a uno por defecto — si no se pasa (`None`), `_ejecutar_por_entidad` cae en
    `db.stock.tienda_por_defecto` (la tienda de id más bajo de la empresa), que es el comportamiento
    HISTÓRICO pero NO el deseado para la GUI del asistente (que ahora siempre pasa el `id_tienda` de
    la sesión activa — ver `gui/migracion_gui.py::_AsistenteMigracion`); se deja `None` como valor por
    defecto aquí solo por compatibilidad con otros llamantes no interactivos de este motor.

    `on_progreso` (Fase B, GUI — parámetro ADITIVO, opcional): callable `(hecho, total)` invocada
    DESPUÉS de cada tanda con el nº de filas procesadas hasta ahora (no necesariamente todas
    confirmadas, ver más abajo) y el total del lote — pensado para alimentar una `QProgressBar` desde
    un worker en segundo plano (`QObject.moveToThread`), sin que este módulo dependa de Qt. Best-effort:
    una excepción dentro del callback nunca interrumpe el commit real.

    `debe_continuar` (Fase B, GUI — parámetro ADITIVO, opcional): callable `() -> bool` consultada
    ANTES de arrancar cada tanda NUEVA; si devuelve `False`, el bucle se detiene ahí — es la semántica
    HONESTA de "cancelar" que pide la especificación: las tandas YA confirmadas se quedan confirmadas
    (nunca se deshacen), solo se deja de iniciar trabajo nuevo. Sin este parámetro (`None`), se
    comporta exactamente igual que antes (compatibilidad total con los llamadores existentes).

    Nota de diseño (rollback parcial): cada tanda NO es una única transacción SQL — cada función de
    dominio (`crear_articulo`, `crear_cliente`, `crear_asiento`, `crear_cuenta`…) ya abre y confirma su
    PROPIA conexión por fila, porque así está construida esta capa (ver `conexion.py`: no hay forma de
    pasarle una conexión externa desde aquí). Esto es en realidad una garantía MÁS fuerte que "revertir
    solo la tanda fallida": cada fila es su propia unidad atómica, así que una fila mala nunca puede
    tirar hacia atrás una fila buena ya confirmada, ni dentro de la misma tanda ni entre tandas — y si
    se pierde la conexión a media tanda, las filas de ESA tanda ya confirmadas ANTES del fallo se
    quedan confirmadas (exactamente el "rollback parcial" pedido, a nivel de fila en vez de tanda).
    Excepción: SALDOS es un asiento ATÓMICO de doble partida (no decomponible fila a fila) — si falla,
    falla la tanda entera (ver `_cargar_saldos`).

    Al terminar, registra/actualiza el `import_trabajos` real (reutilizando `_registrar_trabajo`, sin
    duplicar esa lógica) con los contadores agregados, vuelca el detalle por fila a
    `import_trabajos_errores` y marca `migracion_lotes_staging.estado='confirmado'` (o `'cancelado'`
    si no se confirmó ninguna fila)."""
    lote = _obtener_lote_staging(id_lote_staging)
    if not lote:
        return {"ok": False, "error": "lote de staging no encontrado"}
    entidad, id_empresa, usuario = lote["entidad"], lote["id_empresa"], lote.get("usuario")
    filas_staging = _listar_filas_staging(id_lote_staging, estados=("valido", "advertencia"))
    if not filas_staging:
        return {"ok": False, "error": "no hay filas válidas/con advertencia para confirmar "
                                      "(ejecuta validate() primero)"}

    tamano_lote = max(1, int(tamano_lote))
    total = len(filas_staging)
    hechos = 0
    procesados = 0
    cancelado = False
    errores_acumulados = []
    for inicio in range(0, total, tamano_lote):
        if debe_continuar is not None:
            try:
                seguir = debe_continuar()
            except Exception as e:
                logger.debug("commit debe_continuar(%s): %s", id_lote_staging, e)
                seguir = True
            if not seguir:
                cancelado = True
                break
        tanda_staging = filas_staging[inicio:inicio + tamano_lote]
        filas, mapeo_identidad = _filas_canonicas_e_identidad(tanda_staging)
        try:
            res = _ejecutar_por_entidad(entidad, filas, mapeo_identidad, id_empresa,
                                        id_tienda=id_tienda, usuario=usuario, trazar_kardex=True)
        except Exception as e:
            logger.error("commit tanda(%s): %s", id_lote_staging, e)
            res = {"cargados": 0, "errores": [], "fallos_fila": [
                {"fila": i + 1, "motivo": str(e)} for i in range(len(tanda_staging))]}
        cargados_tanda = int(res.get("cargados", 0) or 0)
        hechos += cargados_tanda
        procesados += len(tanda_staging)
        errores_acumulados.append((tanda_staging, res.get("errores") or [], res.get("fallos_fila") or []))
        if on_progreso is not None:
            try:
                on_progreso(procesados, total)
            except Exception as e:
                logger.debug("commit on_progreso(%s): %s", id_lote_staging, e)

    fallidos = procesados - hechos
    if cancelado:
        estado_final = "parcial"
    else:
        estado_final = "completado" if fallidos == 0 else ("error" if hechos == 0 else "parcial")
    id_trabajo = _registrar_trabajo(id_empresa, f"staging:{id_lote_staging}", entidad, "staging",
                                    total, hechos, fallidos, usuario, estado=estado_final)
    for tanda_staging, errores_canon, fallos_fila in errores_acumulados:
        _registrar_errores_trabajo(id_trabajo, tanda_staging, errores_canon, fallos_fila)
    _marcar_lote(id_lote_staging, "confirmado" if hechos > 0 else "cancelado", id_trabajo=id_trabajo)
    return {"ok": hechos > 0, "total": total, "procesados": procesados, "confirmados": hechos,
            "fallidos": fallidos, "cancelado": cancelado, "id_trabajo": id_trabajo}


# ── Edición en línea de staging + errores de un trabajo YA ejecutado (Fase B, GUI) ───────────────
def actualizar_fila_staging(id_fila_staging, campo, valor) -> dict | None:
    """Edita el valor de UN campo de UNA fila de staging (edición en línea del panel de diagnóstico,
    Paso 3 del asistente) y la RE-VALIDA en el momento, sin tocar el resto del lote — la versión
    "scoped to that row" que pide la especificación, en vez de re-validar el lote entero por un solo
    campo editado. Devuelve `{"estado", "hallazgos"}` (misma forma que un ítem de `validate()['detalle']`)
    o `None` si la fila no existe. Aditiva: no la usa ningún llamador existente."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_lote_staging, datos_mapeados FROM migracion_filas_staging WHERE id=%s",
                        (id_fila_staging,))
            fila = _fila_a_dict_staging(cur, cur.fetchone())
            if not fila:
                return None
            try:
                datos = json.loads(fila.get("datos_mapeados") or "{}")
            except Exception:
                datos = {}
            datos[campo] = valor
            lote = _obtener_lote_staging(fila["id_lote_staging"])
            entidad = lote.get("entidad") if lote else None
            id_empresa = lote.get("id_empresa") if lote else None
            contexto = validadores.construir_contexto(entidad, id_empresa) if entidad else {}
            hallazgos = (validadores.validar_fila(entidad, datos, id_empresa=id_empresa, contexto=contexto)
                        if entidad else [])
            estado = validadores.estado_desde_hallazgos(hallazgos)
            cur.execute("UPDATE migracion_filas_staging SET datos_mapeados=%s, estado=%s WHERE id=%s",
                        (json.dumps(datos, ensure_ascii=False, default=str), estado, id_fila_staging))
            conn.commit()
            return {"estado": estado, "hallazgos": hallazgos}
    except Exception as e:
        logger.error("actualizar_fila_staging(%s): %s", id_fila_staging, e)
        return None


def errores_trabajo(id_trabajo, *, limite=2000) -> list:
    """Detalle fila a fila de una importación YA EJECUTADA (`import_trabajos_errores`) — alimenta el
    drill-down del Historial (Fase B: clic en una fila → ver qué falló y por qué) y la exportación del
    informe de errores. Aditiva: `trabajos_recientes()` ya daba los CONTADORES agregados; esta es la
    contraparte de detalle que faltaba."""
    from src.db.conexion import _filas_a_dicts
    if not id_trabajo:
        return []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM import_trabajos_errores WHERE id_trabajo=%s ORDER BY numero_fila "
                        "LIMIT %s", (id_trabajo, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("errores_trabajo(%s): %s", id_trabajo, e)
        return []


# ── Plantillas de mapeo (tabla `import_mapeos`, migración 0179 — existía sin usar) ──────────────
def guardar_plantilla_mapeo(nombre, entidad, origen, mapeo, id_empresa=None) -> int | None:
    """Guarda (o actualiza si ya existe una con el mismo nombre+entidad+empresa) un mapeo de columnas
    reutilizable, para no tener que re-mapear cada vez que se reimporta del mismo origen."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM import_mapeos WHERE id_empresa=%s AND entidad=%s AND nombre=%s",
                        (id_empresa, entidad, nombre))
            r = cur.fetchone()
            existente = (r[0] if r and not isinstance(r, dict) else r["id"]) if r else None
            if existente:
                cur.execute("UPDATE import_mapeos SET origen=%s, mapeo=%s, actualizado=NOW() WHERE id=%s",
                            (origen, json.dumps(mapeo, ensure_ascii=False), existente))
                conn.commit()
                return existente
            cur.execute("INSERT INTO import_mapeos (id_empresa, nombre, entidad, origen, mapeo) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (id_empresa, nombre, entidad, origen, json.dumps(mapeo, ensure_ascii=False)))
            id_plantilla = cur.lastrowid
            conn.commit()
            return id_plantilla
    except Exception as e:
        logger.error("guardar_plantilla_mapeo(%s): %s", nombre, e)
        return None


def listar_plantillas_mapeo(entidad=None, id_empresa=None) -> list:
    """Plantillas de mapeo guardadas del tenant, opcionalmente filtradas por entidad."""
    from src.db.conexion import _filas_a_dicts
    id_empresa = _emp(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if entidad:
        filtros.append("entidad=%s"); params.append(entidad)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, id_empresa, nombre, entidad, origen, creado, actualizado FROM "
                        "import_mapeos WHERE " + " AND ".join(filtros) + " ORDER BY nombre",
                        tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_plantillas_mapeo: %s", e)
        return []


def obtener_plantilla_mapeo(id_plantilla) -> dict | None:
    """Una plantilla concreta CON el mapeo ya deserializado (`dict`), lista para pasar a `stage()`/
    `ejecutar_filas()`."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM import_mapeos WHERE id=%s", (id_plantilla,))
            fila = _fila_a_dict_staging(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_plantilla_mapeo(%s): %s", id_plantilla, e)
        return None
    if not fila:
        return None
    try:
        fila["mapeo"] = json.loads(fila.get("mapeo") or "{}")
    except Exception:
        fila["mapeo"] = {}
    return fila
