"""
IOC · Fachada — punto único de verdad de la Identidad Operativa. Ofrece a cualquier módulo
(documentos, TPV, CRM, stock, RRHH, BI, SOMA…) la cadena de identidad completa
(empresa → centro → tienda → almacén → terminal → usuario) SIN depender de textos libres, y un puente
de compatibilidad con la feature legada `configuraciones.ref_tienda/ref_almacen` (patrón Strangler:
se conserva y se envuelve). Incluye los jobs de mantenimiento (opt-in) para el JobRegistry.

Regla de arquitectura: los módulos consultan la identidad a través de ESTA fachada; nunca acceden a
las tablas directamente desde la GUI.
"""

import logging

from src.services.identidad import _base as B

logger = logging.getLogger("identidad.facade")


# ── Identidad documental (cadena completa) ───────────────────────────────────
def identidad_documento(*, id_empresa=None, id_centro=None, id_tienda=None, id_almacen=None,
                        id_terminal=None, usuario=None) -> dict:
    """Devuelve la identidad operativa completa para estampar en cualquier documento/movimiento,
    resolviendo desde el contexto activo lo que no se pase explícitamente. Nunca lanza: best-effort."""
    id_empresa = B.emp(id_empresa)
    ident = {"id_empresa": id_empresa, "empresa_codigo": None, "empresa_nombre": None,
             "id_centro": id_centro, "centro_codigo": None, "centro_nombre": None, "centro_tipo": None,
             "id_tienda": id_tienda, "tienda_codigo": None,
             "id_almacen": id_almacen, "almacen_codigo": None,
             "id_terminal": id_terminal, "terminal_codigo": None,
             "usuario": usuario or B.usuario_actual()}
    # Empresa
    try:
        from src.db import empresa as _emp
        dc = _emp.datos_corporativos(id_empresa=id_empresa, id_tienda=id_tienda, id_centro=id_centro)
        if isinstance(dc, dict):
            ident["empresa_nombre"] = dc.get("nombre_empresa") or dc.get("empresa_nombre")
            ident["empresa_codigo"] = dc.get("codigo_empresa") or dc.get("empresa_codigo")
            ident["centro_codigo"] = dc.get("centro_codigo") or ident["centro_codigo"]
    except Exception as e:
        logger.debug("identidad_documento empresa: %s", e)
    # Centro (identidad IOC)
    if id_centro:
        try:
            from src.services.identidad import centros as _c
            c = _c.obtener_centro(id_centro) or {}
            ident["centro_nombre"] = c.get("nombre_centro")
            ident["centro_tipo"] = c.get("tipo")
            ident["centro_codigo"] = c.get("codigo_centro") or ident["centro_codigo"]
        except Exception:
            pass
    # Tienda
    if id_tienda is not None:
        try:
            from src.db.tiendas import obtener_tienda
            t = obtener_tienda(id_tienda) or {}
            ident["tienda_codigo"] = t.get("codigo_tienda")
        except Exception:
            pass
    # Terminal
    if id_terminal:
        try:
            from src.services.identidad import terminales as _t
            term = _t.obtener_terminal(id_terminal) or {}
            ident["terminal_codigo"] = term.get("codigo_terminal")
        except Exception:
            pass
    # Puente de compatibilidad: si no hay identidad estructurada, cae a la referencia legada.
    if not ident["centro_codigo"] and not ident["tienda_codigo"]:
        ref = referencia_legada()
        ident["ref_compat"] = ref
    return ident


# ── Puente de compatibilidad con la feature legada (Strangler) ───────────────
def referencia_legada() -> dict:
    """Lee la referencia legada (configuraciones.ref_tienda/ref_almacen) SIN modificarla."""
    try:
        from src.db.conexion import obtener_referencias
        return obtener_referencias() or {"ref_tienda": "", "ref_almacen": ""}
    except Exception:
        return {"ref_tienda": "", "ref_almacen": ""}


def etiqueta_operativa(id_empresa=None, id_tienda=None) -> str:
    """Etiqueta operativa de la terminal para la UI (chip del menú): el CÓDIGO IOC de la tienda activa.
    Cadena vacía si no hay tienda activa con código. La antigua referencia legada (`T-…`/`A-…`) se RETIRÓ
    (migración 0175); la identidad de la terminal vive ahora en Centros de trabajo (IOC)."""
    tid = id_tienda
    if tid is None:
        try:
            from src.db.empresa import tienda_actual_id
            tid = tienda_actual_id()
        except Exception:
            tid = None
    if tid is None:
        return ""
    try:
        from src.db.tiendas import obtener_tienda
        t = obtener_tienda(tid) or {}
        return (t.get("codigo_tienda") or "").strip()
    except Exception:
        return ""


