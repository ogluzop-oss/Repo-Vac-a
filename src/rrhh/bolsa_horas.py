"""
Bolsa de horas — distribución irregular de jornada (RRHH Fase E; cimientos en Fase A/B).

Motor PURO de cálculo día a día (`calcular_bolsa_horas`, sin BD/Qt, independientemente testable)
más una capa fina de acceso a `rrhh_bolsa_horas` (lectura de la fila de seguimiento del empleado,
UPDATE de `horas_diarias` cuando un ADMINISTRADOR/SUPERADMIN la define desde Horarios) y un
orquestador impuro (`calcular_bolsa_horas_empleado`) que reúne festivos/bajas/fichajes reales y
delega el cálculo en la función pura.

Punto de extensión previsto para la Fase F (nómina): cuando el contrato tenga
`bolsa_horas_compensacion='pago'`, las "horas a compensar por la empresa" de
`calcular_bolsa_horas_empleado` se suman como devengo extra en el borrador de nómina del mes
siguiente — reutilizar estas funciones, no duplicar el acceso a `rrhh_bolsa_horas`.
"""

import datetime as _dt
import logging
import re as _re

from src.db.conexion import _fila_a_dict, ensure_schema, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("rrhh.bolsa_horas")


# ── Acceso a `rrhh_bolsa_horas` ──────────────────────────────────────────────

