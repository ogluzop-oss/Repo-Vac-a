"""
MEMORIA EMPRESARIAL a largo plazo (Fase 8). SOMA recuerda cómo trabaja la empresa — NUNCA
conversaciones. Solo conocimiento útil: decisiones importantes, preferencias reales, hábitos, patrones
de trabajo, configuraciones frecuentes, iniciativas realizadas y objetivos completados. Aprendizaje
LENTO (contador) y REVERSIBLE (olvidar → activo=0). Persiste en `soma_empresa_conocimiento` (migr 0100).

No sustituye ni modifica la memoria de sesión ([[project]] copilot.memoria) ni la memoria persistente
por usuario (Fase 5 `memoria_persistente`, soma_memoria): es una capa NUEVA, por EMPRESA.
"""

import logging

logger = logging.getLogger("soma.empresa.conocimiento")

# Tipos de conocimiento (cerrado por diseño; nunca "conversación").
DECISION = "decision"
PREFERENCIA = "preferencia"
HABITO = "habito"
PATRON = "patron"
CONFIG = "config"
INICIATIVA = "iniciativa"
OBJETIVO = "objetivo"

UMBRAL_HABITO = 3   # nº de refuerzos para considerarlo consolidado (aprendizaje lento)


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def recordar(tipo, clave, valor=None, *, id_empresa=None) -> int:
    """Aprende/refuerza un hecho de la empresa. Devuelve el contador acumulado. Best-effort."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO soma_empresa_conocimiento (id_empresa, tipo, clave, valor, contador, activo) "
                "VALUES (%s,%s,%s,%s,1,1) "
                "ON DUPLICATE KEY UPDATE contador=contador+1, activo=1, "
                "valor=COALESCE(VALUES(valor), valor)",
                (emp, str(tipo)[:24], str(clave)[:140],
                 (str(valor)[:400] if valor is not None else None)))
            c.commit()
            cur.execute("SELECT contador FROM soma_empresa_conocimiento WHERE id_empresa<=>%s AND "
                        "tipo=%s AND clave=%s", (emp, str(tipo)[:24], str(clave)[:140]))
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else 0
    except Exception as e:
        logger.debug("recordar: %s", e)
        return 0


def olvidar(tipo, clave, *, id_empresa=None) -> bool:
    """Reversible: marca un conocimiento como olvidado (activo=0). Nunca invasivo."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE soma_empresa_conocimiento SET activo=0 WHERE id_empresa<=>%s AND "
                        "tipo=%s AND clave=%s", (emp, str(tipo)[:24], str(clave)[:140]))
            c.commit()
            return True
    except Exception as e:
        logger.debug("olvidar: %s", e)
        return False


def saber(tipo=None, *, minimo=1, limite=20, id_empresa=None) -> list:
    """Devuelve el conocimiento vivo (activo) de la empresa. [{tipo, clave, valor, contador}]."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = ("SELECT tipo, clave, valor, contador FROM soma_empresa_conocimiento "
                 "WHERE id_empresa<=>%s AND activo=1 AND contador>=%s")
            p = [emp, int(minimo)]
            if tipo:
                q += " AND tipo=%s"; p.append(str(tipo)[:24])
            q += " ORDER BY contador DESC, actualizado DESC LIMIT %s"; p.append(int(limite))
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("saber: %s", e)
        return []


def consolidado(tipo, *, id_empresa=None) -> list:
    """Solo hechos ya consolidados como hábito (superan el umbral de aprendizaje lento)."""
    return saber(tipo, minimo=UMBRAL_HABITO, id_empresa=id_empresa)


def resumen(id_empresa=None) -> dict:
    """Foto del conocimiento vivo de la empresa, agrupado por tipo (para el contexto de SOMA)."""
    out = {DECISION: [], PREFERENCIA: [], HABITO: [], PATRON: [], CONFIG: [], INICIATIVA: [], OBJETIVO: []}
    for h in saber(id_empresa=id_empresa, limite=60):
        out.setdefault(h.get("tipo"), []).append(h)
    return out


def frase(id_empresa=None, *, limite=3) -> str:
    """Una o dos frases naturales con lo que SOMA sabe de la empresa (para continuidad/personalidad)."""
    hechos = [h for h in saber(id_empresa=id_empresa, minimo=UMBRAL_HABITO, limite=limite)
              if h.get("valor")]
    if not hechos:
        return ""
    return " ".join(h["valor"].rstrip(".") + "." for h in hechos[:limite])
