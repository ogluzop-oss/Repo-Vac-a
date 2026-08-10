"""
Aprendizaje LENTO de hábitos empresariales (Fase 8). Deriva de datos REALES cómo trabaja la empresa,
sin configuración manual, y lo guarda en la memoria empresarial ([[conocimiento]]). Best-effort: cada
señal es opcional; si una fuente falta, se omite sin romper. Es el objetivo de un job del Scheduler
(reutilizado) y también se ejecuta una vez al iniciar sesión, en segundo plano.

Reutiliza lo que YA existe (no recalcula ni crea motores): memoria_persistente (Fase 5), la tabla de
recomendaciones (Fase 7), las misiones (Fase 6) y consultas ligeras de actividad.
"""

import logging

from src.soma.empresa import conocimiento as C

logger = logging.getLogger("soma.empresa.habitos")

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def observar(id_empresa=None, usuario=None) -> int:
    """Observa y consolida hábitos empresariales. Devuelve el nº de señales aprendidas."""
    emp = _emp(id_empresa)
    n = 0
    n += _habitos_de_uso(emp, usuario)
    n += _iniciativas_aceptadas(emp)
    n += _objetivos_completados(emp)
    n += _patron_actividad(emp)
    return n


def _habitos_de_uso(emp, usuario) -> int:
    """Módulos/informes/exportaciones que la empresa usa habitualmente (desde la memoria por usuario)."""
    n = 0
    if not usuario:
        return 0
    try:
        from src.soma import memoria_persistente as MP
        perfil = MP.perfil(usuario, id_empresa=emp)
        for vid in (perfil.get("modulos_frecuentes") or [])[:5]:
            C.recordar(C.HABITO, f"usa_modulo:{vid}",
                       f"La empresa trabaja habitualmente con el módulo «{vid}».", id_empresa=emp)
            n += 1
        prefs = perfil.get("preferencias") or {}
        if prefs.get("formato_export"):
            C.recordar(C.PREFERENCIA, "formato_export",
                       f"Suelen exportar los informes en {prefs['formato_export']}.", id_empresa=emp)
            n += 1
    except Exception as e:
        logger.debug("habitos_uso: %s", e)
    return n


def _iniciativas_aceptadas(emp) -> int:
    """Iniciativas que la empresa ACEPTA con frecuencia (de la tabla de recomendaciones, Fase 7)."""
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT titulo, COUNT(*) n FROM soma_recomendaciones WHERE id_empresa<=>%s "
                        "AND estado='ACEPTADA' GROUP BY titulo ORDER BY n DESC LIMIT 5", (emp,))
            filas = _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("iniciativas: %s", e)
        return 0
    n = 0
    for f in filas:
        if f.get("titulo"):
            C.recordar(C.INICIATIVA, f"acepta:{f['titulo'][:80]}",
                       f"Suelen aceptar la iniciativa «{f['titulo']}».", id_empresa=emp)
            n += 1
    return n


def _objetivos_completados(emp) -> int:
    """Objetivos/misiones que la empresa completa (de soma_misiones, Fase 6)."""
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT objetivo, COUNT(*) n FROM soma_misiones WHERE id_empresa<=>%s "
                        "AND estado='COMPLETADA' GROUP BY objetivo ORDER BY n DESC LIMIT 5", (emp,))
            filas = _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("objetivos: %s", e)
        return 0
    n = 0
    for f in filas:
        if f.get("objetivo"):
            C.recordar(C.OBJETIVO, f"completa:{f['objetivo'][:80]}",
                       f"Han completado antes el objetivo «{f['objetivo']}».", id_empresa=emp)
            n += 1
    return n


def _patron_actividad(emp) -> int:
    """Día de la semana con más actividad de ventas → patrón de trabajo (best-effort)."""
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT WEEKDAY(fecha) d, COUNT(*) n FROM ventas WHERE id_empresa<=>%s "
                        "AND fecha >= DATE_SUB(CURDATE(), INTERVAL 60 DAY) GROUP BY d ORDER BY n DESC "
                        "LIMIT 1", (emp,))
            filas = _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("patron_actividad: %s", e)
        return 0
    if not filas:
        return 0
    d = filas[0].get("d")
    if d is None or int(d) >= len(_DIAS):
        return 0
    dia = _DIAS[int(d)]
    C.recordar(C.PATRON, "dia_mas_actividad",
               f"Los {dia} suelen ser los días de más actividad.", id_empresa=emp)
    return 1
