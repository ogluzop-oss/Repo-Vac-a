"""
IOC v2 · Identity API (Bloque 2.1) — ÚNICA interfaz pública oficial de identidad del ERP.

A partir de este bloque, ningún módulo nuevo accede a Repository/Cache/SQL: el único punto de entrada
es esta API. Es una FACHADA: reutiliza `IdentityService`, `IdentityResolver`,
`IdentityValidationEngine` y (solo lectura) `IdentityRepository`. Nunca ejecuta SQL. Devuelve siempre
MODELOS PÚBLICOS (`IdentityResult`/`IdentitySearchResult`/`IdentityHierarchy`/…), nunca objetos
internos. Resuelve `id_empresa` automáticamente (sin consultas cruzadas), registra telemetría y
publica eventos `identity.api.*`. Preparada para versionado (v1/v2/v3) sin romper compatibilidad.

Arquitectura:  ERP → IdentityAPI → IdentityService → IdentityRepository → IdentityCache → BD.
"""

import logging
import threading
import time

from src.services.identidad import _base as B
from src.services.identidad.excepciones import (
    IdentityException, IdentityHierarchyError, IdentityNotFound, IdentityValidationError,
)
from src.services.identidad.modelos import (
    IdentityHierarchy, IdentityReference, IdentityResult, IdentitySearchResult, IdentitySummary,
)

logger = logging.getLogger("identidad.api")

API_VERSION = "v2"                     # versión pública actual
VERSIONES_SOPORTADAS = ("v1", "v2")    # arquitectura lista para v3 sin romper compatibilidad


# ── Telemetría (in-process; lista para Prometheus/OpenTelemetry, sin integrar aún) ──
class _Telemetria:
    def __init__(self):
        self._lock = threading.RLock()
        self.llamadas = 0
        self.errores = 0
        self.validaciones_fallidas = 0
        self.tiempo_total_ms = 0.0
        self.por_metodo = {}

    def registrar(self, metodo, duracion_ms, ok):
        with self._lock:
            self.llamadas += 1
            self.tiempo_total_ms += duracion_ms
            if not ok:
                self.errores += 1
            m = self.por_metodo.setdefault(metodo, {"llamadas": 0, "errores": 0, "tiempo_ms": 0.0})
            m["llamadas"] += 1
            m["tiempo_ms"] += duracion_ms
            if not ok:
                m["errores"] += 1

    def snapshot(self) -> dict:
        with self._lock:
            from src.services.identidad.cache import cache
            cm = cache().metricas()
            return {"llamadas": self.llamadas, "errores": self.errores,
                    "validaciones_fallidas": self.validaciones_fallidas,
                    "tiempo_total_ms": round(self.tiempo_total_ms, 2),
                    "tiempo_medio_ms": round(self.tiempo_total_ms / self.llamadas, 2) if self.llamadas else 0,
                    "cache_hits": cm.get("hits"), "cache_miss": cm.get("miss"),
                    "cache_ratio": cm.get("ratio_acierto"), "por_metodo": dict(self.por_metodo)}


