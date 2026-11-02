"""
Capa de datos de TRÁFICO EXTERIOR / CAPTURE RATE (sensores de conteo de personas — petición
explícita). Auditoría previa: no existía ninguna infraestructura de ingesta de sensores en el repo
(ni tabla, ni concepto de "tráfico"/"passerby"/"aforo"), así que esta es la ÚNICA pieza de motor
nueva de la funcionalidad — el resto (autenticación M2M del webhook, aislamiento por tenant, patrón
de capa de datos) reutiliza tal cual lo que ya existía (`api/security.py::requiere_auth`,
`db/ventas_analitica.py::_tenant_filtro`).

Capture Rate (%) = (entradas / tráfico exterior) * 100 — se calcula SIEMPRE sobre la SUMA agregada
de un período (nunca promediando un % por bucket), para no distorsionar el resultado con buckets de
tráfico muy bajo.

Zona horaria: el `timestamp` que manda cada sensor puede venir en UTC (con o sin sufijo) o naive —
se normaliza a UTC si no trae info de zona, y se convierte a la hora LOCAL de la tienda
(`tiendas.zona_horaria`, migración 0319) antes de agregarlo en un bucket — el resto del esquema
(incluida `ventas.fecha`) ya asume DATETIME naive en hora local, así que este motor mantiene esa
misma convención en vez de introducir UTC en un rincón aislado de la app.
"""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.db.conexion import obtener_conexion

logger = logging.getLogger("trafico_sensores")

BUCKET_MINUTOS_POR_DEFECTO = 15


def _tenant_filtro(alias=None, id_empresa=None, id_tienda=None):
    """Mismo patrón que `db.ventas_analitica._tenant_filtro` (ningún mecanismo de aislamiento
    paralelo): si se pasa `id_empresa` explícito (REST/sensor, sin sesión de escritorio) se usa tal
    cual; si no, cae en la empresa/tienda ACTIVAS de sesión."""
    p = f"{alias}." if alias else ""
    if id_empresa is not None:
        frag = f" AND {p}id_empresa=%s"
        params = [id_empresa]
        if id_tienda is not None:
            frag += f" AND {p}id_tienda=%s"
            params.append(id_tienda)
        return frag, params
    from src.db.empresa import empresa_actual_id, tienda_actual_id_int
    frag = f" AND {p}id_empresa=%s"
    params = [empresa_actual_id()]
    tid = tienda_actual_id_int()
    if tid is not None:
        frag += f" AND {p}id_tienda=%s"
        params.append(tid)
    return frag, params


def _zona_horaria_tienda(id_tienda) -> str:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT zona_horaria FROM tiendas WHERE id=%s", (id_tienda,))
            r = cur.fetchone()
            zona = (r["zona_horaria"] if isinstance(r, dict) else r[0]) if r else None
            return zona or "Europe/Madrid"
    except Exception as e:
        logger.warning("_zona_horaria_tienda(%s): %s", id_tienda, e)
        return "Europe/Madrid"


def _parsear_instante_local(timestamp, zona: str) -> "datetime | None":
    """Acepta ISO 8601 (con o sin sufijo de zona/'Z') o un `datetime` ya construido. Si no trae
    información de zona, se asume UTC (criterio honesto para hardware de sensor: nunca se asume
    "ya está en hora local de la tienda" sin que el payload lo diga explícitamente). Devuelve un
    `datetime` NAIVE ya convertido a la hora local de `zona`."""
    if isinstance(timestamp, datetime):
        dt = timestamp
    else:
        try:
            texto = str(timestamp).strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(texto)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        dt_local = dt.astimezone(ZoneInfo(zona))
    except Exception as e:
        logger.warning("_parsear_instante_local: zona inválida %r (%s); se usa UTC tal cual", zona, e)
        dt_local = dt.astimezone(timezone.utc)
    return dt_local.replace(tzinfo=None)


