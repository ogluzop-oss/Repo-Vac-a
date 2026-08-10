"""
Motor de ingesta (Fase 1). Orquesta lectura → mapeo → validación (dry-run) → carga a los MOTORES OFICIALES
(N7): `db/articulos` (upsert por `codigo`), `db/familias` (alta/vínculo `id_familia`) y stock por `db/stock`
(persistente por tienda) + kárdex (`db/kardex` AJUSTE, traza). Multi-tenant: todo con `id_empresa`. Idempotente:
re-importar el mismo fichero ACTUALIZA (no duplica) y FIJA el stock (no lo suma). Sin PyQt.
"""

import logging
import os

from src.db.conexion import obtener_conexion
from src.services.importacion import lectores, mapeo as _map
from src.services.importacion.modelo import (
    CLIENTES, PRODUCTOS, PROVEEDORES, SALDOS, TESORERIA, VENTAS_HIST,
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
    """Convierte cada fila de origen a valores canónicos parseados. Devuelve (validas, errores)."""
    validas, errores = [], []
    for i, fila in enumerate(filas, start=1):
        c = _map.aplicar_mapeo(fila, mapeo)
        codigo = limpiar_texto(c.get("codigo"))
        if not codigo:
            errores.append({"fila": i, "motivo": "sin código de artículo"})
            continue
        validas.append({
            "codigo": codigo,
            "nombre": limpiar_texto(c.get("nombre")),
            "descripcion": limpiar_texto(c.get("descripcion")),
            "precio": parse_precio(c.get("precio")) if "precio" in mapeo else None,
            "familia": limpiar_texto(c.get("familia")) if "familia" in mapeo else None,
            "stock": parse_stock(c.get("stock")) if "stock" in mapeo else None,
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
    if entidad == CLIENTES:
        res = _cargar_terceros(filas, mapeo, id_empresa, "cliente")
    elif entidad == PROVEEDORES:
        res = _cargar_terceros(filas, mapeo, id_empresa, "proveedor")
    elif entidad == VENTAS_HIST:
        res = _cargar_ventas_hist(filas, mapeo, id_empresa)
    elif entidad == SALDOS:
        res = _cargar_saldos(filas, mapeo, id_empresa, usuario)
    elif entidad == TESORERIA:
        res = _cargar_tesoreria(filas, mapeo, id_empresa, usuario)
    else:
        res = _cargar_productos(filas, mapeo, id_empresa, id_tienda, usuario, trazar_kardex)
    res["id_trabajo"] = _registrar_trabajo(id_empresa, origen, entidad, formato, len(filas),
                                           res.get("cargados", 0),
                                           res.get("errores_n", len(res.get("errores", []))),
                                           usuario, estado=("completado" if res.get("ok") else "error"))
    return res


def _cargar_productos(filas, mapeo, id_empresa, id_tienda, usuario, trazar_kardex) -> dict:
    """Carga de PRODUCTOS: upsert `articulos` + familias + stock (kárdex). Idempotente."""
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

    # Columnas de `articulos` a upsertar: solo las mapeadas (no se pisan con NULL las no mapeadas).
    cols = ["codigo", "id_empresa"]
    if "nombre" in mapeo:
        cols.append("nombre")
    if "descripcion" in mapeo:
        cols.append("descripcion")
    if "precio" in mapeo:
        cols.append("precio")
    if "familia" in mapeo:
        cols.append("id_familia")
    if img_cache:                     # solo si al menos una imagen se resolvió
        cols.append("imagen")
    hay_stock = "stock" in mapeo
    if hay_stock:
        cols += ["Stock_total", "Stock_tienda"]

    def _valor(v, col):
        if col == "codigo":
            return v["codigo"]
        if col == "id_empresa":
            return id_empresa
        if col == "nombre":
            return v["nombre"]
        if col == "descripcion":
            return v["descripcion"]
        if col == "precio":
            return v["precio"] if v["precio"] is not None else 0
        if col == "id_familia":
            return fam_cache.get((v["familia"] or "").strip().lower()) if v["familia"] else None
        if col == "imagen":
            return img_cache.get(v["codigo"])
        if col in ("Stock_total", "Stock_tienda"):
            return v["stock"] if v["stock"] is not None else 0
        return None

    ph = ",".join(["%s"] * len(cols))
    # `imagen` con COALESCE: una reimportación sin imagen (o sin red) NO borra la imagen ya guardada.
    set_upd = ",".join(
        (f"`{c}`=COALESCE(VALUES(`{c}`),`{c}`)" if c == "imagen" else f"`{c}`=VALUES(`{c}`)")
        for c in cols if c != "codigo")
    sql = f"INSERT INTO articulos ({','.join(f'`{c}`' for c in cols)}) VALUES ({ph}) ON DUPLICATE KEY UPDATE {set_upd}"
    datos = [[_valor(v, c) for c in cols] for v in validas]

    cargados = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.executemany(sql, datos)
            cargados = len(datos)
            # Stock persistente por tienda (además de las columnas de trabajo ya fijadas arriba).
            tid = _tienda(id_empresa, id_tienda) if hay_stock else None
            if hay_stock and tid is not None:
                st = [[id_empresa, tid, v["codigo"], (v["stock"] or 0)] for v in validas if v["stock"] is not None]
                if st:
                    cur.executemany(
                        "INSERT INTO stock_tienda (id_empresa, id_tienda, codigo_articulo, stock) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE stock=VALUES(stock)", st)
            conn.commit()
    except Exception as e:
        logger.error("ejecutar/carga: %s", e)
        return {"ok": False, "error": str(e)}

    # Kárdex (traza de existencias inicial) — best-effort, fuera de la transacción de stock.
    con_stock = sum(1 for v in validas if v["stock"] is not None)
    if trazar_kardex and hay_stock:
        try:
            from src.db.kardex import registrar_movimiento
            tid = _tienda(id_empresa, id_tienda)
            for v in validas:
                if v["stock"] is not None:
                    registrar_movimiento(v["codigo"], "AJUSTE", v["stock"], id_empresa=id_empresa,
                                         id_tienda=tid, usuario=usuario, observaciones="Importación inicial")
        except Exception as e:
            logger.debug("kardex import: %s", e)

    return {"ok": True, "cargados": cargados, "familias_creadas": fam_creadas, "con_stock": con_stock,
            "imagenes": len(img_cache), "errores": errores[:200], "errores_n": len(errores)}


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
        validas.append({"nombre": nombre, "nif": limpiar_texto(c.get("nif")),
                        "email": limpiar_texto(c.get("email")), "telefono": limpiar_texto(c.get("telefono")),
                        "direccion": limpiar_texto(c.get("direccion"))})
    if not validas:
        return {"ok": False, "error": "no hay filas válidas", "errores": errores[:200],
                "errores_n": len(errores)}
    creados = actualizados = 0
    for v in validas:
        existente = _buscar_tercero(v["nif"], id_empresa, tipo) if v["nif"] else None
        if existente:
            _actualizar_tercero(existente, v, id_empresa, tipo)
            actualizados += 1
        elif _crear_tercero(v, id_empresa, tipo):
            creados += 1
    return {"ok": True, "cargados": creados + actualizados, "creados": creados,
            "actualizados": actualizados, "errores": errores[:200], "errores_n": len(errores)}


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
    """Histórico de ventas → `ventas_historicas` (SOLO forecasting; NO toca `ventas` ni finanzas). Idempotente
    por (empresa, fecha, código)."""
    datos, errores = [], []
    for i, fila in enumerate(filas, start=1):
        c = _map.aplicar_mapeo(fila, mapeo)
        fecha = parse_fecha(c.get("fecha"))
        codigo = limpiar_texto(c.get("codigo"))
        if not fecha or not codigo:
            errores.append({"fila": i, "motivo": "falta fecha o código válidos"})
            continue
        cant = parse_precio(c.get("cantidad")) if "cantidad" in mapeo else None
        imp = parse_precio(c.get("importe")) if "importe" in mapeo else None
        datos.append([id_empresa, fecha, codigo, cant or 0, imp or 0])
    if not datos:
        return {"ok": False, "error": "no hay filas válidas", "errores": errores[:200],
                "errores_n": len(errores)}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO ventas_historicas (id_empresa, fecha, codigo_articulo, cantidad, importe) "
                "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE cantidad=VALUES(cantidad), "
                "importe=VALUES(importe)", datos)
            conn.commit()
    except Exception as e:
        logger.error("_cargar_ventas_hist: %s", e)
        return {"ok": False, "error": str(e)}
    return {"ok": True, "cargados": len(datos), "errores": errores[:200], "errores_n": len(errores)}


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
        lineas.append({"cuenta": cuenta, "debe": debe, "haber": haber,
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
        return {"ok": False, "error": str(e)}
    if not res:
        return {"ok": False, "error": "el asiento de apertura no cuadra (Σdebe≠Σhaber) o el ejercicio está "
                                      "cerrado; revisa los saldos.", "errores": errores[:200],
                "errores_n": len(errores)}
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
