"""
IOC v2 · IdentityService (Parte 1.7) — capa superior y ÚNICA puerta pública para los consumidores del
ERP (CRM/RRHH/TPV/Producción/Stock/Compras/Calidad/SAT/Finanzas/BI/SOMA). Reutiliza
`IdentityRepository` (lectura), `IdentityResolver`, `IdentityValidationEngine` y los servicios de
gobierno/centros existentes (mutación). NUNCA accede a la BD directamente. Cada operación audita
(usuario/empresa/terminal/IP/UUID/operación/resultado/duración) e invalida la caché afectada.
Los consumidores no acceden al Repository ni al Cache: solo al Service.
"""

import logging
import time

from src.services.identidad import _base as B
from src.services.identidad.cache import cache
from src.services.identidad.repository import repository
from src.services.identidad.resolver import resolver
from src.services.identidad.validation import validation_engine

logger = logging.getLogger("identidad.service")


class IdentityService:
    def __init__(self):
        self._repo = repository()
        self._resolver = resolver()
        self._val = validation_engine()
        self._cache = cache()

    # ── Auditoría con duración ───────────────────────────────────────────────
    def _audit_op(self, operacion, uuid_val, resultado, duracion_ms, *, id_empresa=None,
                  id_terminal=None, ip=None):
        try:
            from src.db.conexion import log_auditoria
            log_auditoria("identidad", operacion, "ioc",
                          f"emp={B.emp(id_empresa)} uuid={uuid_val} term={id_terminal} ip={ip} "
                          f"res={resultado} dur={duracion_ms}ms")
        except Exception:
            pass

    def _evento(self, tipo, uuid_val, id_empresa, payload=None):
        try:
            from src.services import eventos
            eventos.publicar(tipo, id_empresa=id_empresa, ref_entidad="identidad", ref_id=uuid_val,
                             payload=payload or {})
        except Exception:
            pass

    # ── Ciclo de vida ────────────────────────────────────────────────────────
    def crear_identidad(self, nombre, *, tipo="OTRO", nivel=None, id_centro_padre=None,
                        id_empresa=None, id_terminal=None, ip=None, **kw):
        t0 = time.time()
        from src.services.identidad import centros
        cid = centros.crear_centro(nombre, tipo=tipo, nivel=nivel, id_centro_padre=id_centro_padre,
                                   id_empresa=id_empresa, **kw)
        dur = int((time.time() - t0) * 1000)
        self._cache.invalidar(B.emp(id_empresa))
        self._audit_op("CREAR", cid, bool(cid), dur, id_empresa=id_empresa, id_terminal=id_terminal, ip=ip)
        self._evento("identidad.actualizada", cid, B.emp(id_empresa), {"op": "crear"})
        return cid

    def actualizar_identidad(self, id_centro, *, id_empresa=None, id_terminal=None, ip=None, **campos):
        t0 = time.time()
        # Atributos gobernados (auditados con valor anterior/nuevo, guard de inmutables).
        from src.services.identidad import gobierno
        resultados = {}
        for campo, valor in campos.items():
            resultados[campo] = gobierno.modificar_atributo(
                "centro", id_centro, campo, valor, ip=ip, id_terminal=id_terminal, id_empresa=id_empresa)
        ok = all(r.get("ok") for r in resultados.values()) if resultados else True
        dur = int((time.time() - t0) * 1000)
        self._cache.invalidar(B.emp(id_empresa))
        self._audit_op("ACTUALIZAR", id_centro, ok, dur, id_empresa=id_empresa,
                       id_terminal=id_terminal, ip=ip)
        self._evento("identidad.actualizada", id_centro, B.emp(id_empresa), {"campos": list(campos)})
        return {"ok": ok, "detalle": resultados}

    def mover_identidad(self, id_centro, nuevo_padre, *, id_empresa=None, id_terminal=None, ip=None):
        """Reubica un centro bajo otro padre, validando que no se cree un ciclo."""
        t0 = time.time()
        emp = B.emp(id_empresa)
        # Validación previa: el nuevo padre no puede ser descendiente del centro.
        desc = {d.get("id_centro") for d in self._repo.get_descendientes(id_centro, id_empresa=emp)}
        if nuevo_padre == id_centro or nuevo_padre in desc:
            return {"ok": False, "motivo": "movimiento crearía un ciclo"}
        from src.services.identidad import gobierno
        res = gobierno.modificar_atributo("centro", id_centro, "id_centro_padre", nuevo_padre,
                                          ip=ip, id_terminal=id_terminal, id_empresa=emp)
        dur = int((time.time() - t0) * 1000)
        self._cache.invalidar(emp)
        self._audit_op("MOVER", id_centro, res.get("ok"), dur, id_empresa=emp,
                       id_terminal=id_terminal, ip=ip)
        self._evento("identidad.movida", id_centro, emp, {"nuevo_padre": nuevo_padre})
        return res

    def archivar_identidad(self, id_centro, *, id_empresa=None, id_terminal=None, ip=None):
        return self._transicion(id_centro, "ARCHIVADO", "ARCHIVAR", id_empresa=id_empresa,
                                id_terminal=id_terminal, ip=ip)

    def activar_identidad(self, id_centro, *, id_empresa=None, id_terminal=None, ip=None):
        return self._transicion(id_centro, "ACTIVO", "ACTIVAR", id_empresa=id_empresa,
                                id_terminal=id_terminal, ip=ip)

    def desactivar_identidad(self, id_centro, *, id_empresa=None, id_terminal=None, ip=None):
        return self._transicion(id_centro, "SUSPENDIDO", "DESACTIVAR", id_empresa=id_empresa,
                                id_terminal=id_terminal, ip=ip)

    def _transicion(self, id_centro, nuevo_estado, operacion, *, id_empresa=None, id_terminal=None, ip=None):
        t0 = time.time()
        emp = B.emp(id_empresa)
        from src.services.identidad import gobierno
        actual = gobierno.estado_actual("centro", id_centro) or "ACTIVO"
        # Validación de transición vía el motor (no se duplica lógica).
        vr = self._val.validar_transicion(actual, nuevo_estado)
        if not vr.valido:
            return {"ok": False, "motivo": "transición inválida", "validacion": vr.to_dict()}
        res = gobierno.transicionar_estado("centro", id_centro, nuevo_estado, ip=ip,
                                           id_terminal=id_terminal, id_empresa=emp)
        dur = int((time.time() - t0) * 1000)
        self._cache.invalidar(emp)
        self._audit_op(operacion, id_centro, res.get("ok"), dur, id_empresa=emp,
                       id_terminal=id_terminal, ip=ip)
        return res

    # ── Resolución / validación (delegadas) ──────────────────────────────────
    def resolver_identidad(self, **kw):
        """Devuelve un IdentityContext. Acepta id_centro/id_terminal/id_tienda/id_almacen/usuario…"""
        if "uuid_val" in kw:
            return self._resolver.resolver_por_uuid(kw["uuid_val"], id_empresa=kw.get("id_empresa"))
        return self._resolver.resolver_por_documento(**kw)

    def validar_identidad(self, id_centro, *, id_empresa=None):
        return self._val.validar_centro(id_centro, id_empresa=id_empresa).to_dict()

    # ── Configuración: clonar / heredar ──────────────────────────────────────
    def clonar_configuracion(self, id_centro_origen, id_centro_destino, *, id_empresa=None):
        """Copia los códigos operativos del centro origen al destino (no toca identidad)."""
        emp = B.emp(id_empresa)
        from src.services.identidad import codigos
        origen = self._repo.get_codigos(id_centro_origen)
        copiados = 0
        for tipo_cod, valor in origen.items():
            if codigos.set_codigo(id_centro_destino, tipo_cod, valor, id_empresa=emp):
                copiados += 1
        self._cache.invalidar(emp)
        self._evento("identidad.actualizada", id_centro_destino, emp, {"op": "clonar_config"})
        return {"ok": True, "copiados": copiados}

    def heredar_configuracion(self, id_centro, atributo, *, id_empresa=None):
        """Resuelve un atributo por herencia jerárquica (override local gana)."""
        return self._repo.get_config_heredada(id_centro, atributo, id_empresa=id_empresa)

    # ── Sincronización (invalida caché + evento; base para SaaS) ─────────────
    def sincronizar_identidad(self, *, id_empresa=None):
        emp = B.emp(id_empresa)
        n = self._cache.invalidar(emp)
        self._evento("identidad.sincronizada", emp, emp, {"cache_invalidada": n})
        return {"ok": True, "cache_invalidada": n}


_SERVICE = IdentityService()


def service() -> IdentityService:
    """Única puerta pública IOC para los consumidores del ERP."""
    return _SERVICE
