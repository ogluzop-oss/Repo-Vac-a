"""
IOC v2 · Jerarquía — navegación y resolución jerárquica del Identity Core.

Jerarquía: Grupo → Empresa → Centro → Subcentro → Zona → Terminal → Dispositivo → Usuario.
Los niveles Centro/Subcentro/Zona se representan en `centros_trabajo` (columna `nivel` +
`id_centro_padre`), sin tablas por nivel. Ofrece:
  · navegación ASCENDENTE (`cadena_ascendente`): de un centro hasta el grupo,
  · navegación DESCENDENTE (`descendientes`): todos los hijos recursivos,
  · herencia de configuración con OVERRIDE local (`config_resuelta`).
Solo lectura sobre entidades existentes; multiempresa. No duplica nada.
"""

import logging

from src.services.identidad import _base as B

logger = logging.getLogger("identidad.jerarquia")


def _centro(id_centro):
    try:
        from src.db import centros as _c
        return _c.obtener_centro(id_centro)
    except Exception:
        return None


def cadena_ascendente(id_centro, *, id_empresa=None) -> list:
    """Devuelve la cadena de nodos desde el centro dado hasta la raíz (grupo), de hijo a padre.
    Cada elemento: {nivel, tipo, id, nombre}. Evita ciclos."""
    id_empresa = B.emp(id_empresa)
    cadena, visitados, actual = [], set(), id_centro
    while actual and actual not in visitados:
        visitados.add(actual)
        c = _centro(actual)
        if not c:
            break
        cadena.append({"nivel": c.get("nivel") or "CENTRO", "tipo": c.get("tipo"),
                       "id": c.get("id_centro"), "nombre": c.get("nombre_centro"),
                       "id_empresa": c.get("id_empresa"), "id_centro_padre": c.get("id_centro_padre")})
        actual = c.get("id_centro_padre")
    # Añadir empresa y grupo como niveles raíz.
    emp = cadena[-1]["id_empresa"] if cadena else id_empresa
    if emp:
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT id_empresa, nombre_empresa, id_grupo FROM empresas WHERE id_empresa=%s",
                            (emp,))
                e = B.fila(cur)
            if e:
                cadena.append({"nivel": "EMPRESA", "tipo": "EMPRESA", "id": e.get("id_empresa"),
                               "nombre": e.get("nombre_empresa"), "id_empresa": e.get("id_empresa")})
                if e.get("id_grupo"):
                    from src.services.identidad import grupos
                    g = grupos.obtener_grupo(e["id_grupo"]) or {}
                    cadena.append({"nivel": "GRUPO", "tipo": g.get("tipo") or "GRUPO",
                                   "id": e["id_grupo"], "nombre": g.get("nombre")})
        except Exception as e:
            logger.debug("cadena_ascendente raíz: %s", e)
    return cadena


def descendientes(id_centro, *, id_empresa=None, incluir_self=False) -> list:
    """Todos los centros descendientes (recursivo) del nodo dado. Best-effort, evita ciclos."""
    id_empresa = B.emp(id_empresa)
    resultado, pendientes, visitados = [], [id_centro], set()
    try:
        from src.services.identidad import centros as _cs
        if incluir_self:
            c = _centro(id_centro)
            if c:
                resultado.append(c)
        while pendientes:
            padre = pendientes.pop()
            if padre in visitados:
                continue
            visitados.add(padre)
            hijos = _cs.hijos_de(padre, id_empresa=id_empresa)
            for h in hijos:
                resultado.append(h)
                pendientes.append(h.get("id_centro"))
        return resultado
    except Exception as e:
        logger.error("descendientes: %s", e)
        return resultado


def config_resuelta(id_centro, atributo, *, id_empresa=None):
    """Herencia con override local: resuelve el valor de `atributo` subiendo por la cadena hasta el
    primer nodo que lo tenga definido (el más local gana). Devuelve {valor, origen_id, origen_nivel}
    o None si no está definido en ninguna parte de la cadena."""
    id_empresa = B.emp(id_empresa)
    for nodo in cadena_ascendente(id_centro, id_empresa=id_empresa):
        nid = nodo.get("id")
        if not nid:
            continue
        # Centros: leer atributo directamente; grupo/empresa se omiten salvo atributos propios.
        c = _centro(nid)
        if c and c.get(atributo) not in (None, ""):
            return {"valor": c.get(atributo), "origen_id": nid, "origen_nivel": nodo.get("nivel")}
    return None
