"""
Persistencia documental RRHH → expediente (F4.2.1).

Orquesta el registro de un documento RRHH recién generado en el expediente del
trabajador, usando EXCLUSIVAMENTE la capa de datos `src/rrhh/db/` (el wizard no toca
la BD). Es best-effort: se invoca DESPUÉS de generar el PDF y nunca debe afectar a la
generación (si falla, se registra y se continúa).

Identificación del empleado por (id_empresa, nif). Si no existe, NO se crea
implícitamente: se registra incidencia y no se persiste (las tablas exigen empleado).
Guarda `datos_snapshot` (copia íntegra de self._datos) para trazabilidad histórica.
"""

import datetime as _dt
import json
import logging

logger = logging.getLogger("rrhh.persistencia")

# tipo del wizard (self._tipo) → tipo_doc del expediente
_TIPO_DOC = {
    "CONTRATO": "contrato", "NÓMINA": "nomina", "ALTA": "alta", "BAJA": "baja",
    "CERTIFICADO": "certificado", "CERT LABORAL": "cert_laboral",
    "CARTA DESPIDO": "carta_despido", "FINIQUITO": "finiquito", "VACACIONES": "vacaciones",
}
_VAC_TIPO = {"SOLICITUD": "solicitud", "APROBACIÓN": "aprobacion", "DENEGACIÓN": "denegacion"}
_VAC_ESTADO = {"SOLICITUD": "pendiente", "APROBACIÓN": "aprobada", "DENEGACIÓN": "denegada"}


def _fecha_iso(valor):
    """DD/MM/AAAA → YYYY-MM-DD (o None si no parseable)."""
    if not valor:
        return None
    try:
        return _dt.datetime.strptime(str(valor).strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:
        return None


def _num(valor):
    try:
        return round(float(str(valor).replace(".", "").replace(",", ".").strip()), 2) \
            if isinstance(valor, str) and ("," in valor) else round(float(valor or 0), 2)
    except Exception:
        return 0.0


def _dias(f_ini, f_fin):
    try:
        di = _dt.datetime.strptime(str(f_ini).strip(), "%d/%m/%Y")
        df = _dt.datetime.strptime(str(f_fin).strip(), "%d/%m/%Y")
        return float((df - di).days + 1)
    except Exception:
        return 0.0


def registrar_generacion(tipo, datos, ruta, id_empresa=None) -> int | None:
    """Registra el documento generado en el expediente. Devuelve id_empleado o None.
    No lanza: cualquier error se registra y se devuelve None."""
    try:
        if tipo not in _TIPO_DOC:
            return None                                  # tipos fiscales / no laborales
        from src.db.empresa import empresa_actual_id
        from src.rrhh.db import (ausencias, contratos, documentos, empleados,
                                 nominas, vacaciones)
        id_empresa = id_empresa or empresa_actual_id()
        datos = datos or {}
        nif = (datos.get("nif") or "").strip().upper()
        emp = empleados.obtener_por_nif(nif, id_empresa) if nif else None
        if not emp:
            logger.warning("Documento %s sin expediente (NIF=%s): no se persiste "
                           "(no se crean altas implícitas).", tipo, nif or "—")
            return None

        eid = emp["id"]
        snap = json.dumps(datos, ensure_ascii=False, default=str)
        fecha = _fecha_iso(datos.get("fecha"))
        tipo_doc = _TIPO_DOC[tipo]

        # 1) Documento genérico (siempre)
        documentos.crear_documento(eid, id_empresa, tipo_doc=tipo_doc, fecha=fecha,
                                   ref_documento=ruta, datos_snapshot=snap)

        # 2) Especializados según tipo
        if tipo == "CONTRATO":
            contratos.crear_contrato(
                eid, id_empresa, tipo_registro="contrato", modalidad=datos.get("subtipo"),
                fecha_inicio=fecha, fecha_fin=_fecha_iso(datos.get("fecha_fin")),
                salario=_num(datos.get("salario")), jornada=datos.get("tipo_jornada"),
                id_centro=datos.get("id_centro"), ref_documento=ruta, datos_snapshot=snap)
        elif tipo == "NÓMINA":
            _registrar_nomina(nominas, eid, id_empresa, datos, fecha, ruta, snap)
        elif tipo == "VACACIONES":
            sub = (datos.get("subtipo") or "SOLICITUD").upper()
            f_ini = datos.get("fecha")
            f_fin = datos.get("fecha_fin_vac")
            anio = _anio(fecha)
            vacaciones.crear_vacaciones(
                eid, id_empresa, anio=anio, tipo=_VAC_TIPO.get(sub, "solicitud"),
                fecha_inicio=fecha, fecha_fin=_fecha_iso(f_fin), dias=_dias(f_ini, f_fin),
                estado=_VAC_ESTADO.get(sub, "pendiente"),
                aprobado_por=datos.get("responsable"), ref_documento=ruta)
        elif tipo == "BAJA":
            sub = (datos.get("subtipo") or "").strip().lower().replace(" ", "_")[:14]
            ausencias.crear_ausencia(
                eid, id_empresa, tipo=sub or "baja", fecha_inicio=fecha,
                fecha_fin=_fecha_iso(datos.get("fecha_fin")),
                motivo=datos.get("motivo_baja") or datos.get("subtipo"),
                ref_documento=ruta)
        return eid
    except Exception:
        logger.exception("registrar_generacion(%s) falló (no crítico)", tipo)
        return None


def _anio(fecha_iso):
    try:
        return int(str(fecha_iso)[:4]) if fecha_iso else _dt.date.today().year
    except Exception:
        return _dt.date.today().year


def _registrar_nomina(nominas, eid, id_empresa, datos, fecha, ruta, snap):
    """Mapea la nómina a rrhh_nominas con la MISMA aritmética que render_nomina
    (se unificará con el motor de nómina en F4.3)."""
    salario = _num(datos.get("salario"))
    try:
        num_pagas = int(datos.get("num_pagas") or 12)
    except Exception:
        num_pagas = 12
    irpf_pct = _num(datos.get("irpf_pct")) or 15.0
    ss_pct = _num(datos.get("ss_pct")) or 6.35
    plus = _num(datos.get("plus_convenio"))
    he = _num(datos.get("horas_extras"))
    base = round(salario / num_pagas if num_pagas and salario > 0 else salario, 2)
    irpf_imp = round(base * irpf_pct / 100, 2)
    ss_imp = round(base * ss_pct / 100, 2)
    bruto = round(base + plus + he, 2)
    neto = round(bruto - irpf_imp - ss_imp, 2)
    anio, mes = _anio(fecha), _mes(fecha)
    conceptos = json.dumps({"salario_base": base, "plus_convenio": plus,
                            "horas_extras": he}, ensure_ascii=False)
    nominas.crear_nomina(eid, id_empresa, anio=anio, mes=mes, fecha=fecha, bruto=bruto,
                         base=base, irpf_pct=irpf_pct, irpf_importe=irpf_imp, ss_pct=ss_pct,
                         ss_importe=ss_imp, neto=neto, conceptos=conceptos, ref_documento=ruta)


def _mes(fecha_iso):
    try:
        return int(str(fecha_iso)[5:7]) if fecha_iso else _dt.date.today().month
    except Exception:
        return _dt.date.today().month
