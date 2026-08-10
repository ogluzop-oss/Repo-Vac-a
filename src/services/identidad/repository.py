"""
IOC v2 · IdentityRepository (Parte 1.6) — punto ÚNICO de acceso a la información de identidad.

Compone los servicios de dominio existentes (centros/grupos/terminales/impresoras/codigos/jerarquia)
y los sirve a través de `IdentityCache` (TTL + multiempresa + invalidación por Event Bus). Es de solo
lectura: las mutaciones pasan por `IdentityService`. Ningún consumidor externo debe usar el Repository
directamente (usan el Service); y ninguna GUI accede a `conexion.execute(...)`.
"""

import logging

from src.services.identidad import _base as B
from src.services.identidad.cache import cache

logger = logging.getLogger("identidad.repository")


class IdentityRepository:
    def __init__(self):
        self._c = cache()

    # ── Getters por entidad ──────────────────────────────────────────────────
    def get_centro(self, id_centro, *, id_empresa=None):
        emp = B.emp(id_empresa)
        return self._c.obtener_o_calcular(emp, "centro", id_centro, lambda: self._calc_centro(id_centro))

    def _calc_centro(self, id_centro):
        from src.services.identidad import centros
        return centros.obtener_centro(id_centro)

    def get_empresa(self, id_empresa=None):
        emp = B.emp(id_empresa)
        return self._c.obtener_o_calcular(emp, "empresa", emp, lambda: self._calc_empresa(emp))

    def _calc_empresa(self, id_empresa):
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM empresas WHERE id_empresa=%s", (id_empresa,))
                return B.fila(cur)
        except Exception as e:
            logger.debug("_calc_empresa: %s", e)
            return None

    def get_grupo(self, id_grupo):
        return self._c.obtener_o_calcular("_", "grupo", id_grupo, lambda: self._calc_grupo(id_grupo))

    def _calc_grupo(self, id_grupo):
        from src.services.identidad import grupos
        return grupos.obtener_grupo(id_grupo)

    def get_terminal(self, id_terminal, *, id_empresa=None):
        emp = B.emp(id_empresa)
        return self._c.obtener_o_calcular(emp, "terminal", id_terminal,
                                          lambda: self._calc_terminal(id_terminal))

    def _calc_terminal(self, id_terminal):
        from src.services.identidad import terminales
        return terminales.obtener_terminal(id_terminal)

    def get_impresora(self, id_impresora, *, id_empresa=None):
        emp = B.emp(id_empresa)
        def _calc():
            from src.services.identidad import impresoras
            for imp in impresoras.listar_impresoras(id_empresa=emp):
                if imp.get("id") == id_impresora:
                    return imp
            return None
        return self._c.obtener_o_calcular(emp, "impresora", id_impresora, _calc)

    # ── Jerarquía ────────────────────────────────────────────────────────────
    def get_jerarquia(self, id_centro, *, id_empresa=None):
        emp = B.emp(id_empresa)
        def _calc():
            from src.services.identidad import jerarquia
            return {"ascendentes": jerarquia.cadena_ascendente(id_centro, id_empresa=emp),
                    "descendientes": jerarquia.descendientes(id_centro, id_empresa=emp)}
        return self._c.obtener_o_calcular(emp, "jerarquia", id_centro, _calc)

    def get_ascendentes(self, id_centro, *, id_empresa=None):
        return (self.get_jerarquia(id_centro, id_empresa=id_empresa) or {}).get("ascendentes", [])

    def get_descendientes(self, id_centro, *, id_empresa=None):
        return (self.get_jerarquia(id_centro, id_empresa=id_empresa) or {}).get("descendientes", [])

    def get_codigos(self, id_centro):
        from src.services.identidad import codigos
        return codigos.codigos_de_centro(id_centro)

    def get_config_heredada(self, id_centro, atributo, *, id_empresa=None):
        from src.services.identidad import jerarquia
        return jerarquia.config_resuelta(id_centro, atributo, id_empresa=B.emp(id_empresa))

    # ── Búsquedas genéricas (extensibles; sin métodos por módulo) ────────────
    def buscar_por_uuid(self, uuid_val, *, id_empresa=None):
        """Resuelve una entidad por su UUID probando centro→terminal→impresora→grupo."""
        emp = B.emp(id_empresa)
        c = self.get_centro(uuid_val, id_empresa=emp)
        if c:
            return {"tipo_entidad": "centro", "entidad": c}
        t = self.get_terminal(uuid_val, id_empresa=emp)
        if t:
            return {"tipo_entidad": "terminal", "entidad": t}
        imp = self.get_impresora(uuid_val, id_empresa=emp)
        if imp:
            return {"tipo_entidad": "impresora", "entidad": imp}
        g = self.get_grupo(uuid_val)
        if g:
            return {"tipo_entidad": "grupo", "entidad": g}
        return None

    def buscar_por_codigo(self, tipo_codigo, valor, *, id_empresa=None):
        from src.services.identidad import codigos
        id_centro = codigos.buscar_por_codigo(tipo_codigo, valor, id_empresa=B.emp(id_empresa))
        return self.get_centro(id_centro, id_empresa=id_empresa) if id_centro else None

    def buscar_por_tipo(self, tipo, *, id_empresa=None):
        from src.services.identidad import centros
        return centros.listar_centros(id_empresa=B.emp(id_empresa), tipo=tipo)

    def buscar_por_estado(self, estado_gobierno, *, id_empresa=None):
        emp = B.emp(id_empresa)
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM centros_trabajo WHERE id_empresa=%s AND estado_gobierno=%s",
                            (emp, estado_gobierno))
                return B.filas(cur)
        except Exception as e:
            logger.error("buscar_por_estado: %s", e)
            return []

    def buscar_por_empresa(self, id_empresa=None):
        from src.services.identidad import centros
        return centros.listar_centros(id_empresa=B.emp(id_empresa), incluir_archivados=True,
                                      solo_activos=False)

    def buscar_por_grupo(self, id_grupo):
        from src.services.identidad import grupos
        return grupos.empresas_de_grupo(id_grupo)


_REPO = IdentityRepository()


def repository() -> IdentityRepository:
    return _REPO