def migrar_referencias_a_centros(id_empresa=None, *, sobrescribir=False) -> dict:
    """Fase 2 de la deprecación «Asignar referencia»: vuelca la referencia legada al código VISIBLE del
    centro IOC del tipo correspondiente (ref_tienda→centro TIENDA, ref_almacen→centro ALMACEN) de la empresa.

    IDEMPOTENTE: no sobrescribe un código VISIBLE ya existente salvo `sobrescribir=True`. NO borra la
    referencia legada (sigue como fallback hasta la Fase 3). Devuelve {tienda:{estado,...}, almacen:{...}}
    con estado ∈ {migrado, ya_tiene_codigo, sin_centro, sin_referencia, error}."""
    id_empresa = B.emp(id_empresa)
    ref = referencia_legada()
    from src.services.identidad import centros as _centros
    from src.services.identidad import codigos as _codigos
    resultado = {}
    for clave, ref_key, tipo_centro in (("tienda", "ref_tienda", "TIENDA"),
                                        ("almacen", "ref_almacen", "ALMACEN")):
        valor = (ref.get(ref_key) or "").strip()
        if not valor:
            resultado[clave] = {"estado": "sin_referencia"}
            continue
        centros = _centros.listar_centros(id_empresa=id_empresa, tipo=tipo_centro)
        if not centros:
            resultado[clave] = {"estado": "sin_centro", "valor": valor}
            continue
        idc = centros[0].get("id_centro")            # el principal primero (es_principal DESC)
        actual = _codigos.get_codigo(idc, "VISIBLE")
        if actual and not sobrescribir:
            resultado[clave] = {"estado": "ya_tiene_codigo", "id_centro": idc,
                                "codigo_actual": actual, "valor": valor}
            continue
        ok = _codigos.set_codigo(idc, "VISIBLE", valor, id_empresa=id_empresa)
        resultado[clave] = {"estado": "migrado" if ok else "error", "id_centro": idc, "valor": valor}
    return resultado


def migrar_referencia_a_centro(id_centro, *, tipo_codigo="VISIBLE", id_empresa=None) -> dict:
    """Puente Strangler: copia la referencia legada al código operativo del centro IOC, SIN borrar
    los campos ref_* (compatibilidad total). Permite migrar progresivamente los consumidores."""
    id_empresa = B.emp(id_empresa)
    ref = referencia_legada()
    valor = ref.get("ref_tienda") or ref.get("ref_almacen")
    if not valor:
        return {"ok": False, "motivo": "sin referencia legada"}
    try:
        from src.services.identidad import codigos
        ok = codigos.set_codigo(id_centro, tipo_codigo, valor, id_empresa=id_empresa)
        return {"ok": ok, "valor": valor, "id_centro": id_centro}
    except Exception as e:
        logger.error("migrar_referencia_a_centro: %s", e)
        return {"ok": False, "motivo": str(e)}


# ── Jobs de mantenimiento (opt-in, deshabilitados por defecto) ───────────────
def _job_validacion_centros(id_empresa=None) -> dict:
    """Valida integridad de centros (jerarquía padre existente, tipo válido). Solo informa."""
    id_empresa = B.emp(id_empresa)
    incidencias = 0
    try:
        from src.services.identidad import centros
        from src.services.identidad.tipos import TIPOS_CENTRO
        cs = centros.listar_centros(id_empresa=id_empresa, incluir_archivados=True, solo_activos=False)
        ids = {c.get("id_centro") for c in cs}
        for c in cs:
            padre = c.get("id_centro_padre")
            if padre and padre not in ids:
                incidencias += 1
            if (c.get("tipo") or "OTRO") not in TIPOS_CENTRO:
                incidencias += 1
    except Exception as e:
        logger.debug("_job_validacion_centros: %s", e)
    return {"incidencias": incidencias}


def _job_verificacion_terminales(id_empresa=None) -> dict:
    """Marca en MANTENIMIENTO los terminales sin conexión reciente (>30 días). Solo cuenta aquí."""
    id_empresa = B.emp(id_empresa)
    try:
        from src.services.identidad import terminales
        ts = terminales.listar_terminales(id_empresa=id_empresa)
        import datetime as _dt
        limite = _dt.datetime.now() - _dt.timedelta(days=30)
        obsoletos = 0
        for t in ts:
            uc = t.get("ultima_conexion")
            if uc and isinstance(uc, _dt.datetime) and uc < limite:
                obsoletos += 1
        return {"terminales": len(ts), "sin_conexion_reciente": obsoletos}
    except Exception as e:
        logger.debug("_job_verificacion_terminales: %s", e)
        return {"terminales": 0}


def _job_sincronizacion_identidades(id_empresa=None) -> dict:
    """Reservado: sincronización de identidades hacia servicios externos/SaaS. Placeholder opt-in."""
    return {"sincronizadas": 0}


def registrar_jobs_identidad(id_empresa=None):
    """Registra en el Scheduler los jobs IOC (los declara; el JobRegistry decide activación)."""
    try:
        from src.services import scheduler
        scheduler.registrar("identidad_validacion_centros", _job_validacion_centros)
        scheduler.registrar("identidad_verificacion_terminales", _job_verificacion_terminales)
        scheduler.registrar("identidad_sincronizacion", _job_sincronizacion_identidades)
        scheduler.registrar_job("identidad_validacion_centros", intervalo_horas=168,
                                descripcion="IOC · validación de integridad de centros")
        scheduler.registrar_job("identidad_verificacion_terminales", intervalo_horas=24,
                                descripcion="IOC · verificación de terminales")
        scheduler.registrar_job("identidad_sincronizacion", intervalo_horas=24,
                                descripcion="IOC · sincronización de identidades")
    except Exception as e:
        logger.debug("registrar_jobs_identidad: %s", e)
