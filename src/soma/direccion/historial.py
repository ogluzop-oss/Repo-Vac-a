"""
Historial de recomendaciones + APRENDIZAJE de decisiones (Fase 7). Persiste qué recomendó SOMA, cuándo,
por qué y la decisión del usuario (aceptada/rechazada) para mejorar futuras recomendaciones. El
aprendizaje es LENTO y solo ajusta PRIORIDADES (nunca la personalidad): si el usuario rechaza
sistemáticamente un tipo, su prioridad baja; si lo acepta, sube. Persiste en `soma_recomendaciones`.
"""

import logging

from src.soma import prioridad as P

logger = logging.getLogger("soma.direccion.historial")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def registrar(ini, *, estado="PROPUESTA", usuario=None, id_empresa=None):
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO soma_recomendaciones (id_empresa, usuario, clave, tipo, dominio, "
                        "titulo, prioridad, mensaje, por_que, estado) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, usuario, (ini.get("clave") or "")[:64], ini.get("tipo", "riesgo"),
                         ini.get("dominio"), (ini.get("titulo") or "")[:200], ini.get("prioridad", "MEDIA"),
                         (ini.get("mensaje") or "")[:500], (ini.get("por_que") or "")[:500], estado))
            c.commit()
    except Exception as e:
        logger.debug("registrar recomendación: %s", e)


def decidir(clave, estado, *, usuario=None, id_empresa=None, resultado=None):
    """Marca la última recomendación con esa clave como ACEPTADA/RECHAZADA (aprendizaje)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE soma_recomendaciones SET estado=%s, resultado=%s, decidida=NOW() "
                        "WHERE id_empresa<=>%s AND clave=%s ORDER BY id DESC LIMIT 1",
                        (estado, (resultado or "")[:255], emp, clave[:64]))
            c.commit()
    except Exception as e:
        logger.debug("decidir recomendación: %s", e)


def ajuste_prioridad(tipo, *, usuario=None, id_empresa=None) -> int:
    """Aprendizaje lento: +1 si el usuario acepta ese tipo con frecuencia, -1 si lo rechaza mucho, 0
    si no hay señal clara. Se usa para subir/bajar la prioridad efectiva de nuevas iniciativas."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT estado, COUNT(*) n FROM soma_recomendaciones WHERE id_empresa<=>%s "
                        "AND tipo=%s AND estado IN ('ACEPTADA','RECHAZADA') GROUP BY estado", (emp, tipo))
            filas = {f["estado"]: int(f["n"]) for f in _filas_a_dicts(cur, cur.fetchall())}
    except Exception as e:
        logger.debug("ajuste_prioridad: %s", e)
        return 0
    acept, rech = filas.get("ACEPTADA", 0), filas.get("RECHAZADA", 0)
    if acept + rech < 3:
        return 0   # aún sin señal clara (aprendizaje lento)
    if acept >= rech * 2:
        return 1
    if rech >= acept * 2:
        return -1
    return 0


def aplicar_ajuste(prioridad, delta) -> str:
    """Sube/baja una prioridad `delta` niveles dentro de la escala."""
    escala = [P.MUY_BAJA, P.BAJA, P.MEDIA, P.ALTA, P.CRITICA]
    i = escala.index(prioridad) if prioridad in escala else 2
    j = max(0, min(len(escala) - 1, i + delta))
    return escala[j]
