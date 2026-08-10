"""
Tests · Preparación de despliegue SaaS (Fase 2) — lo VALIDABLE localmente, sin infraestructura externa.

  · Backup/restore por tenant (Fase 10): export a JSON → integridad → restore round-trip real (reutiliza
    `dr/backup_operacional` → `saas/backup_tenant`). NO valida RPO/RTO productivo (eso es [EXTERNO]).
  · Configuración por entorno (Fase 4): existen `.env.example` / `.env.staging.example` /
    `.env.production.example` y NO contienen secretos reales (solo placeholders).

El aislamiento multi-tenant, los health checks y la API pública se validan en `test_cloud_infra.py` y
`test_capacidades_avanzadas.py`. Aquí no se duplican.
"""

import json
import os

import pytest

pytestmark = pytest.mark.db

EMP = "T-DEPLOY-1"
COD = "DEPLOY_ART"
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM articulos WHERE id_empresa=%s AND codigo=%s", (EMP, COD))
            c.commit()
    _b()
    yield
    _b()


def test_backup_restore_tenant_local(limpia, db):
    from src.services.dr import backup_operacional

    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, Stock_tienda) "
                    "VALUES (%s,%s,%s,%s,%s)", (COD, EMP, "Artículo backup", 9.99, 5))
        c.commit()

    # 1) BACKUP: exporta el tenant (solo la tabla articulos para un artefacto pequeño y determinista).
    r = backup_operacional.exportar_tenant(id_empresa=EMP, tablas=["articulos"])
    ruta = r.get("ruta")
    assert ruta and os.path.exists(ruta), "el backup debe escribir un artefacto en disco"
    assert r.get("filas", 0) >= 1

    # 2) INTEGRIDAD: el artefacto contiene el registro exportado.
    with open(ruta, encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc.get("id_empresa") == EMP
    arts = doc.get("datos", {}).get("articulos", [])
    assert any(a.get("codigo") == COD for a in arts), "el backup debe contener el registro del tenant"

    # 3) RESTORE round-trip: borramos el registro y lo restauramos desde el backup.
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("DELETE FROM articulos WHERE id_empresa=%s AND codigo=%s", (EMP, COD))
        c.commit()
    from src.services.saas import backup_tenant
    res = backup_tenant.importar_empresa(ruta, id_empresa=EMP, tablas=["articulos"], reemplazar=False)
    assert res.get("ok") is True
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM articulos WHERE id_empresa=%s AND codigo=%s", (EMP, COD))
        row = cur.fetchone()
        assert (row[0] if not isinstance(row, dict) else list(row.values())[0]) == 1  # restaurado

    # Limpieza del artefacto de backup.
    try:
        os.remove(ruta)
    except OSError:
        pass


@pytest.mark.parametrize("fichero", [".env.example", ".env.staging.example", ".env.production.example"])
def test_env_examples_sin_secretos(fichero):
    ruta = os.path.join(_RAIZ, fichero)
    assert os.path.exists(ruta), f"debe existir {fichero}"
    contenido = open(ruta, encoding="utf-8").read()
    # Los ejemplos de STAGING/PROD no deben traer secretos reales (solo placeholders <...> o vacíos).
    if fichero != ".env.example":
        for var in ("SMART_MANAGER_JWT_SECRET", "DB_PASSWORD"):
            for linea in contenido.splitlines():
                if linea.startswith(var + "="):
                    val = linea.split("=", 1)[1].strip()
                    assert val == "" or val.startswith("<"), \
                        f"{fichero}:{var} no debe contener un secreto real (usar placeholder)"
