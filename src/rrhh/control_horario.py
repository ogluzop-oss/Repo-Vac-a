"""
Control horario laboral (RD 8/2019) — F4.9.

Capa de servicio sobre `rrhh_jornadas`/`rrhh_pausas` (registro diario por empleado),
integrada con el expediente y multiempresa/multitienda. Reutiliza la infraestructura
existente (empleados, fichajes como puente). Calcula tiempo efectivo, exceso/déficit,
detecta incidencias y produce informes/exportaciones. No toca motor de nómina ni
contabilidad. Sin Qt.
"""

import csv
import datetime as _dt
import io
import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion, transaccion)
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("rrhh.control_horario")

TIPOS_PAUSA = {"comida": "Comida", "descanso": "Descanso", "medico": "Médico", "otros": "Otros"}
JORNADA_DEFECTO_MIN = 480   # 8 h


class ControlHorarioError(Exception):
    """Validación de registro horario fallida."""


def _dt_parse(v):
    if v in (None, ""):
        return None
    if isinstance(v, _dt.datetime):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return _dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ControlHorarioError(f"Fecha/hora no válida: {v!r}")


def _fecha(v):
    d = _dt_parse(v) if (isinstance(v, str) and ":" in str(v)) else None
    if d:
        return d.date()
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ControlHorarioError(f"Fecha no válida: {v!r}")


def _seg(ini, fin):
    if not ini or not fin:
        return 0
    s = int((fin - ini).total_seconds())
    if s < 0:
        raise ControlHorarioError("La hora de fin no puede ser anterior a la de inicio.")
    return s


# ── Registro de jornada ─────────────────────────────────────────────────────
def registrar_jornada(id_empleado, fecha, hora_entrada, hora_salida=None, pausas=None,
                      planificada_min=JORNADA_DEFECTO_MIN, observaciones="", usuario=None,
                      id_empresa=None, id_tienda="", origen="manual") -> int:
    """Registra (o reemplaza no permitido: una jornada por empleado+fecha) el registro
    diario. Calcula pausas, tiempo efectivo, exceso y déficit. Devuelve id_jornada."""
    id_empresa = id_empresa or empresa_actual_id()
    fch = _fecha(fecha)
    ent = _dt_parse(hora_entrada)
    sal = _dt_parse(hora_salida)
    if not ent:
        raise ControlHorarioError("La hora de entrada es obligatoria.")
    if sal and sal < ent:
        raise ControlHorarioError("La salida no puede ser anterior a la entrada.")
    pausas = pausas or []
    pausas_norm = []
    pausa_seg = 0
    for p in pausas:
        tipo = (p.get("tipo") or "descanso")
        if tipo not in TIPOS_PAUSA:
            raise ControlHorarioError(f"Tipo de pausa no válido: {tipo!r}.")
        pi, pf = _dt_parse(p.get("inicio")), _dt_parse(p.get("fin"))
        seg = _seg(pi, pf)
        pausa_seg += seg
        pausas_norm.append((tipo, pi, pf, seg))
    efectivo_min = 0
    if sal:
        bruto = int((sal - ent).total_seconds())
        efectivo_min = max(int((bruto - pausa_seg) / 60), 0)
    exceso = max(efectivo_min - int(planificada_min or 0), 0) if sal else 0
    deficit = max(int(planificada_min or 0) - efectivo_min, 0) if sal else 0

    if _existe_jornada(id_empleado, id_empresa, fch):
        raise ControlHorarioError(f"Ya existe una jornada registrada para {fch}.")
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rrhh_jornadas (id_empresa, id_tienda, id_empleado, fecha, "
                "hora_entrada, hora_salida, pausa_segundos, tiempo_efectivo_min, "
                "planificada_min, exceso_min, deficit_min, observaciones, usuario_registro, "
                "origen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_tienda or "", id_empleado, fch.isoformat(),
                 ent, sal, pausa_seg, efectivo_min, int(planificada_min or 0), exceso, deficit,
                 observaciones, usuario, origen))
            jid = cur.lastrowid
            for tipo, pi, pf, seg in pausas_norm:
                cur.execute(
                    "INSERT INTO rrhh_pausas (id_empresa, id_jornada, tipo, inicio, fin, segundos) "
                    "VALUES (%s,%s,%s,%s,%s,%s)", (id_empresa, jid, tipo, pi, pf, seg))
        return jid
    except ControlHorarioError:
        raise
    except Exception as e:
        logger.error("registrar_jornada(emp=%s): %s", id_empleado, e)
        raise ControlHorarioError("No se pudo registrar la jornada.") from e