class IdentityAPI:
    def __init__(self, version=API_VERSION):
        if version not in VERSIONES_SOPORTADAS:
            version = API_VERSION
        self.version = version
        self._tel = _Telemetria()
        from src.services.identidad.service import service
        from src.services.identidad.resolver import resolver
        from src.services.identidad.validation import validation_engine
        from src.services.identidad.repository import repository
        self._service = service()
        self._resolver = resolver()
        self._val = validation_engine()
        self._repo = repository()

    # ── Núcleo de instrumentación ────────────────────────────────────────────
    def _medir(self, metodo, fn, *, id_empresa=None):
        """Ejecuta `fn`, mide tiempo, registra telemetría y publica eventos. Propaga las excepciones
        propias de identidad; envuelve las inesperadas en IdentityException."""
        t0 = time.time()
        ok = True
        try:
            self._evento("identity.api.called", id_empresa, {"metodo": metodo, "version": self.version})
            return fn()
        except IdentityException as e:
            ok = False
            self._evento("identity.api.failed", id_empresa, {"metodo": metodo, "codigo": e.codigo})
            raise
        except Exception as e:
            ok = False
            self._evento("identity.api.failed", id_empresa, {"metodo": metodo, "error": str(e)[:120]})
            raise IdentityException(f"error en {metodo}: {e}", id_empresa=id_empresa) from e
        finally:
            self._tel.registrar(metodo, (time.time() - t0) * 1000, ok)

    def _evento(self, tipo, id_empresa, payload):
        try:
            from src.services import eventos
            eventos.publicar(tipo, id_empresa=id_empresa, ref_entidad="identity_api", payload=payload)
        except Exception:
            pass

    # ── Construcción de modelos públicos (nunca objetos internos) ────────────
    def _summary(self, centro: dict, tipo_entidad="centro") -> IdentitySummary:
        c = centro or {}
        return IdentitySummary(uuid=c.get("id_centro") or c.get("id"), tipo_entidad=tipo_entidad,
                               nombre=c.get("nombre_centro") or c.get("nombre"),
                               nombre_corto=c.get("nombre_corto"), tipo=c.get("tipo"),
                               nivel=c.get("nivel"), estado=c.get("estado_gobierno") or c.get("estado"),
                               id_empresa=c.get("id_empresa"), propietario=c.get("id_propietario"),
                               responsable=c.get("id_responsable_operativo"))

    def _ref(self, ent: dict, tipo_entidad="centro") -> IdentityReference:
        c = ent or {}
        return IdentityReference(uuid=c.get("id_centro") or c.get("id"), tipo_entidad=tipo_entidad,
                                 tipo=c.get("tipo"), nivel=c.get("nivel"),
                                 nombre=c.get("nombre_centro") or c.get("nombre"),
                                 codigo=c.get("codigo_centro") or c.get("codigo_terminal") or c.get("codigo"),
                                 estado=c.get("estado_gobierno") or c.get("estado"),
                                 id_empresa=c.get("id_empresa"))

    def _resultado(self, ctx, *, uuid=None, id_empresa=None) -> IdentityResult:
        d = ctx.to_dict() if hasattr(ctx, "to_dict") else dict(ctx or {})
        centro = d.get("centro") or {}
        resumen = self._summary(centro).to_dict() if centro else None
        return IdentityResult(ok=True, uuid=uuid or d.get("id_centro"), id_empresa=d.get("id_empresa"),
                              origen=d.get("origen"), resumen=resumen, contexto=d)

    # ── Resolución ───────────────────────────────────────────────────────────
    def resolver(self, **kw) -> IdentityResult:
        emp = B.emp(kw.get("id_empresa"))
        def _f():
            ctx = self._resolver.resolver_por_documento(
                id_empresa=emp, id_centro=kw.get("id_centro"), id_terminal=kw.get("id_terminal"),
                id_tienda=kw.get("id_tienda"), id_almacen=kw.get("id_almacen"), usuario=kw.get("usuario"))
            return self._resultado(ctx, id_empresa=emp)
        return self._medir("resolver", _f, id_empresa=emp)

    def resolver_por_uuid(self, uuid_val, *, id_empresa=None) -> IdentityResult:
        emp = B.emp(id_empresa)
        def _f():
            # "No encontrado" se decide por si el UUID corresponde a una entidad real (el contexto
            # siempre trae la empresa activa, así que no sirve como señal de existencia).
            if self._repo.buscar_por_uuid(uuid_val, id_empresa=emp) is None:
                raise IdentityNotFound(f"UUID no resuelto: {uuid_val}", entidad=uuid_val, id_empresa=emp)
            ctx = self._resolver.resolver_por_uuid(uuid_val, id_empresa=emp)
            return self._resultado(ctx, uuid=uuid_val, id_empresa=emp)
        return self._medir("resolver_por_uuid", _f, id_empresa=emp)

    def resolver_por_codigo(self, tipo_codigo, valor, *, id_empresa=None) -> IdentityResult:
        emp = B.emp(id_empresa)
        def _f():
            ctx = self._resolver.resolver_por_codigo(tipo_codigo, valor, id_empresa=emp)
            if not ctx.id_centro:
                raise IdentityNotFound(f"Código no encontrado: {tipo_codigo}={valor}", id_empresa=emp)
            return self._resultado(ctx, id_empresa=emp)
        return self._medir("resolver_por_codigo", _f, id_empresa=emp)

    def resolver_por_terminal(self, id_terminal, *, id_empresa=None) -> IdentityResult:
        emp = B.emp(id_empresa)
        return self._medir("resolver_por_terminal",
                           lambda: self._resultado(self._resolver.resolver_por_terminal(id_terminal, id_empresa=emp), id_empresa=emp),
                           id_empresa=emp)

    def resolver_por_documento(self, **kw) -> IdentityResult:
        return self.resolver(**kw)

    def resolver_por_usuario(self, usuario, *, id_empresa=None) -> IdentityResult:
        emp = B.emp(id_empresa)
        return self._medir("resolver_por_usuario",
                           lambda: self._resultado(self._resolver.resolver_por_usuario(usuario, id_empresa=emp), id_empresa=emp),
                           id_empresa=emp)

    def resolver_por_tienda(self, id_tienda, *, id_empresa=None) -> IdentityResult:
        emp = B.emp(id_empresa)
        return self._medir("resolver_por_tienda",
                           lambda: self._resultado(self._resolver.resolver_por_tienda(id_tienda, id_empresa=emp), id_empresa=emp),
                           id_empresa=emp)

    def resolver_por_almacen(self, id_almacen, *, id_empresa=None) -> IdentityResult:
        emp = B.emp(id_empresa)
        return self._medir("resolver_por_almacen",
                           lambda: self._resultado(self._resolver.resolver_por_almacen(id_almacen, id_empresa=emp), id_empresa=emp),
                           id_empresa=emp)

    def resolver_por_empresa(self, id_empresa=None) -> IdentityResult:
        emp = B.emp(id_empresa)
        return self._medir("resolver_por_empresa",
                           lambda: self._resultado(self._resolver.resolver_por_empresa(id_empresa=emp), id_empresa=emp),
                           id_empresa=emp)

    def obtener_contexto(self, **kw) -> dict:
        """Devuelve el IdentityContext (dict). Lanza IdentityNotFound si no hay empresa resoluble."""
        emp = B.emp(kw.get("id_empresa"))
        def _f():
            res = self.resolver(**{**kw, "id_empresa": emp})
            if not res.contexto or not res.contexto.get("id_empresa"):
                raise IdentityNotFound("Contexto de identidad no resoluble", id_empresa=emp)
            return res.contexto
        return self._medir("obtener_contexto", _f, id_empresa=emp)

    # ── Jerarquía ────────────────────────────────────────────────────────────
    def obtener_jerarquia(self, id_centro, *, id_empresa=None) -> IdentityHierarchy:
        emp = B.emp(id_empresa)
        def _f():
            if not self._repo.get_centro(id_centro, id_empresa=emp):
                raise IdentityHierarchyError(f"Centro inexistente: {id_centro}", id_empresa=emp)
            jer = self._repo.get_jerarquia(id_centro, id_empresa=emp) or {}
            return IdentityHierarchy(uuid=id_centro, id_empresa=emp,
                                     ascendentes=jer.get("ascendentes", []),
                                     descendientes=[self._ref(d).to_dict() for d in jer.get("descendientes", [])])
        return self._medir("obtener_jerarquia", _f, id_empresa=emp)

    def obtener_padres(self, id_centro, *, id_empresa=None) -> list:
        emp = B.emp(id_empresa)
        return self._medir("obtener_padres",
                           lambda: list(self._repo.get_ascendentes(id_centro, id_empresa=emp)),
                           id_empresa=emp)

    def obtener_hijos(self, id_centro, *, id_empresa=None) -> list:
        emp = B.emp(id_empresa)
        def _f():
            from src.services.identidad import centros
            return [self._ref(h).to_dict() for h in centros.hijos_de(id_centro, id_empresa=emp)]
        return self._medir("obtener_hijos", _f, id_empresa=emp)

    # ── Validación / existencia ──────────────────────────────────────────────
    def validar(self, id_centro, *, id_empresa=None, estricto=False) -> dict:
        emp = B.emp(id_empresa)
        def _f():
            vr = self._val.validar_centro(id_centro, id_empresa=emp)
            if not vr.valido:
                self._tel.validaciones_fallidas += 1
                self._evento("identity.api.validation_failed", emp,
                             {"id_centro": id_centro, "bloqueantes": len(vr.bloqueantes)})
                if estricto:
                    raise IdentityValidationError("Identidad no válida", detalle=vr.to_dict(),
                                                  entidad=id_centro, id_empresa=emp)
            return vr.to_dict()
        return self._medir("validar", _f, id_empresa=emp)

    def existe(self, uuid_val, *, id_empresa=None) -> bool:
        emp = B.emp(id_empresa)
        return self._medir("existe",
                           lambda: self._repo.buscar_por_uuid(uuid_val, id_empresa=emp) is not None,
                           id_empresa=emp)

    # ── Búsquedas (devuelven IdentitySearchResult) ───────────────────────────
    def _search(self, criterio, filas, tipo_entidad, emp) -> IdentitySearchResult:
        refs = [self._ref(f, tipo_entidad).to_dict() for f in (filas or [])]
        return IdentitySearchResult(ok=True, total=len(refs), id_empresa=emp, criterio=criterio,
                                    resultados=refs)

    def buscar(self, *, tipo=None, estado=None, id_empresa=None) -> IdentitySearchResult:
        emp = B.emp(id_empresa)
        def _f():
            if tipo:
                return self._search(f"tipo={tipo}", self._repo.buscar_por_tipo(tipo, id_empresa=emp), "centro", emp)
            if estado:
                return self._search(f"estado={estado}", self._repo.buscar_por_estado(estado, id_empresa=emp), "centro", emp)
            return self._search("empresa", self._repo.buscar_por_empresa(id_empresa=emp), "centro", emp)
        return self._medir("buscar", _f, id_empresa=emp)

    def buscar_por_tipo(self, tipo, *, id_empresa=None) -> IdentitySearchResult:
        emp = B.emp(id_empresa)
        return self._medir("buscar_por_tipo",
                           lambda: self._search(f"tipo={tipo}", self._repo.buscar_por_tipo(tipo, id_empresa=emp), "centro", emp),
                           id_empresa=emp)

    def buscar_por_estado(self, estado, *, id_empresa=None) -> IdentitySearchResult:
        emp = B.emp(id_empresa)
        return self._medir("buscar_por_estado",
                           lambda: self._search(f"estado={estado}", self._repo.buscar_por_estado(estado, id_empresa=emp), "centro", emp),
                           id_empresa=emp)

    def buscar_por_empresa(self, id_empresa=None) -> IdentitySearchResult:
        emp = B.emp(id_empresa)
        return self._medir("buscar_por_empresa",
                           lambda: self._search("empresa", self._repo.buscar_por_empresa(id_empresa=emp), "centro", emp),
                           id_empresa=emp)

    def buscar_por_grupo(self, id_grupo) -> IdentitySearchResult:
        def _f():
            filas = self._repo.buscar_por_grupo(id_grupo)
            return self._search(f"grupo={id_grupo}",
                                [{"id": f.get("id_empresa"), "nombre": f.get("nombre_empresa"),
                                  "codigo": f.get("codigo_empresa")} for f in filas], "empresa", None)
        return self._medir("buscar_por_grupo", _f)

    # ── Telemetría ───────────────────────────────────────────────────────────
    def telemetria(self) -> dict:
        return self._tel.snapshot()


# Singleton de proceso (versión pública actual).
_API = IdentityAPI(API_VERSION)


def api(version=API_VERSION) -> IdentityAPI:
    """Punto de acceso a la Identity API. `version` reservado para v1/v2/v3 (hoy solo v2)."""
    if version == API_VERSION:
        return _API
    return IdentityAPI(version)
