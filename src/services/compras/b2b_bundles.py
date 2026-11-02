"""
Reglas de pack/bundle definidas por el PROVEEDOR (Smart Suppliers). Ver docstring de la migración
0281 (`src/database/migraciones/0281_b2b_promo_bundles.py`) para por qué esto es una tabla nueva y no
una reutilización de `rappel_tramos` (umbral de GASTO ACUMULADO retroactivo, un concepto distinto) ni
de `b2b_catalogo_escalones` (descuento por cantidad de UN solo artículo, no un emparejamiento A→B).

Dos formas de recompensa, ambas evaluadas aquí:
  - 'pct_descuento': "compra `cantidad_minima` de A, obtén `pct_descuento`% en cada unidad de B que ya
    tengas en el carrito" — la forma pedida explícitamente en la especificación.
  - 'precio_pack_fijo': variante bonus, precio fijo para el conjunto (cantidad_minima de A + 1 de B),
    aplicado por "packs" completos (floor) si el carrito contiene múltiplos de ambos.

Misma convención de ventana activa que `rappel_tramos` (fecha_inicio/fecha_fin + activo) — reutilizada
tal cual, ver `b2b_rappels._tramos_vigentes_ventana`.
"""

import datetime as _dt
import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.b2b_bundles")

FORMAS_RECOMPENSA = ("pct_descuento", "precio_pack_fijo")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _filas(cur):
    cols = [d[0] for d in cur.description]
    return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]


def _iso(d):
    """Normaliza DATE (string 'YYYY-MM-DD' o `datetime.date` leído de pymysql) a string ISO
    comparable lexicográficamente — mismo helper que `b2b_rappels._iso`."""
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("compras.b2b_bundles", accion, "b2b_promo_bundles", (detalle or "")[:255])
    except Exception:
        pass


def _hoy_iso():
    return _dt.date.today().isoformat()


# ── Alta / listado ───────────────────────────────────────────────────────────
def crear_regla_bundle(id_suministrador, nombre, *, codigo_disparador, cantidad_minima,
                       codigo_recompensa, fecha_inicio, fecha_fin, forma_recompensa="pct_descuento",
                       pct_descuento=None, precio_pack_fijo=None, creado_por=None) -> dict:
    """Da de alta una regla de bundle del proveedor. Valida que el disparador y la recompensa sean
    artículos DISTINTOS y activos del PROPIO catálogo del proveedor (nunca se acepta un código que no
    pertenece a su catálogo: una regla sobre un artículo ajeno no tendría cómo aplicarse nunca)."""
    nombre = str(nombre or "").strip()
    codigo_disparador = str(codigo_disparador or "").strip()
    codigo_recompensa = str(codigo_recompensa or "").strip()
    if not nombre:
        return {"ok": False, "error": "nombre_obligatorio"}
    if not codigo_disparador or not codigo_recompensa:
        return {"ok": False, "error": "codigos_obligatorios"}
    if codigo_disparador == codigo_recompensa:
        return {"ok": False, "error": "disparador_y_recompensa_deben_ser_distintos"}
    try:
        cantidad_minima = int(cantidad_minima)
        if cantidad_minima < 1:
            return {"ok": False, "error": "cantidad_minima_debe_ser_mayor_o_igual_a_1"}
    except (TypeError, ValueError):
        return {"ok": False, "error": "cantidad_minima_invalida"}
    if forma_recompensa not in FORMAS_RECOMPENSA:
        return {"ok": False, "error": "forma_recompensa_invalida"}
    if forma_recompensa == "pct_descuento":
        try:
            pct_descuento = float(pct_descuento)
        except (TypeError, ValueError):
            return {"ok": False, "error": "pct_descuento_obligatorio_para_esta_forma"}
        if not (0 < pct_descuento <= 100):
            return {"ok": False, "error": "pct_descuento_debe_estar_entre_0_y_100"}
        precio_pack_fijo = None
    else:
        try:
            precio_pack_fijo = float(precio_pack_fijo)
        except (TypeError, ValueError):
            return {"ok": False, "error": "precio_pack_fijo_obligatorio_para_esta_forma"}
        if precio_pack_fijo < 0:
            return {"ok": False, "error": "precio_pack_fijo_no_puede_ser_negativo"}
        pct_descuento = None
    if not fecha_inicio or not fecha_fin or _iso(fecha_fin) < _iso(fecha_inicio):
        return {"ok": False, "error": "ventana_de_fechas_invalida"}

    try:
        from src.services.compras import b2b_catalogo as CAT
        if not CAT.obtener_activo(id_suministrador, codigo_disparador):
            return {"ok": False, "error": "codigo_disparador_no_pertenece_al_catalogo_del_proveedor"}
        if not CAT.obtener_activo(id_suministrador, codigo_recompensa):
            return {"ok": False, "error": "codigo_recompensa_no_pertenece_al_catalogo_del_proveedor"}
    except Exception as e:
        logger.error("crear_regla_bundle: validando catálogo (%s): %s", id_suministrador, e)
        return {"ok": False, "error": "error_interno"}

    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO b2b_promo_bundles (id_suministrador, nombre, codigo_disparador, "
                "cantidad_minima, codigo_recompensa, forma_recompensa, pct_descuento, "
                "precio_pack_fijo, fecha_inicio, fecha_fin, creado_por) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_suministrador, nombre, codigo_disparador, cantidad_minima, codigo_recompensa,
                 forma_recompensa, pct_descuento, precio_pack_fijo, fecha_inicio, fecha_fin,
                 creado_por))
            id_regla = cur.lastrowid
            conn.commit()
        _audit("REGLA_ALTA", f"{id_regla}:sum={id_suministrador} {codigo_disparador}x{cantidad_minima}"
                             f"->{codigo_recompensa} ({forma_recompensa})")
        return {"ok": True, "id": id_regla}
    except Exception as e:
        logger.error("crear_regla_bundle(%s,%s): %s", id_suministrador, nombre, e)
        return {"ok": False, "error": "error_interno"}