def obtener_bolsa_horas(id_empleado, id_empresa=None) -> "dict | None":
    """Fila de seguimiento MÁS RECIENTE de `rrhh_bolsa_horas` para el empleado (normalmente hay
    una sola, la del contrato firmado con la cláusula activa). `None` si el empleado no tiene
    ninguna (su contrato no tiene la cláusula, o el contrato aún no se ha firmado — Fase B,
    `contratos.marcar_firmado`)."""
    id_empresa = id_empresa or empresa_actual_id()
    if not id_empleado:
        return None
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM rrhh_bolsa_horas WHERE id_empleado=%s AND id_empresa=%s "
                "ORDER BY fecha_creacion DESC, id DESC LIMIT 1",
                (id_empleado, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_bolsa_horas(%s): %s", id_empleado, e)
        return None


def definir_horas_diarias(id_bolsa_horas, horas_diarias, id_empresa=None) -> bool:
    """Define `horas_diarias` (DECIMAL(4,2)) de una fila YA EXISTENTE de `rrhh_bolsa_horas`
    (creada automáticamente por `rrhh.db.contratos.marcar_firmado`). El gate de rol
    (ADMINISTRADOR/SUPERADMIN) vive en la GUI (`rrhh/gui/bolsa_horas_dialog.py`); aquí solo se
    valida el rango del valor."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        horas = float(horas_diarias)
    except (TypeError, ValueError):
        raise ValueError("Horas diarias no válidas.")
    if horas <= 0 or horas > 24:
        raise ValueError("Las horas diarias deben estar entre 0 y 24.")
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE rrhh_bolsa_horas SET horas_diarias=%s WHERE id=%s AND id_empresa=%s",
                (round(horas, 2), id_bolsa_horas, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("definir_horas_diarias(%s): %s", id_bolsa_horas, e)
        return False


# ── Motor puro (independientemente testable) ─────────────────────────────────

def calcular_bolsa_horas(id_empleado, fecha_inicio, fecha_fin, horas_diarias,
                          dias_festivos, dias_baja, fichajes_por_dia) -> dict:
    """Calcula el saldo de la bolsa de horas DÍA A DÍA sobre `[fecha_inicio, fecha_fin]` (ambos
    incluidos, `date`). Función PURA — no accede a BD ni a disco; toda la información llega ya
    resuelta por el llamador (ver `calcular_bolsa_horas_empleado` para el orquestador real).

    - `dias_festivos`: iterable de `date` marcados como FESTIVO en la rejilla de Horarios. Día
      excluido POR COMPLETO: no genera expectativa de trabajo ("esperadas") ni puede generar
      saldo en contra de nadie ese día.
    - `dias_baja`: iterable de `date` en baja (rejilla y/o `rrhh_ausencias`). A diferencia del
      festivo, SÍ genera expectativa de trabajo (`horas_diarias`) — el día entero cuenta como
      déficit a compensar por el empleado, exactamente como un día ordinario trabajado de 0h (la
      compensación ECONÓMICA de la baja en sí la resuelve la Fase F/IT aparte; esto es solo saldo
      de horas). Un festivo que coincidiera también con una baja se trata como festivo (regla más
      fuerte: nunca genera expectativa de trabajo).
    - `fichajes_por_dia`: dict `{date: horas_trabajadas_ese_dia}` (float). Se suma siempre a
      "horas trabajadas" (independientemente del tipo de día — así se refleja fielmente cualquier
      fichaje real, aunque lo esperable es que solo existan en días ordinarios); solo se usa para
      calcular déficit/exceso en días ORDINARIOS (ni festivo ni baja).

    Devuelve un dict con `horas_esperadas`, `horas_trabajadas`, `horas_compensar_empleado`,
    `horas_compensar_empresa`, `dias_festivos`, `dias_baja`, `dias_ordinarios` y un `detalle`
    (lista día a día, para depuración/trazabilidad)."""
    if fecha_inicio > fecha_fin:
        raise ValueError("fecha_inicio no puede ser posterior a fecha_fin.")
    horas_diarias = float(horas_diarias or 0)
    festivos = set(dias_festivos or [])
    bajas = set(dias_baja or [])
    fichajes = dict(fichajes_por_dia or {})

    horas_esperadas = 0.0
    horas_trabajadas = 0.0
    horas_compensar_empleado = 0.0
    horas_compensar_empresa = 0.0
    n_festivos = n_bajas = n_ordinarios = 0
    detalle = []

    dia = fecha_inicio
    un_dia = _dt.timedelta(days=1)
    while dia <= fecha_fin:
        trabajadas_dia = float(fichajes.get(dia, 0.0) or 0.0)
        horas_trabajadas += trabajadas_dia

        if dia in festivos:
            n_festivos += 1
            detalle.append({"fecha": dia, "tipo": "festivo", "esperadas": 0.0,
                             "trabajadas": trabajadas_dia, "deficit": 0.0, "exceso": 0.0})
        elif dia in bajas:
            n_bajas += 1
            horas_esperadas += horas_diarias
            horas_compensar_empleado += horas_diarias
            detalle.append({"fecha": dia, "tipo": "baja", "esperadas": horas_diarias,
                             "trabajadas": trabajadas_dia, "deficit": horas_diarias, "exceso": 0.0})
        else:
            n_ordinarios += 1
            horas_esperadas += horas_diarias
            deficit = max(0.0, horas_diarias - trabajadas_dia)
            exceso = max(0.0, trabajadas_dia - horas_diarias)
            horas_compensar_empleado += deficit
            horas_compensar_empresa += exceso
            detalle.append({"fecha": dia, "tipo": "ordinario", "esperadas": horas_diarias,
                             "trabajadas": trabajadas_dia, "deficit": deficit, "exceso": exceso})
        dia += un_dia

    return {
        "id_empleado": id_empleado,
        "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin,
        "horas_diarias": horas_diarias,
        "horas_esperadas": round(horas_esperadas, 2),
        "horas_trabajadas": round(horas_trabajadas, 2),
        "horas_compensar_empleado": round(horas_compensar_empleado, 2),
        "horas_compensar_empresa": round(horas_compensar_empresa, 2),
        "dias_festivos": n_festivos, "dias_baja": n_bajas, "dias_ordinarios": n_ordinarios,
        "detalle": detalle,
    }


# ── Orquestador impuro (reúne datos reales y delega en la función pura) ──────

def _fecha(v) -> "_dt.date | None":
    if v is None:
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except Exception:
        return None


_RE_FECHA = _re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _lunes_de_titulo_semana(titulo: str) -> "_dt.date | None":
    """Best-effort: extrae la fecha de INICIO (lunes) de un título de semana con el formato del
    placeholder ("Semana DD/MM/AAAA – DD/MM/AAAA"). El título es texto LIBRE editado por el
    usuario — si no encaja ningún patrón `DD/MM/AAAA`, devuelve `None` (esa semana no se puede
    cruzar con fechas reales; limitación conocida y documentada, no hay otra fuente de festivos)."""
    m = _RE_FECHA.search(titulo or "")
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        return _dt.date(y, mo, d)
    except ValueError:
        return None


def _festivos_y_bajas_desde_horarios(id_empleado, fecha_inicio, fecha_fin, id_empresa=None):
    """Días FESTIVO / BAJA MÉDICA marcados en la rejilla de Horarios (`documentos/horarios.json`,
    vía `rrhh.horarios_vinculo_empleado`) para `id_empleado`, dentro de `[fecha_inicio,
    fecha_fin]`. Complementa (no sustituye) las bajas reales de `rrhh_ausencias`, ver
    `_bajas_desde_ausencias` — unión de ambas fuentes en `calcular_bolsa_horas_empleado`."""
    festivos, bajas = set(), set()
    try:
        from src.rrhh.horarios_vinculo_empleado import cargar_horarios_json_normalizado
        semanas = cargar_horarios_json_normalizado(id_empresa=id_empresa)
    except Exception as e:
        logger.debug("_festivos_y_bajas_desde_horarios: %s", e)
        return festivos, bajas

    for semana in semanas:
        grid = semana.get("grid") or {}
        ids = grid.get("ids") or []
        absences = grid.get("absences") or {}
        if id_empleado not in ids:
            continue
        lunes = _lunes_de_titulo_semana(semana.get("title", ""))
        if lunes is None:
            continue
        filas_del_empleado = {i for i, v in enumerate(ids) if v == id_empleado}
        for k, info in absences.items():
            try:
                e_idx_str, dia_idx_str = k.split(",")
                e_idx, dia_idx = int(e_idx_str), int(dia_idx_str)
            except Exception:
                continue
            if e_idx not in filas_del_empleado or not (0 <= dia_idx <= 6):
                continue
            fecha = lunes + _dt.timedelta(days=dia_idx)
            if not (fecha_inicio <= fecha <= fecha_fin):
                continue
            texto = str((info or {}).get("text", "")).upper()
            if texto == "FESTIVO":
                festivos.add(fecha)
            elif texto.startswith("BAJA"):
                bajas.add(fecha)
    return festivos, bajas


def _bajas_desde_ausencias(id_empleado, fecha_inicio, fecha_fin, id_empresa=None) -> set:
    """Días de baja médica REALES (`rrhh_ausencias.tipo == TIPO_BAJA_MEDICA`, Fase C) que caen
    dentro de `[fecha_inicio, fecha_fin]` — fuente fiable (fechas estructuradas en BD), a
    diferencia del best-effort de `_festivos_y_bajas_desde_horarios`."""
    dias = set()
    try:
        from src.rrhh.ausencias_servicio import TIPO_BAJA_MEDICA
        from src.rrhh.ausencias_servicio import listar as _listar_ausencias
        filas = _listar_ausencias(id_empleado, id_empresa=id_empresa, tipo=TIPO_BAJA_MEDICA)
    except Exception as e:
        logger.debug("_bajas_desde_ausencias: %s", e)
        return dias
    for f in filas or []:
        fi, ff = _fecha(f.get("fecha_inicio")), _fecha(f.get("fecha_fin"))
        if not fi or not ff:
            continue
        d = max(fi, fecha_inicio)
        limite = min(ff, fecha_fin)
        while d <= limite:
            dias.add(d)
            d += _dt.timedelta(days=1)
    return dias


def _fichajes_por_dia(id_empleado, fecha_inicio, fecha_fin, id_empresa=None) -> dict:
    """`{date: horas_trabajadas}` reales del empleado en `[fecha_inicio, fecha_fin]`, reutilizando
    `db.usuario.listar_fichajes_empleado` (que filtra por `usuario_id` + año/mes) — se recorre un
    mes a la vez. `rrhh_empleados.id_usuario` es el vínculo empleado→cuenta de login."""
    horas_por_dia: dict = {}
    try:
        from src.rrhh.db.empleados import obtener_empleado
        emp = obtener_empleado(id_empleado, id_empresa=id_empresa)
    except Exception as e:
        logger.debug("_fichajes_por_dia: obtener_empleado: %s", e)
        return horas_por_dia
    id_usuario = (emp or {}).get("id_usuario")
    if not id_usuario:
        return horas_por_dia
    try:
        from src.db.usuario import listar_fichajes_empleado
    except Exception as e:
        logger.debug("_fichajes_por_dia: import listar_fichajes_empleado: %s", e)
        return horas_por_dia

    anio, mes = fecha_inicio.year, fecha_inicio.month
    while (anio, mes) <= (fecha_fin.year, fecha_fin.month):
        try:
            fichajes = listar_fichajes_empleado(id_usuario, anio=anio, mes=mes) or []
        except Exception as e:
            logger.debug("_fichajes_por_dia: listar_fichajes_empleado(%s,%s,%s): %s",
                         id_usuario, anio, mes, e)
            fichajes = []
        for fj in fichajes:
            entrada = fj.get("entrada")
            fecha = _fecha(entrada)
            if fecha is None or not (fecha_inicio <= fecha <= fecha_fin):
                continue
            seg = int(fj.get("segundos") or 0)
            horas_por_dia[fecha] = horas_por_dia.get(fecha, 0.0) + seg / 3600.0
        mes += 1
        if mes > 12:
            mes = 1
            anio += 1
    return horas_por_dia


def calcular_bolsa_horas_empleado(id_empleado, id_empresa=None, bolsa=None) -> dict:
    """Orquestador IMPURO: reúne festivos/bajas (rejilla de Horarios + `rrhh_ausencias`) y
    fichajes reales de `id_empleado` sobre la vigencia de su bolsa de horas, y delega el cálculo
    en `calcular_bolsa_horas` (función pura). `bolsa` permite pasar una fila de
    `rrhh_bolsa_horas` ya cargada (evita una segunda consulta); si no se pasa, se obtiene aquí.

    Lanza `ValueError` si el empleado no tiene bolsa de horas activa, o si la tiene pero
    `horas_diarias` sigue `NULL` — la GUI (`rrhh/gui/bolsa_horas_dialog.py`) comprueba
    `obtener_bolsa_horas` ANTES de llamar aquí y muestra el estado vacío correspondiente en
    cualquiera de esos dos casos, así que en el flujo normal esta función solo se invoca cuando
    ya se sabe que hay datos."""
    bolsa = bolsa or obtener_bolsa_horas(id_empleado, id_empresa=id_empresa)
    if not bolsa:
        raise ValueError("El empleado no tiene bolsa de horas activa.")
    if bolsa.get("horas_diarias") is None:
        raise ValueError("Aún no se han definido las horas diarias de trabajo.")

    fi = _fecha(bolsa.get("fecha_inicio_vigencia"))
    ff = _fecha(bolsa.get("fecha_fin_vigencia"))
    if fi is None or ff is None:
        raise ValueError("La bolsa de horas no tiene vigencia definida.")
    # No se calcula más allá de hoy (fichajes futuros no existen).
    hoy = _dt.date.today()
    ff_calculo = min(ff, hoy)
    if ff_calculo < fi:
        ff_calculo = fi

    festivos_grid, bajas_grid = _festivos_y_bajas_desde_horarios(
        id_empleado, fi, ff_calculo, id_empresa=id_empresa)
    bajas_reales = _bajas_desde_ausencias(id_empleado, fi, ff_calculo, id_empresa=id_empresa)
    dias_baja = bajas_grid | bajas_reales
    fichajes = _fichajes_por_dia(id_empleado, fi, ff_calculo, id_empresa=id_empresa)

    resultado = calcular_bolsa_horas(
        id_empleado, fi, ff_calculo, float(bolsa["horas_diarias"]),
        festivos_grid, dias_baja, fichajes)
    resultado["bolsa_horas_id"] = bolsa.get("id")
    resultado["fecha_inicio_vigencia"] = fi
    resultado["fecha_fin_vigencia"] = ff
    resultado["fecha_regularizacion_limite"] = bolsa.get("fecha_regularizacion_limite")
    return resultado
