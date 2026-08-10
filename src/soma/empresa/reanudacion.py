"""
REANUDACIÓN de misiones entre sesiones (Fase 8). Si una misión quedó pendiente (esperando aprobación,
proveedor, RRHH, auditoría…), SOMA la RECUPERA — no crea una nueva. Lee la misión persistida (Fase 6,
tablas soma_misiones / soma_mision_tareas) conservando su historial, especialistas y progreso, y la
SURFACEA para continuarla exactamente donde se dejó.

Solo LECTURA: no modifica el Mission Engine ni ejecuta nada. La ejecución de lo crítico sigue pasando
por Workflow/Gobierno/Autonomía. Reutiliza el modelo de la Fase 6 para reconstruir una foto de la
misión (sin tocar el motor).
"""

import logging

logger = logging.getLogger("soma.empresa.reanudacion")

# Estados de misión que se consideran "pendientes de continuar".
_PENDIENTES = ("ESPERANDO_APROBACION", "PAUSADA", "EN_CURSO")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def pendientes(id_empresa=None, usuario=None) -> list:
    """Misiones persistidas que quedaron a medias. [{id, objetivo, estado, prioridad, tareas,
    pendientes, especialistas}] — conserva progreso/historial (solo lectura)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            marcadores = ",".join(["%s"] * len(_PENDIENTES))
            cur.execute(
                f"SELECT id, objetivo, estado, prioridad, especialistas, creada FROM soma_misiones "
                f"WHERE id_empresa<=>%s AND estado IN ({marcadores}) ORDER BY creada DESC LIMIT 10",
                (emp, *_PENDIENTES))
            misiones = _filas_a_dicts(cur, cur.fetchall())
            out = []
            for m in misiones:
                cur.execute("SELECT clave, titulo, estado, progreso, especialista FROM "
                            "soma_mision_tareas WHERE id_mision=%s ORDER BY orden", (m["id"],))
                tareas = _filas_a_dicts(cur, cur.fetchall())
                pend = [t for t in tareas if t.get("estado") not in ("HECHA", "OMITIDA", "FALLIDA")]
                out.append({
                    "id": m["id"], "objetivo": m.get("objetivo"), "estado": m.get("estado"),
                    "prioridad": m.get("prioridad"), "tareas": tareas, "pendientes": pend,
                    "especialistas": _lista(m.get("especialistas")),
                })
            return out
    except Exception as e:
        logger.debug("pendientes: %s", e)
        return []


def _lista(v):
    if not v:
        return []
    try:
        import json
        x = json.loads(v)
        return x if isinstance(x, list) else [str(x)]
    except Exception:
        return [s.strip() for s in str(v).split(",") if s.strip()]


_MOTIVO = {"ESPERANDO_APROBACION": "esperando aprobación", "PAUSADA": "en pausa",
           "EN_CURSO": "en curso"}


def resumen(id_empresa=None, usuario=None) -> str:
    """Frase natural de continuidad sobre las misiones pendientes ('Ayer dejamos preparada…')."""
    ms = pendientes(id_empresa, usuario)
    if not ms:
        return ""
    m = ms[0]
    motivo = _MOTIVO.get(m["estado"], "pendiente")
    txt = f"Ayer dejamos en marcha «{m['objetivo']}», ahora mismo {motivo}."
    if m["pendientes"]:
        t = m["pendientes"][0]
        txt += f" Queda pendiente: {t.get('titulo')}."
    if len(ms) > 1:
        txt += f" Y hay {len(ms) - 1} objetivo(s) más en curso."
    return txt


def hallazgo_continuidad(id_empresa=None, usuario=None):
    """Construye un hallazgo (para kernel.intervenir) que ofrece continuar la misión pendiente. No
    ejecuta: solo propone retomarla. Devuelve None si no hay nada pendiente."""
    ms = pendientes(id_empresa, usuario)
    if not ms:
        return None
    m = ms[0]
    return {
        "clave": f"reanudar_mision_{m['id']}",
        "tipo": "objetivo", "dominio": "mision",
        "titulo": "Retomamos donde lo dejamos",
        "mensaje": resumen(id_empresa, usuario),
        "prioridad": (m.get("prioridad") or "ALTA").upper().replace("NORMAL", "MEDIA"),
        "por_que": "Hay una misión que quedó a la espera en la sesión anterior; conservo su progreso.",
        "consecuencias": "Sin retomarla, el objetivo se quedaría parado.",
        "si_no_hago_nada": "El objetivo seguiría detenido a la espera de resolverse.",
        "especialistas": m.get("especialistas") or [],
        "datos": {"mision": m["objetivo"], "estado": m["estado"],
                  "tareas_pendientes": len(m["pendientes"])},
    }
