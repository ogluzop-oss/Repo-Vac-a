"""
Migración 0334 — Adaptador REST genérico para el datáfono (petición explícita: reducir la
incertidumbre de "cada banco envuelve Redsys/PAX a su manera" convirtiendo el ajuste en CONFIG, no
en código). ADITIVA, idempotente, reversible.

`adaptador_json` guarda, SOLO para el proveedor "generico", la forma de la API del banco (base_url,
tipo de autenticación, rutas y plantillas de petición/respuesta) — ver
`services.tpv.datafono.generico`. No son credenciales (esas siguen en `api_key`/`api_secret`,
cifradas); es la FORMA de la integración, así que se guarda en claro.
"""

VERSION = "0334"
DESCRIPCION = "Adaptador REST genérico del datáfono (config en vez de código por banco)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute(
        "ALTER TABLE tpv_datafono_config "
        "ADD COLUMN IF NOT EXISTS adaptador_json TEXT DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE tpv_datafono_config DROP COLUMN IF EXISTS adaptador_json")