def _existe_jornada(id_empleado, id_empresa, fch) -> bool:
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM rrhh_jornadas WHERE id_empresa=%s AND id_empleado=%s AND fecha=%s",
                    (id_empresa, id_empleado, fch.isoformat() if hasattr(fch, "isoformat") else fch))
        return cur.fetchone() is not None


def obtener_jornada(id_jornada, id_empresa=None) -> dict | None:
    id_empresa = id_empresa or empresa_actual_id()
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM rrhh_jornadas WHERE id=%s AND id_empresa=%s",
                    (id_jornada, id_empresa))
        j = _fila_a_dict(cur, cur.fetchone())
        if j:
            cur.execute("SELECT * FROM rrhh_pausas WHERE id_jornada=%s ORDER BY inicio", (id_jornada,))
            j["pausas"] = _filas_a_dicts(cur, cur.fetchall())
        return j


def listar_jornadas(id_empleado, id_empresa=None, desde=None, hasta=None, id_tienda=None) -> list:
    id_empresa = id_empresa or empresa_actual_id()
    filtros, params = ["id_empresa=%s", "id_empleado=%s"], [id_empresa, id_empleado]
    if desde:
        filtros.append("fecha>=%s"); params.append(_fecha(desde).isoformat())
    if hasta:
        filtros.append("fecha<=%s"); params.append(_fecha(hasta).isoformat())
    if id_tienda is not None:
        filtros.append("id_tienda=%s"); params.append(id_tienda)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_jornadas WHERE " + " AND ".join(filtros)
                        + " ORDER BY fecha DESC", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_jornadas: %s", e)
        return []


