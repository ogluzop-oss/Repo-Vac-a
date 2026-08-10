"""
Corporate Templates Manager (CCP Fase II · B1) — gestor documental de plantillas corporativas.

Evoluciona el sistema de plantillas SIN sustituirlo: categorías, idiomas, VERSIONADO con historial y
comparación, estados (borrador/producción/archivada), variables dinámicas, formatos (texto/HTML/
Markdown), import/export y render reutilizando el sistema existente (`ccp.plantillas` →
`plantillas_correo`). Multiempresa.

API-First: servicio puro (sin PyQt). Objetos = dicts serializables. Reutilizable desde REST/móvil/IA.
"""

import json
import logging
import re
from difflib import unified_diff

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("ccp.templates")

CATEGORIAS = ("general", "pedidos", "facturas", "contratos", "nominas", "aeat", "workflow",
              "campanas", "notificaciones", "legal")
FORMATOS = ("texto", "html", "markdown")
ESTADOS = ("borrador", "produccion", "archivada")
_RE_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _usuario(usuario=None):
    if usuario:
        return usuario
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        return str(u.get("nombre") or u.get("usuario") or "") or None
    except Exception:
        return None


def crear_plantilla(codigo, asunto, cuerpo, *, id_empresa=None, categoria="general", idioma="es",
                    formato="texto", estado="borrador", condiciones=None, autor=None) -> int | None:
    """Crea (o actualiza si ya existe codigo+idioma) una plantilla y su versión 1."""
    id_empresa = _emp(id_empresa)
    autor = _usuario(autor)
    if categoria not in CATEGORIAS:
        categoria = "general"
    if formato not in FORMATOS:
        formato = "texto"
    if estado not in ESTADOS:
        estado = "borrador"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO ccp_plantillas
                   (id_empresa, codigo, categoria, idioma, formato, estado, asunto, cuerpo,
                    condiciones, version_actual, autor)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s)
                   ON DUPLICATE KEY UPDATE categoria=VALUES(categoria), formato=VALUES(formato),
                     estado=VALUES(estado), asunto=VALUES(asunto), cuerpo=VALUES(cuerpo),
                     condiciones=VALUES(condiciones), actualizado=NOW()""",
                (id_empresa, codigo, categoria, idioma, formato, estado, asunto, cuerpo,
                 json.dumps(condiciones) if condiciones else None, autor))
            cur.execute("SELECT id, version_actual FROM ccp_plantillas WHERE id_empresa=%s AND "
                        "codigo=%s AND idioma=%s", (id_empresa, codigo, idioma))
            row = cur.fetchone()
            pid = row[0] if not isinstance(row, dict) else row.get("id")
            ver = (row[1] if not isinstance(row, dict) else row.get("version_actual")) or 1
            cur.execute(
                "INSERT INTO ccp_plantillas_versiones (id_plantilla, id_empresa, version, formato, "
                "estado, asunto, cuerpo, autor) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE asunto=VALUES(asunto), cuerpo=VALUES(cuerpo)",
                (pid, id_empresa, ver, formato, estado, asunto, cuerpo, autor))
            conn.commit()
            return pid
    except Exception as e:
        logger.error("crear_plantilla(%s): %s", codigo, e)
        return None


def nueva_version(id_plantilla, asunto, cuerpo, *, formato=None, autor=None, id_empresa=None) -> int:
    """Guarda una NUEVA versión (incrementa version_actual) conservando el historial. Devuelve la
    nueva versión."""
    id_empresa = _emp(id_empresa)
    autor = _usuario(autor)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT version_actual, formato FROM ccp_plantillas WHERE id=%s", (id_plantilla,))
            row = _fila_a_dict(cur, cur.fetchone())
            if not row:
                return 0
            nueva = int(row.get("version_actual") or 1) + 1
            fmt = formato or row.get("formato") or "texto"
            cur.execute("UPDATE ccp_plantillas SET asunto=%s, cuerpo=%s, formato=%s, version_actual=%s,"
                        " actualizado=NOW() WHERE id=%s", (asunto, cuerpo, fmt, nueva, id_plantilla))
            cur.execute("INSERT INTO ccp_plantillas_versiones (id_plantilla, id_empresa, version, "
                        "formato, estado, asunto, cuerpo, autor) VALUES (%s,%s,%s,%s,'borrador',%s,%s,%s)",
                        (id_plantilla, id_empresa, nueva, fmt, asunto, cuerpo, autor))
            conn.commit()
            return nueva
    except Exception as e:
        logger.error("nueva_version(%s): %s", id_plantilla, e)
        return 0


def cambiar_estado(id_plantilla, estado) -> bool:
    if estado not in ESTADOS:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE ccp_plantillas SET estado=%s, actualizado=NOW() WHERE id=%s",
                        (estado, id_plantilla))
            conn.commit()
            return True
    except Exception as e:
        logger.error("cambiar_estado(%s): %s", id_plantilla, e)
        return False


def listar_plantillas(id_empresa=None, *, categoria=None, idioma=None, estado=None) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM ccp_plantillas WHERE id_empresa=%s"
    p = [id_empresa]
    for col, val in (("categoria", categoria), ("idioma", idioma), ("estado", estado)):
        if val:
            q += f" AND {col}=%s"; p.append(val)
    q += " ORDER BY categoria, codigo"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_plantillas: %s", e)
        return []


def obtener_plantilla(id_plantilla) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM ccp_plantillas WHERE id=%s", (id_plantilla,))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_plantilla(%s): %s", id_plantilla, e)
        return None


def listar_versiones(id_plantilla) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM ccp_plantillas_versiones WHERE id_plantilla=%s ORDER BY "
                        "version DESC", (id_plantilla,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_versiones(%s): %s", id_plantilla, e)
        return []


def comparar_versiones(id_plantilla, v1, v2) -> str:
    """Diff unificado del cuerpo entre dos versiones (texto)."""
    vers = {v["version"]: v for v in listar_versiones(id_plantilla)}
    a, b = vers.get(v1), vers.get(v2)
    if not a or not b:
        return ""
    return "\n".join(unified_diff((a.get("cuerpo") or "").splitlines(),
                                  (b.get("cuerpo") or "").splitlines(),
                                  fromfile=f"v{v1}", tofile=f"v{v2}", lineterm=""))


def _sustituir(texto, variables):
    return _RE_VAR.sub(lambda m: str((variables or {}).get(m.group(1), m.group(0))), texto or "")


def render(codigo, variables=None, *, id_empresa=None, idioma="es"):
    """Devuelve (asunto, cuerpo) de una plantilla corporativa con variables sustituidas y decoradores
    (firma/logo/pie). Prefiere una plantilla en PRODUCCIÓN; si no existe en `ccp_plantillas`, degrada
    al sistema anterior (`ccp.plantillas` → `plantillas_correo`). None si no hay plantilla."""
    id_empresa = _emp(id_empresa)
    fila = None
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT asunto, cuerpo FROM ccp_plantillas WHERE id_empresa=%s AND codigo=%s "
                        "AND idioma=%s AND estado='produccion'", (id_empresa, codigo, idioma))
            fila = _fila_a_dict(cur, cur.fetchone())
            if not fila:
                cur.execute("SELECT asunto, cuerpo FROM ccp_plantillas WHERE id_empresa=%s AND "
                            "codigo=%s AND idioma=%s ORDER BY FIELD(estado,'produccion','borrador',"
                            "'archivada') LIMIT 1", (id_empresa, codigo, idioma))
                fila = _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.debug("render lookup %s: %s", codigo, e)
    if fila:
        asunto = _sustituir(fila.get("asunto"), variables)
        cuerpo = _sustituir(fila.get("cuerpo"), variables)
        try:
            from src.services.ccp import plantillas as _pl
            for fn in getattr(_pl, "_DECORADORES", []):
                asunto, cuerpo = fn(asunto, cuerpo, id_empresa=id_empresa, idioma=idioma)
        except Exception:
            pass
        return asunto, cuerpo
    # Degradación al sistema anterior.
    try:
        from src.services.ccp import plantillas as _pl
        return _pl.render(codigo, variables or {}, id_empresa=id_empresa, idioma=idioma)
    except Exception:
        return None


# ── Import / Export ───────────────────────────────────────────────────────────
def exportar(id_plantilla) -> dict | None:
    p = obtener_plantilla(id_plantilla)
    if not p:
        return None
    return {"codigo": p.get("codigo"), "categoria": p.get("categoria"), "idioma": p.get("idioma"),
            "formato": p.get("formato"), "estado": p.get("estado"), "asunto": p.get("asunto"),
            "cuerpo": p.get("cuerpo"), "versiones": listar_versiones(id_plantilla)}


def importar(data, *, id_empresa=None) -> int | None:
    if isinstance(data, str):
        data = json.loads(data)
    return crear_plantilla(data.get("codigo"), data.get("asunto"), data.get("cuerpo"),
                           id_empresa=id_empresa, categoria=data.get("categoria", "general"),
                           idioma=data.get("idioma", "es"), formato=data.get("formato", "texto"),
                           estado=data.get("estado", "borrador"))
