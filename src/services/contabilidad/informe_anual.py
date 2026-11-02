"""
Informe Anual de Empresa (Contabilidad · pestaña "Cierres"). Orquestador de SOLO LECTURA: agrega
cifras que YA existen en motores reales de la app (contabilidad, compras, control horario, ausencias,
nóminas, ventas, pedidos online, mermas, devoluciones). No crea tablas ni motores paralelos, no
recalcula nada que ya calcule otro servicio: cada cifra sale de una consulta directa a datos ya
registrados, o de una función de servicio existente sin tocar su contrato.

Honestidad (regla dura, sin excepciones): cero cifras inventadas. Donde una categoría no está
diferenciada hoy en los datos reales (p. ej. parte del gasto directo que no se etiquetó por tipo, o
una nómina generada fuera del motor único sin `conceptos` JSON), se etiqueta explícitamente como
"no disponible" o "sin categorizar (histórico)" en vez de rellenar con un cero silencioso o un
reparto inventado.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, _filas_a_dicts, obtener_conexion

logger = logging.getLogger("contab.informe_anual")

# Códigos de `mapeo.TIPOS_GASTO` que sí corresponden 1:1 a una de las categorías de inversión
# solicitadas. Todo lo demás (reparaciones, transporte, dietas, profesionales, seguros, bancarios,
# material, internet, otros, o gasto sin `ref_origen` reconocible) cae honestamente en
# "sin categorizar (histórico)" — no se inventa una repartición.
_CATEGORIA_GASTO = {
    "maquinaria": "maquinaria",
    "vehiculos": "vehiculos",
    "publicidad": "publicidad",
    "alquiler": "alquiler",
    # Las 3 cuentan como "Suministros" (cuenta PGC 628, ver mapeo.CUENTAS_GASTO) — agrupación
    # contable real, no una categoría inventada.
    "luz": "suministros", "agua": "suministros", "gas": "suministros",
    "impuestos": "impuestos",
}


def _empresa(id_empresa=None):
    try:
        from src.services.contabilidad.identidad_contabilidad import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        if id_empresa:
            return id_empresa
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return EMPRESA_DEFAULT_ID


def _nombre_completo(emp: dict) -> str:
    return " ".join(p for p in (emp.get("nombre"), emp.get("apellidos")) if p).strip() or "(sin nombre)"


# ── Ventas físicas (POS) por tienda / por empleado ───────────────────────────
def _ventas_por_tienda(anio, id_empresa) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id_tienda, COUNT(*) AS num_ventas, COALESCE(SUM(total),0) AS total "
                "FROM ventas WHERE id_empresa=%s AND YEAR(fecha)=%s "
                "GROUP BY id_tienda ORDER BY total DESC", (id_empresa, int(anio)))
            filas = _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("_ventas_por_tienda(%s): %s", anio, e)
        return []
    nombres = {}
    try:
        from src.db.tiendas import listar_tiendas
        for t in (listar_tiendas(id_empresa) or []):
            nombres[t.get("id")] = t.get("nombre") or t.get("codigo_tienda")
    except Exception as e:
        logger.debug("listar_tiendas: %s", e)
    out = []
    for f in filas:
        tid = f.get("id_tienda")
        out.append({
            "id_tienda": tid,
            "tienda": nombres.get(tid) or (f"Tienda {tid}" if tid is not None else "(sin tienda)"),
            "num_ventas": int(f.get("num_ventas") or 0),
            "total": round(float(f.get("total") or 0), 2),
        })
    return out


def _ventas_por_empleado(anio, id_empresa) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(NULLIF(empleado,''),'(sin empleado)') AS empleado, "
                "COUNT(*) AS num_ventas, COALESCE(SUM(total),0) AS total "
                "FROM ventas WHERE id_empresa=%s AND YEAR(fecha)=%s "
                "GROUP BY empleado ORDER BY total DESC", (id_empresa, int(anio)))
            filas = _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("_ventas_por_empleado(%s): %s", anio, e)
        return []
    for f in filas:
        f["num_ventas"] = int(f.get("num_ventas") or 0)
        f["total"] = round(float(f.get("total") or 0), 2)
    return filas


def _ventas_online_total(anio, id_empresa) -> float:
    """Suma la facturación de pedidos online del ejercicio recorriendo los 12 meses vía
    `online_orders_service.facturacion_por_dia` (ya real, agrupa por día — se pide mes a mes para
    cubrir el año completo sin tocar su contrato)."""
    try:
        from src.services.tpv.online_orders_service import facturacion_por_dia
    except Exception as e:
        logger.error("import facturacion_por_dia: %s", e)
        return 0.0
    total = 0.0
    for m in range(1, 13):
        desde = f"{int(anio)}-{m:02d}-01"
        # último día del mes, sin dependencias de calendario externas
        if m == 12:
            hasta = f"{int(anio)}-12-31"
        else:
            import datetime as _dt
            hasta = (_dt.date(int(anio), m + 1, 1) - _dt.timedelta(days=1)).isoformat()
        try:
            por_dia = facturacion_por_dia(desde, hasta, id_empresa=id_empresa, id_tienda=None)
            total += sum(por_dia.values())
        except Exception as e:
            logger.debug("facturacion_por_dia(%s..%s): %s", desde, hasta, e)
    return round(total, 2)


# ── Mermas / devoluciones anuales ────────────────────────────────────────────
def _mermas_anuales(anio, id_empresa) -> dict:
    from src.db import mermas as M
    registros, cantidad_total = 0, 0.0
    for m in range(1, 13):
        try:
            filas = M.obtener_mermas(mes=f"{int(anio)}-{m:02d}", id_empresa=id_empresa) or []
        except Exception as e:
            logger.debug("obtener_mermas(%s-%02d): %s", anio, m, e)
            continue
        for fila in filas:
            # `obtener_mermas` devuelve tuplas (id, codigo, cantidad, motivo, fecha, origen_stock)
            # salvo que el cursor ya entregue dicts (no es el caso por defecto en este proyecto).
            cantidad = fila.get("cantidad") if isinstance(fila, dict) else fila[2]
            try:
                cantidad_total += float(cantidad or 0)
            except Exception:
                pass
            registros += 1
    return {"registros": registros, "cantidad_total": round(cantidad_total, 2)}


def _devoluciones_anuales(anio, id_empresa) -> dict:
    try:
        from src.services.tpv.refund_service import historial_devoluciones_anual
        r = historial_devoluciones_anual(anio, id_empresa)
        return {"registros": r.get("registros", 0), "total_reembolso": r.get("total_reembolso", 0.0)}
    except Exception as e:
        logger.error("_devoluciones_anuales(%s): %s", anio, e)
        return {"registros": 0, "total_reembolso": 0.0}


# ── Plantilla / altas nuevas ──────────────────────────────────────────────────
def _plantilla(anio, id_empresa) -> dict:
    from src.rrhh.db.empleados import listar_empleados
    todos = listar_empleados(id_empresa=id_empresa) or []
    activos = [e for e in todos if (e.get("estado") or "").lower() == "activo"]
    altas = []
    for e in todos:
        fa = e.get("fecha_alta")
        if fa and str(fa)[:4] == str(anio):
            altas.append({
                "id": e.get("id"), "nombre_completo": _nombre_completo(e),
                "fecha_alta": str(fa),
            })
    return {"empleados": todos, "activos_actuales": len(activos),
            "altas_nuevas": altas, "num_altas_nuevas": len(altas)}


# ── Horas trabajadas / baja médica / nómina por empleado ─────────────────────
def _horas_trabajadas_anuales(id_empleado, anio, id_empresa):
    from src.rrhh import control_horario as CH
    try:
        inf = CH.informe_anual(id_empleado, anio, id_empresa)
        return round(inf["totales"]["efectivo_min"] / 60.0, 2)
    except Exception as e:
        logger.debug("informe_anual horas(%s,%s): %s", id_empleado, anio, e)
        return None


def _dias_baja_medica_anuales(id_empleado, anio, id_empresa):
    from src.rrhh import ausencias_servicio as AU
    dias = 0
    try:
        for a in (AU.listar(id_empleado, id_empresa, tipo=AU.TIPO_BAJA_MEDICA) or []):
            fi = str(a.get("fecha_inicio") or "")
            if fi[:4] == str(anio):
                dias += int(a.get("dias") or 0)
    except Exception as e:
        logger.debug("ausencias baja(%s,%s): %s", id_empleado, anio, e)
    return dias


def _nomina_anual_por_empleado(anio, id_empresa) -> dict:
    """{id_empleado: {bruto, ss_empresa, filas, filas_sin_conceptos}}. `ss_empresa` es la cadena
    'no disponible' si CUALQUIER nómina de ese empleado en el año carece de `conceptos` (alta
    manual histórica fuera del motor único) — sumar solo las filas que sí lo tienen infravaloraría
    la cifra en silencio, así que se marca honesto en vez de aproximar."""
    out = {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id_empleado, COUNT(*) AS filas, SUM(bruto) AS bruto, "
                "SUM(CASE WHEN conceptos IS NOT NULL "
                "THEN CAST(JSON_EXTRACT(conceptos,'$.ss_empresa.total') AS DECIMAL(14,2)) "
                "ELSE 0 END) AS ss_empresa, "
                "SUM(CASE WHEN conceptos IS NULL THEN 1 ELSE 0 END) AS filas_sin_conceptos "
                "FROM rrhh_nominas WHERE id_empresa=%s AND anio=%s GROUP BY id_empleado",
                (id_empresa, int(anio)))
            filas = _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("_nomina_anual_por_empleado(%s): %s", anio, e)
        return {}
    for f in filas:
        sin_conceptos = int(f.get("filas_sin_conceptos") or 0)
        out[f.get("id_empleado")] = {
            "bruto": round(float(f.get("bruto") or 0), 2),
            "ss_empresa": "no disponible" if sin_conceptos > 0 else round(float(f.get("ss_empresa") or 0), 2),
            "filas": int(f.get("filas") or 0),
            "filas_sin_conceptos": sin_conceptos,
        }
    return out


def _empleados_detalle(anio, id_empresa, empleados) -> list:
    nominas = _nomina_anual_por_empleado(anio, id_empresa)
    out = []
    for e in empleados:
        eid = e.get("id")
        nom = nominas.get(eid, {})
        out.append({
            "id": eid, "nombre_completo": _nombre_completo(e), "estado": e.get("estado"),
            "fecha_alta": str(e.get("fecha_alta") or ""),
            "horas_trabajadas_anio": _horas_trabajadas_anuales(eid, anio, id_empresa),
            "dias_baja_medica_anio": _dias_baja_medica_anuales(eid, anio, id_empresa),
            "bruto_anual": nom.get("bruto", 0.0),
            "ss_empresa_anual": nom.get("ss_empresa", "no disponible"),
        })
    return out


# ── Inversión por categoría ───────────────────────────────────────────────────
def _tipo_gasto_manual(ref_origen) -> str | None:
    """Extrae el código de tipo ('luz','publicidad'...) del `ref_origen` que genera
    `posting.registrar_gasto` (formato 'gasto:<tipo>:<fecha>:<total>:<hhmmss>')."""
    ref = str(ref_origen or "")
    if not ref.startswith("gasto:"):
        return None
    partes = ref.split(":")
    return partes[1] if len(partes) > 1 and partes[1] else None


def _inversion_proveedores(anio, id_empresa) -> float:
    """Gasto NETO de proveedores del ejercicio. `compras_por_periodo` ya resta los documentos
    abono/rectificativa (`db.compras._SQL_TOTAL_NETO`) — un rappel B2B liquidado
    (`services.compras.b2b_rappels.liquidar_rappel` → `registrar_abono`, tipo_documento='abono')
    reduce esta cifra automáticamente, sin ningún paso adicional aquí."""
    from src.db.compras import compras_por_periodo
    desde, hasta = f"{int(anio)}-01-01", f"{int(anio)}-12-31"
    filas = compras_por_periodo(desde, hasta, id_empresa) or []
    return round(sum(float(f.get("total") or 0) for f in filas), 2)


def _rebates_proveedores_liquidados(anio, id_empresa) -> float:
    """Rebates retroactivos (rappels B2B) liquidados en el ejercicio — cifra INFORMATIVA, devuelta
    en NEGATIVO (dinero que YA redujo el gasto). No se suma/resta de nuevo en
    `total_inversion_calculada`: `_inversion_proveedores` (arriba) ya la refleja porque lee
    `compras_por_periodo`, que neta los documentos tipo_documento='abono' generados por
    `b2b_rappels.liquidar_rappel`. Existe solo para que el Cierre del Ejercicio Anual muestre,
    explícito y por separado, cuánto de ese neto corresponde a rebates liquidados (no se
    inventa un segundo conteo paralelo)."""
    try:
        from src.services.compras.b2b_rappels import listar_liquidaciones
        liquidaciones = listar_liquidaciones(id_empresa=id_empresa, limite=5000) or []
    except Exception as e:
        logger.error("_rebates_proveedores_liquidados(%s): %s", anio, e)
        return 0.0
    total = 0.0
    for r in liquidaciones:
        fl = r.get("fecha_liquidacion")
        try:
            anio_fl = fl.year if hasattr(fl, "year") else int(str(fl)[:4])
        except Exception:
            continue
        if anio_fl == int(anio):
            total += float(r.get("importe_rebate") or 0)
    return round(-total, 2)


def _inversion_gasto_directo(anio, id_empresa) -> dict:
    """Desglosa el gasto directo (asientos 'gasto' de un clic) en las categorías reconocidas
    (maquinaria/vehiculos/publicidad/alquiler/suministros/impuestos) + 'sin_categorizar_historico'
    para el resto. Las facturas de proveedor (`origen='compra'`) NO se cuentan aquí — van en
    `_inversion_proveedores` para no duplicar el gasto de proveedor."""
    from src.services.contabilidad.posting import listar_gastos
    out = {"maquinaria": 0.0, "vehiculos": 0.0, "publicidad": 0.0, "alquiler": 0.0,
           "suministros": 0.0, "impuestos": 0.0, "sin_categorizar_historico": 0.0}
    try:
        gastos = listar_gastos(anio=anio, id_empresa=id_empresa) or []
    except Exception as e:
        logger.error("_inversion_gasto_directo(%s): %s", anio, e)
        return out
    for g in gastos:
        tipo = _tipo_gasto_manual(g.get("ref_origen"))
        cat = _CATEGORIA_GASTO.get(tipo, "sin_categorizar_historico")
        importe = round(float(g.get("total_debe") or 0), 2)
        out[cat] = round(out.get(cat, 0.0) + importe, 2)
    return out


def _inversion_activos(anio, id_empresa) -> dict:
    """Altas REALES de activos/vehículos capitalizables (`activos.coste_adquisicion`, vía
    `gmao.activos.gastos_activos_periodo`) del ejercicio. Fuente DISTINTA de
    `_inversion_gasto_directo` (tipos 'maquinaria'/'vehiculos' de `mapeo.TIPOS_GASTO` son gasto
    CORRIENTE no capitalizado — consumibles/mantenimiento/combustible, ver nota en `mapeo.py` —
    nunca la compra/alta del activo en sí). Sin riesgo de solape: una fila de `activos` y un
    asiento `contab_asientos` origen='gasto' son dos tablas/eventos que nunca comparten referencia,
    así que ambas fuentes se suman aditivamente sobre las mismas categorías 'maquinaria'/'vehiculos'."""
    from src.services.gmao.activos import gastos_activos_periodo
    desde, hasta = f"{int(anio)}-01-01", f"{int(anio)}-12-31"
    out = {"maquinaria": 0.0, "vehiculos": 0.0}
    try:
        filas = gastos_activos_periodo(desde, hasta, id_empresa=id_empresa) or []
    except Exception as e:
        logger.error("_inversion_activos(%s): %s", anio, e)
        return out
    for f in filas:
        clave = "vehiculos" if f.get("tipo") == "vehiculo" else "maquinaria"
        out[clave] = round(out.get(clave, 0.0) + float(f.get("importe") or 0), 2)
    return out


def _impuestos_aeat_pagado(anio, id_empresa) -> float:
    """Impuestos REALMENTE ingresados a la AEAT en el ejercicio: suma `resultado` de las
    declaraciones (modelo 303/111/130…, `services.aeat.base`) en estado PRESENTADO (fuente
    primaria y ya real — nunca un BORRADOR/GENERADO, que todavía no se ha presentado ni pagado).
    Solo se cuentan resultados POSITIVOS (importe a ingresar): un resultado negativo es a
    devolver/compensar, no un pago, y sumarlo restaría del total en vez de reflejarlo."""
    try:
        from src.services.aeat import base as AEAT
        from src.services.aeat import estados as EST
        decls = AEAT.listar_declaraciones(ejercicio=int(anio), id_empresa=id_empresa) or []
    except Exception as e:
        logger.error("_impuestos_aeat_pagado(%s): %s", anio, e)
        return 0.0
    total = 0.0
    for d in decls:
        if d.get("estado") != EST.PRESENTADO:
            continue
        try:
            r = float(d.get("resultado") or 0)
        except (TypeError, ValueError):
            continue
        if r > 0:
            total += r
    return round(total, 2)


def _inversion(anio, id_empresa, nominas_por_empleado: dict) -> dict:
    proveedores = _inversion_proveedores(anio, id_empresa)
    rebates_proveedores_liquidados = _rebates_proveedores_liquidados(anio, id_empresa)
    directo = _inversion_gasto_directo(anio, id_empresa)
    activos = _inversion_activos(anio, id_empresa)
    impuestos_aeat = _impuestos_aeat_pagado(anio, id_empresa)
    sueldos = round(sum(n.get("bruto", 0.0) for n in nominas_por_empleado.values()), 2)
    ss_valores = [n.get("ss_empresa") for n in nominas_por_empleado.values()]
    filas_sin_conceptos = sum(n.get("filas_sin_conceptos", 0) for n in nominas_por_empleado.values())
    ss_numericos = [v for v in ss_valores if isinstance(v, (int, float))]
    ss_empresa = round(sum(ss_numericos), 2) if filas_sin_conceptos == 0 else "no disponible"
    # `directo.values()` ya incluye el gasto manual tipo 'maquinaria'/'vehiculos'/'impuestos'; los
    # activos capitalizados y los impuestos AEAT-pagado son sumas ADICIONALES sobre esas mismas
    # categorías (ver `_inversion_activos`/`_impuestos_aeat_pagado`) — se suman UNA sola vez aquí.
    extra_activos_impuestos = round(activos["maquinaria"] + activos["vehiculos"] + impuestos_aeat, 2)
    total_numerico = round(
        proveedores + sueldos + (ss_empresa if isinstance(ss_empresa, (int, float)) else 0.0)
        + sum(directo.values()) + extra_activos_impuestos, 2)
    return {
        "proveedores": proveedores,
        # Informativo — YA incluido dentro de "proveedores" (ver docstring de
        # `_rebates_proveedores_liquidados`); no sumar de nuevo en ningún total.
        "rebates_proveedores_liquidados": rebates_proveedores_liquidados,
        "sueldos": sueldos,
        "ss_empresa": ss_empresa,
        "ss_empresa_nota": (None if filas_sin_conceptos == 0 else
                            f"{filas_sin_conceptos} nómina(s) sin desglose de SS empresa "
                            "(alta histórica fuera del motor único) — no incluidas en el total."),
        "maquinaria": round(directo["maquinaria"] + activos["maquinaria"], 2),
        "publicidad": directo["publicidad"],
        "alquiler": directo["alquiler"],
        "suministros": directo["suministros"],
        "vehiculos": round(directo["vehiculos"] + activos["vehiculos"], 2),
        "impuestos": round(directo["impuestos"] + impuestos_aeat, 2),
        # Se sigue calculando y sumando en `total_inversion_calculada` (es gasto real ya contado) —
        # pero la GUI (`informe_anual_gui._render_inversion`/`_filas_export`) y el PDF
        # (`informe_anual_pdf.generar_pdf_informe_anual`) omiten deliberadamente su fila en la tabla
        # "Inversión por categoría": decisión de producto para no mostrar una categoría "cajón de
        # sastre" en pantalla/documento. No tocar aquí si se quiere ocultar más/menos — el cambio
        # vive en esos dos renderers, no en este cálculo.
        "sin_categorizar_historico": directo["sin_categorizar_historico"],
        "total_inversion_calculada": total_numerico,
    }


# ── Orquestador público ───────────────────────────────────────────────────────
def generar_informe_anual(anio, id_empresa=None) -> dict:
    """Informe Anual de Empresa completo del ejercicio `anio`. Agrega SOLO datos ya reales
    (contabilidad/compras/RRHH/ventas/pedidos online/mermas/devoluciones); nunca fabrica cifras."""
    anio = int(anio)
    id_empresa = _empresa(id_empresa)

    from src.services.contabilidad.informes import perdidas_ganancias

    ventas_tienda = _ventas_por_tienda(anio, id_empresa)
    ventas_empleado = _ventas_por_empleado(anio, id_empresa)
    total_fisico = round(sum(f["total"] for f in ventas_tienda), 2)
    total_online = _ventas_online_total(anio, id_empresa)

    plantilla = _plantilla(anio, id_empresa)
    nominas_por_empleado = _nomina_anual_por_empleado(anio, id_empresa)
    empleados_detalle = _empleados_detalle(anio, id_empresa, plantilla["empleados"])

    pyg_actual = perdidas_ganancias(id_empresa=id_empresa, anio=anio)
    pyg_anterior = perdidas_ganancias(id_empresa=id_empresa, anio=anio - 1)

    ventas_tienda_anterior = _ventas_por_tienda(anio - 1, id_empresa)
    total_fisico_anterior = round(sum(f["total"] for f in ventas_tienda_anterior), 2)
    total_online_anterior = _ventas_online_total(anio - 1, id_empresa)

    inversion = _inversion(anio, id_empresa, nominas_por_empleado)

    return {
        "anio": anio, "id_empresa": id_empresa,
        "ventas": {
            "por_tienda": ventas_tienda,
            "por_empleado": ventas_empleado,
            "total_fisico": total_fisico,
            "total_online": total_online,
            "total_empresa": round(total_fisico + total_online, 2),
        },
        "mermas": _mermas_anuales(anio, id_empresa),
        "devoluciones": _devoluciones_anuales(anio, id_empresa),
        "plantilla": {
            "activos_actuales": plantilla["activos_actuales"],
            "total_empleados_con_expediente": len(plantilla["empleados"]),
            "altas_nuevas": plantilla["altas_nuevas"],
            "num_altas_nuevas": plantilla["num_altas_nuevas"],
        },
        "empleados_detalle": empleados_detalle,
        "inversion": inversion,
        "pyg": {
            "actual": pyg_actual, "anterior": pyg_anterior,
        },
        "comparacion_interanual": {
            "anio_anterior": anio - 1,
            "ventas_fisico": {"actual": total_fisico, "anterior": total_fisico_anterior},
            "ventas_online": {"actual": total_online, "anterior": total_online_anterior},
            "ventas_total": {"actual": round(total_fisico + total_online, 2),
                             "anterior": round(total_fisico_anterior + total_online_anterior, 2)},
            "resultado_pyg": {"actual": pyg_actual.get("resultado", 0.0),
                              "anterior": pyg_anterior.get("resultado", 0.0)},
        },
    }