def listar_reglas(id_suministrador=None, *, solo_activas=False) -> list:
    """Reglas de bundle, opcionalmente filtradas por proveedor y/o solo las activas y vigentes hoy."""
    try:
        ensure_schema()
        filtros, params = [], []
        if id_suministrador:
            filtros.append("id_suministrador=%s")
            params.append(id_suministrador)
        where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM b2b_promo_bundles {where} "
                        f"ORDER BY id_suministrador, nombre", params)
            reglas = _filas(cur)
        if solo_activas:
            hoy = _hoy_iso()
            reglas = [r for r in reglas if r.get("activo")
                     and _iso(r["fecha_inicio"]) <= hoy <= _iso(r["fecha_fin"])]
        return reglas
    except Exception as e:
        logger.error("listar_reglas(%s): %s", id_suministrador, e)
        return []


def desactivar_regla(id_suministrador, id_regla) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE b2b_promo_bundles SET activo=0 WHERE id=%s AND id_suministrador=%s",
                        (id_regla, id_suministrador))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("desactivar_regla(%s,%s): %s", id_suministrador, id_regla, e)
        return False


# ── Aplicabilidad (vista de producto) ────────────────────────────────────────
def reglas_aplicables_a_producto(codigo_articulo, id_empresa, *, id_suministrador=None) -> list:
    """Reglas de bundle VIGENTES en las que `codigo_articulo` participa, como disparador (A) o como
    recompensa (B) — útil para mostrar "Ahorra comprando el Pack" tanto en la ficha de A como en la
    de B. `id_suministrador` estrecha la búsqueda cuando ya se conoce (p. ej. desde la fila del
    catálogo que originó la vista de producto); sin él, se buscan TODOS los proveedores visibles para
    `id_empresa` (mismo criterio de sector que `b2b_catalogo.buscar_para_empresa`) que tengan ese
    código en su catálogo activo.

    `id_empresa` es obligatorio: nunca se devuelve una regla de un proveedor fuera del sector
    (compatible) de la empresa que está mirando el producto — mismo aislamiento que el resto del
    catálogo B2B."""
    codigo_articulo = str(codigo_articulo or "").strip()
    if not codigo_articulo or not id_empresa:
        return []
    try:
        ensure_schema()
        if id_suministrador:
            proveedores = [id_suministrador]
        else:
            proveedores = _proveedores_visibles_con_codigo(codigo_articulo, id_empresa)
        if not proveedores:
            return []
        placeholders = ",".join(["%s"] * len(proveedores))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM b2b_promo_bundles WHERE id_suministrador IN ({placeholders}) "
                f"AND activo=1 AND (codigo_disparador=%s OR codigo_recompensa=%s) "
                f"AND CURDATE() BETWEEN fecha_inicio AND fecha_fin",
                [*proveedores, codigo_articulo, codigo_articulo])
            return _filas(cur)
    except Exception as e:
        logger.error("reglas_aplicables_a_producto(%s,%s): %s", codigo_articulo, id_empresa, e)
        return []


