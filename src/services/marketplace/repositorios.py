"""
Marketplace · Repositorios (Fase IV · Bloque 2). Un módulo puede provenir de: Marketplace Oficial,
Marketplace Privado, Repositorio Git, ZIP firmado o Repositorio Local. Registro por empresa
(`marketplace_repositorios`) + lectura de plugins disponibles. DEGRADABLE: local/zip/oficial se
leen del sistema de ficheros ahora mismo; git/privado remoto quedan preparados (devuelven []).
"""

from __future__ import annotations

import logging
import os

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion
from src.sdk import plugin_manifest

logger = logging.getLogger("marketplace.repositorios")

OFICIAL, PRIVADO, GIT, ZIP, LOCAL = "oficial", "privado", "git", "zip", "local"
TIPOS = (OFICIAL, PRIVADO, GIT, ZIP, LOCAL)

# Repositorio OFICIAL integrado: la carpeta `plugins/` del propio proyecto.
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REPO_OFICIAL = {"nombre": "oficial", "tipo": OFICIAL, "url": os.path.join(_RAIZ, "plugins"),
                 "prioridad": 0, "activo": 1, "integrado": True}


def registrar_repositorio(nombre, tipo, *, url=None, id_empresa=None, prioridad=100) -> bool:
    if tipo not in TIPOS:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO marketplace_repositorios (id_empresa, nombre, tipo, url, prioridad, "
                "activo) VALUES (%s,%s,%s,%s,%s,1) ON DUPLICATE KEY UPDATE tipo=VALUES(tipo), "
                "url=VALUES(url), prioridad=VALUES(prioridad), activo=1",
                (id_empresa, nombre, tipo, url, prioridad))
            conn.commit()
        return True
    except Exception as e:
        logger.error("registrar_repositorio(%s): %s", nombre, e)
        return False


def listar_repositorios(id_empresa=None) -> list:
    """Repos de la empresa (+ globales) + el repositorio oficial integrado, por prioridad."""
    repos = [dict(_REPO_OFICIAL)]
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM marketplace_repositorios WHERE (id_empresa=%s OR id_empresa "
                        "IS NULL) AND activo=1 ORDER BY prioridad ASC", (id_empresa,))
            repos += _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_repositorios: %s", e)
    return sorted(repos, key=lambda r: r.get("prioridad", 100))


def _plugins_local(ruta) -> list:
    """Lee los manifests de una carpeta local (cada subcarpeta con manifest.json es un plugin)."""
    salida = []
    if not ruta or not os.path.isdir(ruta):
        return salida
    for entrada in sorted(os.listdir(ruta)):
        sub = os.path.join(ruta, entrada)
        if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "manifest.json")):
            m = plugin_manifest.cargar(sub)
            if m:
                m = dict(m); m["_ruta"] = sub
                salida.append(m)
    return salida


def plugins_de(repo) -> list:
    """Plugins disponibles en un repositorio. Local/zip(desempaquetado)/oficial: filesystem;
    git/privado remoto: preparado (vacío hasta cablear el cliente remoto)."""
    tipo = repo.get("tipo")
    url = repo.get("url")
    if tipo in (OFICIAL, LOCAL):
        return _plugins_local(url)
    if tipo == ZIP:
        # Un ZIP firmado se trataría desempaquetándolo a una carpeta temporal; si `url` ya es una
        # carpeta desempaquetada, se lee igual que local (degradable).
        return _plugins_local(url)
    # git / privado remoto: PREPARADO (requiere cliente remoto; sin red aquí).
    return []


__all__ = ["TIPOS", "OFICIAL", "PRIVADO", "GIT", "ZIP", "LOCAL",
           "registrar_repositorio", "listar_repositorios", "plugins_de"]
