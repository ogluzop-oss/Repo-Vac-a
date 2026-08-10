"""
IOC v2 · IdentityResolver (Parte 1.8) — resuelve CUALQUIER identidad del sistema a un contexto
completo (`IdentityContext`), nunca a cadenas sueltas. Se apoya en `IdentityRepository` (y por tanto
en la caché). Publica `identidad.resuelta`. No accede a la BD directamente ni a módulos funcionales.
"""

import logging
from dataclasses import asdict, dataclass, field

from src.services.identidad import _base as B
from src.services.identidad.repository import repository

logger = logging.getLogger("identidad.resolver")


@dataclass
class IdentityContext:
    """Contexto de identidad completo que consumirán los módulos (documentos/TPV/CRM/…)."""
    id_empresa: str | None = None
    empresa: dict | None = None
    grupo: dict | None = None
    id_centro: str | None = None
    centro: dict | None = None
    id_terminal: str | None = None
    terminal: dict | None = None
    id_tienda: object | None = None
    tienda: dict | None = None
    id_almacen: object | None = None
    usuario: str | None = None
    jerarquia: list = field(default_factory=list)
    propietario: str | None = None
    responsable: str | None = None
    codigos: dict = field(default_factory=dict)
    estado: str | None = None
    origen: str | None = None  # cómo se resolvió

    def to_dict(self) -> dict:
        return asdict(self)


class IdentityResolver:
    def __init__(self):
        self._repo = repository()

    def _construir(self, *, id_empresa=None, id_centro=None, id_terminal=None, id_tienda=None,
                   id_almacen=None, usuario=None, origen=None) -> IdentityContext:
        emp = B.emp(id_empresa)
        ctx = IdentityContext(id_empresa=emp, id_centro=id_centro, id_terminal=id_terminal,
                              id_tienda=id_tienda, id_almacen=id_almacen,
                              usuario=usuario or B.usuario_actual(), origen=origen)
        ctx.empresa = self._repo.get_empresa(emp)
        if ctx.empresa and ctx.empresa.get("id_grupo"):
            ctx.grupo = self._repo.get_grupo(ctx.empresa["id_grupo"])
        # Terminal → deduce centro si no se dio.
        if id_terminal:
            ctx.terminal = self._repo.get_terminal(id_terminal, id_empresa=emp)
            if ctx.terminal and not id_centro:
                id_centro = ctx.terminal.get("id_centro"); ctx.id_centro = id_centro
        # Centro + jerarquía + gobierno + códigos.
        if id_centro:
            ctx.centro = self._repo.get_centro(id_centro, id_empresa=emp)
            if ctx.centro:
                ctx.propietario = ctx.centro.get("id_propietario")
                ctx.responsable = ctx.centro.get("id_responsable_operativo")
                ctx.estado = ctx.centro.get("estado_gobierno")
            ctx.jerarquia = self._repo.get_ascendentes(id_centro, id_empresa=emp)
            ctx.codigos = self._repo.get_codigos(id_centro)
        # Tienda
        if id_tienda is not None:
            try:
                from src.db.tiendas import obtener_tienda
                ctx.tienda = obtener_tienda(id_tienda)
            except Exception:
                pass
        try:
            from src.services import eventos
            eventos.publicar("identidad.resuelta", id_empresa=emp, ref_entidad="identidad",
                             ref_id=id_centro or id_terminal or emp,
                             payload={"origen": origen})
        except Exception:
            pass
        return ctx

    # ── Resoluciones ─────────────────────────────────────────────────────────
    def resolver_por_uuid(self, uuid_val, *, id_empresa=None) -> IdentityContext:
        emp = B.emp(id_empresa)
        hit = self._repo.buscar_por_uuid(uuid_val, id_empresa=emp)
        if not hit:
            return self._construir(id_empresa=emp, origen="uuid_no_encontrado")
        te = hit["tipo_entidad"]
        if te == "centro":
            return self._construir(id_empresa=emp, id_centro=uuid_val, origen="uuid:centro")
        if te == "terminal":
            return self._construir(id_empresa=emp, id_terminal=uuid_val, origen="uuid:terminal")
        return self._construir(id_empresa=emp, origen=f"uuid:{te}")

    def resolver_por_codigo(self, tipo_codigo, valor, *, id_empresa=None) -> IdentityContext:
        emp = B.emp(id_empresa)
        centro = self._repo.buscar_por_codigo(tipo_codigo, valor, id_empresa=emp)
        return self._construir(id_empresa=emp, id_centro=(centro or {}).get("id_centro"),
                               origen=f"codigo:{tipo_codigo}")

    def resolver_por_terminal(self, id_terminal, *, id_empresa=None) -> IdentityContext:
        return self._construir(id_empresa=id_empresa, id_terminal=id_terminal, origen="terminal")

    def resolver_por_impresora(self, id_impresora, *, id_empresa=None) -> IdentityContext:
        emp = B.emp(id_empresa)
        imp = self._repo.get_impresora(id_impresora, id_empresa=emp) or {}
        return self._construir(id_empresa=emp, id_centro=imp.get("id_centro"),
                               id_terminal=imp.get("id_terminal"), origen="impresora")

    def resolver_por_usuario(self, usuario, *, id_empresa=None) -> IdentityContext:
        return self._construir(id_empresa=id_empresa, usuario=usuario, origen="usuario")

    def resolver_por_empresa(self, id_empresa=None) -> IdentityContext:
        return self._construir(id_empresa=id_empresa, origen="empresa")

    def resolver_por_tienda(self, id_tienda, *, id_empresa=None) -> IdentityContext:
        return self._construir(id_empresa=id_empresa, id_tienda=id_tienda, origen="tienda")

    def resolver_por_almacen(self, id_almacen, *, id_empresa=None) -> IdentityContext:
        return self._construir(id_empresa=id_empresa, id_almacen=id_almacen, origen="almacen")

    def resolver_por_documento(self, *, id_empresa=None, id_centro=None, id_terminal=None,
                               id_tienda=None, id_almacen=None, usuario=None) -> IdentityContext:
        return self._construir(id_empresa=id_empresa, id_centro=id_centro, id_terminal=id_terminal,
                               id_tienda=id_tienda, id_almacen=id_almacen, usuario=usuario,
                               origen="documento")


_RESOLVER = IdentityResolver()


def resolver() -> IdentityResolver:
    return _RESOLVER
