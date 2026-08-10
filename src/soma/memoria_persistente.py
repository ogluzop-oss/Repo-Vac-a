"""
Memoria PERSISTENTE de SOMA (Fase 5). Aprende LENTAMENTE y guarda SOLO información útil: preferencias,
hábitos, módulos/empresas/tiendas frecuentes, idioma, configuraciones favoritas, decisiones
repetitivas. No almacena conversaciones. Persiste en `soma_memoria` (migr 0097). NO duplica la memoria
de sesión (`copilot.memoria`): la complementa (propósito distinto). Best-effort: nunca rompe el flujo.
"""

import logging

logger = logging.getLogger("soma.memoria_persistente")

UMBRAL_FRECUENTE = 3   # nº de usos para considerar algo "hábito/frecuente" (aprendizaje lento)


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def registrar_uso(usuario, tipo, clave, *, valor=None, id_empresa=None) -> int:
    """Incrementa el contador de un hábito (módulo abierto, exportación, dominio consultado…).
    Devuelve el contador acumulado. El 'aprendizaje' emerge de la frecuencia."""
    if not usuario:
        return 0
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO soma_memoria (id_empresa, usuario, tipo, clave, valor, contador) "
                "VALUES (%s,%s,%s,%s,%s,1) "
                "ON DUPLICATE KEY UPDATE contador=contador+1, valor=COALESCE(VALUES(valor), valor)",
                (emp, str(usuario)[:80], tipo, str(clave)[:120],
                 (str(valor)[:255] if valor is not None else None)))
            c.commit()
            cur.execute("SELECT contador FROM soma_memoria WHERE id_empresa<=>%s AND usuario=%s "
                        "AND tipo=%s AND clave=%s", (emp, str(usuario)[:80], tipo, str(clave)[:120]))
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else 0
    except Exception as e:
        logger.debug("registrar_uso: %s", e)
        return 0


def aprender(usuario, clave, valor, *, tipo="preferencia", id_empresa=None) -> bool:
    """Guarda/actualiza una preferencia o configuración explícita del usuario."""
    if not usuario:
        return False
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO soma_memoria (id_empresa, usuario, tipo, clave, valor, contador) "
                "VALUES (%s,%s,%s,%s,%s,1) "
                "ON DUPLICATE KEY UPDATE valor=VALUES(valor), contador=contador+1",
                (emp, str(usuario)[:80], tipo, str(clave)[:120], str(valor)[:255]))
            c.commit()
            return True
    except Exception as e:
        logger.debug("aprender: %s", e)
        return False


def preferencia(usuario, clave, defecto=None, *, id_empresa=None):
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT valor FROM soma_memoria WHERE id_empresa<=>%s AND usuario=%s "
                        "AND clave=%s ORDER BY contador DESC LIMIT 1",
                        (emp, str(usuario)[:80], str(clave)[:120]))
            r = cur.fetchone()
            if r:
                return (r[0] if not isinstance(r, dict) else list(r.values())[0]) or defecto
    except Exception as e:
        logger.debug("preferencia: %s", e)
    return defecto


def frecuentes(usuario, tipo, *, limite=5, minimo=UMBRAL_FRECUENTE, id_empresa=None) -> list:
    """Devuelve los hábitos que ya superan el umbral (aprendizaje lento). [{clave, valor, contador}]."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT clave, valor, contador FROM soma_memoria WHERE id_empresa<=>%s "
                        "AND usuario=%s AND tipo=%s AND contador>=%s ORDER BY contador DESC LIMIT %s",
                        (emp, str(usuario)[:80], tipo, int(minimo), int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("frecuentes: %s", e)
        return []


def perfil(usuario, *, id_empresa=None) -> dict:
    """Foto de lo aprendido del usuario (para el contexto de SOMA)."""
    return {
        "modulos_frecuentes": [f.get("clave") for f in frecuentes(usuario, "modulo", id_empresa=id_empresa)],
        "dominios_frecuentes": [f.get("clave") for f in frecuentes(usuario, "dominio", id_empresa=id_empresa)],
        "preferencias": {f.get("clave"): f.get("valor")
                         for f in frecuentes(usuario, "preferencia", minimo=1, id_empresa=id_empresa)},
    }