def _proveedores_visibles_con_codigo(codigo_articulo, id_empresa) -> list:
    """IDs de suministrador que tienen `codigo_articulo` activo en su catálogo Y son visibles para
    `id_empresa` (sector propio o compatible) — mismo filtro de aislamiento que
    `b2b_catalogo.buscar_para_empresa`, resuelto aquí porque esta función solo recibe el código, no
    la empresa->sector ya resuelta."""
    try:
        from src.services.compras import sectores
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT sector_id FROM empresas WHERE id_empresa=%s", (id_empresa,))
            row = cur.fetchone()
            sector_id = row[0] if row and not isinstance(row, dict) else (row or {}).get("sector_id")
        if not sector_id:
            return []
        sector_ids = sectores.compatibles_de(sector_id)
        if not sector_ids:
            return []
        placeholders = ",".join(["%s"] * len(sector_ids))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT id_suministrador FROM b2b_catalogo WHERE codigo=%s AND activo=1 "
                f"AND sector_id IN ({placeholders})", [codigo_articulo, *sector_ids])
            return [r[0] if not isinstance(r, dict) else r["id_suministrador"] for r in cur.fetchall()]
    except Exception as e:
        logger.error("_proveedores_visibles_con_codigo(%s,%s): %s", codigo_articulo, id_empresa, e)
        return []


# ── Cálculo sobre el carrito ─────────────────────────────────────────────────
def _cantidad_en_carrito(lineas, codigo) -> int:
    return sum(int(l.get("cantidad") or 0) for l in (lineas or []) if l.get("codigo") == codigo)


def _precio_en_carrito(lineas, codigo) -> float:
    """Precio unitario de `codigo` tal como figura en el carrito (primera línea que lo tenga) — 0.0 si
    no está presente (nunca se inventa un precio para un artículo que el comprador no ha añadido)."""
    for l in lineas or []:
        if l.get("codigo") == codigo:
            return float(l.get("precio_unitario") or 0)
    return 0.0