def _inicio_bucket(dt_local: datetime, bucket_minutos: int) -> datetime:
    minuto_bucket = (dt_local.minute // bucket_minutos) * bucket_minutos
    return dt_local.replace(minute=minuto_bucket, second=0, microsecond=0)


def registrar_lectura(id_empresa, id_tienda, timestamp, passerby_count: int, entry_count: int, *,
                      bucket_minutos: int = BUCKET_MINUTOS_POR_DEFECTO, fuente: str | None = None) -> dict:
    """Registra (o actualiza, si el sensor reenvía el mismo bucket — p. ej. un reintento tras un
    fallo de red) una lectura agregada de tráfico. Nunca SUMA sobre un reenvío del mismo bucket:
    SOBRESCRIBE con el último valor recibido, para no duplicar el conteo si el sensor reintenta."""
    passerby_count = max(0, int(passerby_count or 0))
    entry_count = max(0, int(entry_count or 0))
    zona = _zona_horaria_tienda(id_tienda)
    dt_local = _parsear_instante_local(timestamp, zona)
    if dt_local is None:
        return {"ok": False, "error": "timestamp_invalido"}
    bucket_inicio = _inicio_bucket(dt_local, bucket_minutos)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO trafico_sensores_buckets "
                "(id_empresa, id_tienda, bucket_inicio, bucket_minutos, passerby_count, "
                "entry_count, fuente) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE passerby_count=VALUES(passerby_count), "
                "entry_count=VALUES(entry_count), fuente=VALUES(fuente)",
                (id_empresa, id_tienda, bucket_inicio, bucket_minutos, passerby_count,
                 entry_count, fuente))
            conn.commit()
        return {"ok": True, "bucket_inicio": bucket_inicio.isoformat(), "bucket_minutos": bucket_minutos}
    except Exception as e:
        logger.error("registrar_lectura(%s,%s): %s", id_empresa, id_tienda, e)
        return {"ok": False, "error": "error_interno"}


def resumen_periodo(desde, hasta, *, id_empresa=None, id_tienda=None) -> dict:
    """{'passerby': int, 'entries': int, 'capture_rate': float|None} agregado (SUMA, no promedio de
    porcentajes) para el rango `desde`..`hasta` (fechas, inclusive) — mismo filtro de tenant/tienda
    que el resto de la analítica de Ventas. `capture_rate` es `None` (no 0) si no hubo tráfico
    exterior registrado, para que la UI pueda distinguir "sin datos de sensor" de "0% de captación
    real"."""
    tf, tp = _tenant_filtro(None, id_empresa, id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(passerby_count),0), COALESCE(SUM(entry_count),0) "
                "FROM trafico_sensores_buckets WHERE DATE(bucket_inicio) BETWEEN %s AND %s" + tf,
                (desde, hasta, *tp))
            fila = cur.fetchone() or (0, 0)
            passerby = int(fila[0] or 0)
            entries = int(fila[1] or 0)
            capture_rate = round(entries / passerby * 100, 1) if passerby > 0 else None
            return {"passerby": passerby, "entries": entries, "capture_rate": capture_rate}
    except Exception as e:
        logger.error("resumen_periodo: %s", e)
        return {"passerby": 0, "entries": 0, "capture_rate": None}


def serie_por_dia(desde, hasta, *, id_empresa=None, id_tienda=None) -> list:
    """[(dia, passerby, entries)] por día en el rango — análogo a
    `ventas_analitica.serie_por_dia`, para poder superponer tráfico y facturación en la misma
    gráfica si en el futuro hiciera falta."""
    tf, tp = _tenant_filtro(None, id_empresa, id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DATE(bucket_inicio) AS dia, COALESCE(SUM(passerby_count),0), "
                "COALESCE(SUM(entry_count),0) FROM trafico_sensores_buckets "
                "WHERE DATE(bucket_inicio) BETWEEN %s AND %s" + tf + " GROUP BY dia ORDER BY dia",
                (desde, hasta, *tp))
            return list(cur.fetchall())
    except Exception as e:
        logger.error("serie_por_dia: %s", e)
        return []
