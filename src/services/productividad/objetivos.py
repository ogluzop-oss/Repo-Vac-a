"""
Fase Productividad · Objetivos VERSIONADOS por centro (fijo) y por empleado (dinámico/hora).

Nunca se actualiza un objetivo "en sitio": fijar uno nuevo CIERRA la versión anterior
(`vigente_hasta`) e inserta una fila nueva — así una barra de progreso de un periodo ya pasado
sigue mostrando el objetivo que estaba vigente ENTONCES, nunca el que el superadmin puso después.
`valor` significa cosas distintas según `tipo_objetivo`: para "centro" es el importe FIJO del
periodo; para "empleado" es la TARIFA POR HORA — el objetivo real se calcula multiplicando por las
horas trabajadas (ver `objetivo_dinamico_empleado`, que lee de Fichajes vía
`src.db.usuario.horas_trabajadas_rango`).
"""

import datetime

from src.db.conexion import obtener_conexion
from src.services.productividad import periodos as P

TIPOS_OBJETIVO = ("centro", "empleado")


def _hoy() -> datetime.date:
    return datetime.date.today()


def _fijar(tipo_objetivo, periodo, valor, id_empresa, *, centro_codigo=None, usuario_id=None,
           creado_por_id=None, vigente_desde=None) -> int | None:
    if tipo_objetivo not in TIPOS_OBJETIVO:
        raise ValueError(f"tipo_objetivo inválido: {tipo_objetivo!r}")
    if periodo not in P.TIPOS:
        raise ValueError(f"periodo inválido: {periodo!r}")
    desde = vigente_desde or _hoy()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cond = "id_empresa=%s AND tipo_objetivo=%s AND periodo=%s AND vigente_hasta IS NULL"
            params = [id_empresa, tipo_objetivo, periodo]
            if tipo_objetivo == "centro":
                cond += " AND centro_codigo=%s"
                params.append(centro_codigo)
            else:
                cond += " AND usuario_id=%s"
                params.append(usuario_id)
            cur.execute(
                f"UPDATE productividad_objetivos SET vigente_hasta=%s "
                f"WHERE {cond}",
                tuple([desde - datetime.timedelta(days=1)] + params))
            cur.execute(
                "INSERT INTO productividad_objetivos "
                "(id_empresa, tipo_objetivo, centro_codigo, usuario_id, periodo, valor, "
                " vigente_desde, creado_por_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, tipo_objetivo, centro_codigo, usuario_id, periodo,
                 round(float(valor or 0), 2), desde, creado_por_id))
            conn.commit()
            return cur.lastrowid
    except Exception:
        return None


def fijar_objetivo_centro(centro_codigo, periodo, valor_fijo, id_empresa, creado_por_id=None,
                           vigente_desde=None) -> int | None:
    return _fijar("centro", periodo, valor_fijo, id_empresa, centro_codigo=centro_codigo,
                   creado_por_id=creado_por_id, vigente_desde=vigente_desde)


def fijar_objetivo_empleado(usuario_id, periodo, valor_hora, id_empresa, creado_por_id=None,
                             vigente_desde=None) -> int | None:
    return _fijar("empleado", periodo, valor_hora, id_empresa, usuario_id=usuario_id,
                   creado_por_id=creado_por_id, vigente_desde=vigente_desde)


def objetivo_en_fecha(tipo_objetivo, periodo, id_empresa, fecha_referencia=None, *,
                       centro_codigo=None, usuario_id=None) -> dict | None:
    """Versión del objetivo vigente EN `fecha_referencia` (hoy si se omite) — la que corresponde
    mostrar en una barra de progreso de un periodo que contenga esa fecha, pasado o presente."""
    fecha_referencia = fecha_referencia or _hoy()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cond = ("id_empresa=%s AND tipo_objetivo=%s AND periodo=%s AND vigente_desde<=%s "
                    "AND (vigente_hasta IS NULL OR vigente_hasta>=%s)")
            params = [id_empresa, tipo_objetivo, periodo, fecha_referencia, fecha_referencia]
            if tipo_objetivo == "centro":
                cond += " AND centro_codigo=%s"
                params.append(centro_codigo)
            else:
                cond += " AND usuario_id=%s"
                params.append(usuario_id)
            cur.execute(
                "SELECT id, valor, vigente_desde, vigente_hasta, creado_por_id FROM "
                f"productividad_objetivos WHERE {cond} ORDER BY vigente_desde DESC LIMIT 1",
                tuple(params))
            r = cur.fetchone()
            if not r:
                return None
            if isinstance(r, dict):
                return {"id": r["id"], "valor": float(r["valor"]), "vigente_desde": r["vigente_desde"],
                        "vigente_hasta": r["vigente_hasta"], "creado_por_id": r["creado_por_id"]}
            return {"id": r[0], "valor": float(r[1]), "vigente_desde": r[2], "vigente_hasta": r[3],
                    "creado_por_id": r[4]}
    except Exception:
        return None


def objetivos_obligatorios_completos(tipo_objetivo, id_empresa, fecha_referencia=None, *,
                                      centro_codigo=None, usuario_id=None) -> dict:
    """{periodo: bool} para los 3 periodos OBLIGATORIOS (mensual/semestral/anual) — indica si cada
    uno ya tiene un objetivo vigente definido en `fecha_referencia`."""
    return {
        periodo: objetivo_en_fecha(tipo_objetivo, periodo, id_empresa, fecha_referencia,
                                    centro_codigo=centro_codigo, usuario_id=usuario_id) is not None
        for periodo in P.OBLIGATORIOS
    }


def objetivo_dinamico_empleado(usuario_id, periodo, id_empresa, fecha_referencia=None) -> dict:
    """Objetivo REAL vivo de un empleado para el periodo que contiene `fecha_referencia`: tarifa/
    hora vigente × horas trabajadas en ese rango (obtenidas de Fichajes, sesión abierta incluida).
    Se recalcula completo cada vez que se llama — nunca se guarda un valor "objetivo" fijo para un
    empleado, siempre se deriva (pedido explícito: el objetivo de empleado es DINÁMICO)."""
    fecha_referencia = fecha_referencia or _hoy()
    desde, hasta = P.limites_periodo(periodo, fecha_referencia)
    obj = objetivo_en_fecha("empleado", periodo, id_empresa, fecha_referencia, usuario_id=usuario_id)
    valor_hora = obj["valor"] if obj else 0.0
    from src.db.usuario import horas_trabajadas_rango
    horas = horas_trabajadas_rango(usuario_id, desde, hasta, id_empresa=id_empresa)
    return {
        "periodo": periodo, "desde": desde, "hasta": hasta, "valor_hora": valor_hora,
        "horas_trabajadas": horas, "objetivo_calculado": round(valor_hora * horas, 2),
    }