def calcular_descuento_bundle(carrito_lineas, reglas) -> list:
    """Dadas las líneas actuales del carrito (forma de `b2b_carrito.listar`) y una lista de reglas
    (de `listar_reglas`/`reglas_aplicables_a_producto`, ya filtradas por el llamante a las vigentes),
    calcula qué descuento gana CADA regla con el contenido actual del carrito. Nunca modifica el
    carrito — solo informa; `b2b_pedidos.tramitar`/el checkout decide si aplicarlo al precio final.

    Devuelve una lista de dicts, uno por regla: {id_regla, nombre, codigo_disparador,
    cantidad_minima, cantidad_disparador_en_carrito, cumple, codigo_recompensa, forma_recompensa,
    cantidad_recompensa_en_carrito, descuento_unitario, descuento_total}."""
    resultados = []
    hoy = _hoy_iso()
    for r in reglas or []:
        if not r.get("activo", True):
            continue
        if not (_iso(r["fecha_inicio"]) <= hoy <= _iso(r["fecha_fin"])):
            continue
        cant_a = _cantidad_en_carrito(carrito_lineas, r["codigo_disparador"])
        cant_min = int(r["cantidad_minima"])
        cumple = cant_a >= cant_min
        cant_b = _cantidad_en_carrito(carrito_lineas, r["codigo_recompensa"])
        precio_b = _precio_en_carrito(carrito_lineas, r["codigo_recompensa"])
        descuento_unitario = 0.0
        descuento_total = 0.0
        if cumple and cant_b > 0:
            if r["forma_recompensa"] == "pct_descuento":
                pct = float(r.get("pct_descuento") or 0)
                descuento_unitario = round(precio_b * pct / 100.0, 2)
                descuento_total = round(descuento_unitario * cant_b, 2)
            else:  # precio_pack_fijo
                precio_a = _precio_en_carrito(carrito_lineas, r["codigo_disparador"])
                n_packs = min(cant_a // cant_min, cant_b) if cant_min else 0
                if n_packs > 0:
                    coste_pack_normal = precio_a * cant_min + precio_b
                    ahorro_pack = max(0.0, coste_pack_normal - float(r.get("precio_pack_fijo") or 0))
                    descuento_total = round(ahorro_pack * n_packs, 2)
                    descuento_unitario = round(ahorro_pack / cant_min, 2) if cant_min else 0.0
        resultados.append({
            "id_regla": r["id"], "nombre": r["nombre"], "codigo_disparador": r["codigo_disparador"],
            "cantidad_minima": cant_min, "cantidad_disparador_en_carrito": cant_a, "cumple": cumple,
            "codigo_recompensa": r["codigo_recompensa"], "forma_recompensa": r["forma_recompensa"],
            "pct_descuento": r.get("pct_descuento"), "precio_pack_fijo": r.get("precio_pack_fijo"),
            "cantidad_recompensa_en_carrito": cant_b, "descuento_unitario": descuento_unitario,
            "descuento_total": descuento_total,
        })
    return resultados


def descuento_total_carrito(carrito_lineas, reglas) -> float:
    """Suma de `descuento_total` de todas las reglas efectivamente ganadas — atajo para el checkout."""
    return round(sum(c["descuento_total"] for c in calcular_descuento_bundle(carrito_lineas, reglas)
                     if c["cumple"]), 2)


# ── Progreso combinado (bundle + rappel) para el "termómetro" del carrito ────
def progreso_mas_cercano(id_empresa, carrito_lineas) -> dict | None:
    """Para el carrito actual (de UN solo proveedor, ver `b2b_carrito.anadir`), compara cuánto falta
    para desbloquear el próximo escalón de descuento entre los DOS sistemas — reglas de bundle (este
    módulo) y tramos de rappel (`b2b_rappels`, umbral de gasto acumulado) — y devuelve el que esté más
    cerca de alcanzarse (o `None` si no hay ningún escalón pendiente en ninguno de los dos). Pensado
    para el "termómetro" del carrito del Portal Empresa (`portal_empresa_b2b.py::pagina_carrito`).

    No reimplementa el cálculo de ninguno de los dos sistemas: reutiliza
    `b2b_rappels.gasto_acumulado`/`tramo_alcanzado`/`listar_tramos` tal cual (mismo criterio pedido:
    "reusa las funciones existentes del lado rappel")."""
    if not carrito_lineas:
        return None
    id_suministrador = carrito_lineas[0].get("id_suministrador")
    candidatos = []

    # Lado bundle: para cada regla vigente aplicable a este proveedor, cuánto falta de A.
    for r in listar_reglas(id_suministrador, solo_activas=True):
        cant_a = _cantidad_en_carrito(carrito_lineas, r["codigo_disparador"])
        cant_min = int(r["cantidad_minima"])
        if cant_a >= cant_min or cant_min <= 0:
            continue  # ya desbloqueado, o regla sin sentido — no es un "próximo" escalón
        faltan = cant_min - cant_a
        pct_progreso = round(cant_a / cant_min * 100, 1)
        if r["forma_recompensa"] == "pct_descuento":
            etiqueta_premio = f"{r.get('pct_descuento')}% en {r['codigo_recompensa']}"
        else:
            etiqueta_premio = f"precio especial en el pack con {r['codigo_recompensa']}"
        candidatos.append({
            "tipo": "bundle", "id_regla": r["id"], "nombre": r["nombre"], "faltan": faltan,
            "pct_progreso": pct_progreso, "etiqueta": f"Añade {faltan} unidad(es) más de "
            f"{r['codigo_disparador']} para desbloquear {etiqueta_premio}.",
        })

    # Lado rappel: próximo tramo de gasto acumulado del mismo proveedor.
    if id_suministrador:
        try:
            from src.services.compras import b2b_rappels as RAP
            tramos = RAP.listar_tramos(id_empresa, id_suministrador)
            prog = RAP.progreso_suministrador(id_empresa, id_suministrador, tramos=tramos)
            siguiente = prog.get("siguiente_tramo")
            if prog.get("tiene_tramos") and siguiente:
                gasto = float(prog.get("gasto_acumulado") or 0)
                techo = float(siguiente["umbral_desde"])
                falta_importe = round(max(0.0, techo - gasto), 2)
                pct_progreso = round(min(gasto / techo * 100, 100), 1) if techo else 0.0
                if falta_importe > 0:
                    candidatos.append({
                        "tipo": "rappel", "id_regla": siguiente.get("id"),
                        "nombre": f"Rebate por volumen ({siguiente['pct_rebate']}%)",
                        "faltan": falta_importe, "pct_progreso": pct_progreso,
                        "etiqueta": f"Gasta {falta_importe} € más con este proveedor para desbloquear "
                        f"un {siguiente['pct_rebate']}% adicional de rebate.",
                    })
        except Exception as e:
            logger.debug("progreso_mas_cercano/rappel(%s,%s): %s", id_empresa, id_suministrador, e)

    if not candidatos:
        return None
    # "Más cerca" = mayor % de progreso ya alcanzado (el escalón que menos esfuerzo relativo falta
    # para desbloquear), no la menor cantidad absoluta — comparar unidades de A contra euros de
    # gasto directamente no sería homogéneo.
    return max(candidatos, key=lambda c: c["pct_progreso"])