def eliminar_jornada(id_jornada, id_empresa=None) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM rrhh_jornadas WHERE id=%s AND id_empresa=%s",
                        (id_jornada, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("eliminar_jornada(%s): %s", id_jornada, e)
        return False


# ── Alertas / incidencias ────────────────────────────────────────────────────
def alertas(id_empleado, id_empresa=None, desde=None, hasta=None) -> list:
    """Detecta incidencias del registro horario del empleado."""
    jornadas = listar_jornadas(id_empleado, id_empresa, desde, hasta)
    inc = []
    vistas = {}
    for j in jornadas:
        f = str(j.get("fecha"))
        if not j.get("hora_salida"):
            inc.append({"fecha": f, "tipo": "jornada_incompleta", "detalle": "Sin hora de salida."})
        elif j.get("hora_entrada") and j["hora_salida"] < j["hora_entrada"]:
            inc.append({"fecha": f, "tipo": "inconsistente", "detalle": "Salida anterior a entrada."})
        if int(j.get("exceso_min") or 0) > 0:
            inc.append({"fecha": f, "tipo": "exceso_jornada", "detalle": f"{j['exceso_min']} min de exceso."})
        if int(j.get("deficit_min") or 0) > 0:
            inc.append({"fecha": f, "tipo": "deficit_jornada", "detalle": f"{j['deficit_min']} min de déficit."})
        vistas[f] = vistas.get(f, 0) + 1
    for f, n in vistas.items():
        if n > 1:
            inc.append({"fecha": f, "tipo": "fichaje_duplicado", "detalle": f"{n} jornadas en {f}."})
    return inc


# ── Informes (diario / semanal / mensual / anual) ────────────────────────────
def _totales(jornadas) -> dict:
    return {
        "dias": len(jornadas),
        "efectivo_min": sum(int(j.get("tiempo_efectivo_min") or 0) for j in jornadas),
        "planificada_min": sum(int(j.get("planificada_min") or 0) for j in jornadas),
        "exceso_min": sum(int(j.get("exceso_min") or 0) for j in jornadas),
        "deficit_min": sum(int(j.get("deficit_min") or 0) for j in jornadas),
    }


def informe(id_empleado, id_empresa=None, desde=None, hasta=None, id_tienda=None) -> dict:
    """Informe de un periodo arbitrario (sirve para diario/semanal/mensual/anual según el
    rango): jornadas + totales."""
    jornadas = listar_jornadas(id_empleado, id_empresa, desde, hasta, id_tienda)
    return {"desde": str(_fecha(desde)) if desde else None,
            "hasta": str(_fecha(hasta)) if hasta else None,
            "jornadas": jornadas, "totales": _totales(jornadas)}


def informe_diario(id_empleado, fecha, id_empresa=None):
    return informe(id_empleado, id_empresa, desde=fecha, hasta=fecha)


def informe_mensual(id_empleado, anio, mes, id_empresa=None):
    d = _dt.date(int(anio), int(mes), 1)
    h = (d.replace(day=28) + _dt.timedelta(days=4)).replace(day=1) - _dt.timedelta(days=1)
    return informe(id_empleado, id_empresa, desde=d, hasta=h)


def informe_anual(id_empleado, anio, id_empresa=None):
    return informe(id_empleado, id_empresa, desde=_dt.date(int(anio), 1, 1),
                   hasta=_dt.date(int(anio), 12, 31))


# ── Exportaciones (CSV / Excel / PDF) ────────────────────────────────────────
_COLS = [("fecha", "Fecha"), ("hora_entrada", "Entrada"), ("hora_salida", "Salida"),
         ("pausa_segundos", "Pausa (s)"), ("tiempo_efectivo_min", "Efectivo (min)"),
         ("planificada_min", "Planificada (min)"), ("exceso_min", "Exceso (min)"),
         ("deficit_min", "Déficit (min)"), ("observaciones", "Observaciones")]


def exportar_csv(jornadas) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([et for _, et in _COLS])
    for j in jornadas:
        w.writerow([j.get(k, "") for k, _ in _COLS])
    return buf.getvalue()


def exportar_excel(jornadas, ruta) -> str | None:
    try:
        from openpyxl import Workbook
    except Exception as e:
        logger.warning("openpyxl no disponible: %s", e); return None
    wb = Workbook(); ws = wb.active; ws.title = "Control horario"
    ws.append([et for _, et in _COLS])
    for j in jornadas:
        ws.append([str(j.get(k, "")) for k, _ in _COLS])
    wb.save(ruta)
    return ruta


def exportar_pdf(jornadas, ruta, titulo="Registro horario") -> str | None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
    except Exception as e:
        logger.warning("reportlab no disponible: %s", e); return None
    doc = SimpleDocTemplate(ruta, pagesize=A4)
    st = getSampleStyleSheet()
    data = [[et for _, et in _COLS]] + [[str(j.get(k, "")) for k, _ in _COLS] for j in jornadas]
    t = Table(data)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                           ("FONTSIZE", (0, 0), (-1, -1), 7)]))
    doc.build([Paragraph(titulo, st["Title"]), Spacer(1, 12), t])
    return ruta


# ── Puente: importar fichajes existentes ─────────────────────────────────────
def importar_de_fichajes(id_empleado, usuario_id, id_empresa=None, id_tienda="",
                         planificada_min=JORNADA_DEFECTO_MIN) -> int:
    """Crea jornadas a partir de los fichajes (tabla `fichajes`) de un usuario. Reutiliza
    la infraestructura existente. Omite fechas ya registradas. Devuelve nº importadas."""
    id_empresa = id_empresa or empresa_actual_id()
    from src.db.usuario import listar_fichajes
    n = 0
    for f in listar_fichajes():
        if f.get("usuario_id") != usuario_id or not f.get("entrada"):
            continue
        ent = _dt_parse(f["entrada"])
        fch = ent.date()
        if _existe_jornada(id_empleado, id_empresa, fch):
            continue
        try:
            registrar_jornada(id_empleado, fch, ent, f.get("salida"),
                              planificada_min=planificada_min, id_empresa=id_empresa,
                              id_tienda=id_tienda, origen="fichaje")
            n += 1
        except ControlHorarioError:
            continue
    return n
